"""
server.py
---------
Flask-based REST API server for the Multi-Cloud Platform.
Exposes HTTP endpoints that the web front-end and mobile app consume.
Runs locally on the user's PC to simulate a prototype backend.

Endpoints:
  GET  /api/providers              -- list registered providers
  GET  /api/files?provider=<name>  -- list files on a provider
  POST /api/upload                 -- upload a file to a provider
  GET  /api/download/<provider>/<file_id> -- download a file
  DELETE /api/delete/<provider>/<file_id> -- delete a file
  POST /api/transfer               -- copy/move between providers
  GET  /api/history                -- transfer history
  GET  /api/quota?provider=<name>  -- quota for a provider
  GET  /api/stats                  -- database statistics
  GET  /                           -- serve the web front-end

Course concepts used: Web API (Flask), Object-Oriented Programming,
                      Database Integration
"""

import os
import json
import tempfile
from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename

from cloud_provider import (
    GoogleDriveProvider,
    OneDriveProvider,
    ProviderRegistry,
    CloudException,
)
from transfer import TransferEngine
from database import Database


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(config: dict = None) -> Flask:
    """
    Create and configure the Flask application.

    :param config: Optional dict overriding default configuration values.
    :return: Configured Flask app instance.
    """
    app = Flask(__name__, static_folder="web")
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024   # 500 MB upload limit
    app.config["UPLOAD_TEMP_DIR"] = tempfile.mkdtemp(prefix="mc_upload_")

    if config:
        app.config.update(config)

    # -- Initialise providers ------------------------------------------------
    google = GoogleDriveProvider(
        credentials={"api_key": "demo-google-key"},
        storage_root="sim_google",
    )
    onedrive = OneDriveProvider(
        credentials={"client_id": "demo-client-id",
                     "client_secret": "demo-client-secret"},
        storage_root="sim_onedrive",
    )
    google.authenticate()
    onedrive.authenticate()

    ProviderRegistry.register(google)
    ProviderRegistry.register(onedrive)

    # -- Shared services -------------------------------------------------
    app.transfer_engine = TransferEngine()
    app.db = Database("multicloud.db")

    # ------------------------------------------------------------------ #
    # ROUTES                                                               #
    # ------------------------------------------------------------------ #

    @app.route("/")
    def index():
        """Serve the single-page web application."""
        return send_from_directory("web", "index.html")

    # -- Provider routes -----------------------------------------------------

    @app.route("/api/providers", methods=["GET"])
    def list_providers():
        """Return a JSON list of all registered cloud provider names."""
        return jsonify({
            "providers": ProviderRegistry.provider_names()
        })

    # -- File routes ---------------------------------------------------------

    @app.route("/api/files", methods=["GET"])
    def list_files():
        """
        List files on a cloud provider.
        Query param: provider (required), path (optional, default '/')
        """
        provider_name = request.args.get("provider")
        path = request.args.get("path", "/")

        if not provider_name:
            return jsonify({"error": "Query param 'provider' is required."}), 400

        try:
            provider = ProviderRegistry.get(provider_name)
            files = provider.list_files(path)
            return jsonify({
                "provider": provider_name,
                "path":     path,
                "files":    [f.to_dict() for f in files],
            })
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except CloudException as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/upload", methods=["POST"])
    def upload_file():
        """
        Upload a file to a cloud provider.
        Form data: provider (str), path (str, optional), file (binary)
        """
        provider_name = request.form.get("provider")
        remote_path   = request.form.get("path", "/")

        if not provider_name:
            return jsonify({"error": "'provider' field is required."}), 400
        if "file" not in request.files:
            return jsonify({"error": "No file part in the request."}), 400

        file_obj = request.files["file"]
        if file_obj.filename == "":
            return jsonify({"error": "No file selected."}), 400

        try:
            provider = ProviderRegistry.get(provider_name)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

        # Save to temp dir then upload to provider
        filename    = secure_filename(file_obj.filename)
        temp_path   = os.path.join(app.config["UPLOAD_TEMP_DIR"], filename)
        file_obj.save(temp_path)

        try:
            cloud_file = provider.upload(temp_path, remote_path)
            app.db.save_file(cloud_file)
            os.unlink(temp_path)  # remove temp copy
            return jsonify({
                "message":    "Upload successful.",
                "cloud_file": cloud_file.to_dict(),
            }), 201
        except CloudException as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/download/<provider_name>/<file_id>", methods=["GET"])
    def download_file(provider_name: str, file_id: str):
        """
        Download a file from a cloud provider and stream it to the client.
        URL params: provider_name, file_id
        """
        try:
            provider    = ProviderRegistry.get(provider_name)
            local_dir   = tempfile.mkdtemp(prefix="mc_dl_")
            local_path  = provider.download(file_id, local_dir)
            return send_file(local_path, as_attachment=True,
                             download_name=os.path.basename(local_path))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except CloudException as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/delete/<provider_name>/<file_id>", methods=["DELETE"])
    def delete_file(provider_name: str, file_id: str):
        """
        Delete a file from a cloud provider and remove its DB record.
        URL params: provider_name, file_id
        """
        try:
            provider = ProviderRegistry.get(provider_name)
            provider.delete(file_id)
            app.db.delete_file_record(file_id)
            return jsonify({"message": f"File '{file_id}' deleted from {provider_name}."}), 200
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except CloudException as exc:
            return jsonify({"error": str(exc)}), 500

    # -- Transfer routes -----------------------------------------------------

    @app.route("/api/transfer", methods=["POST"])
    def transfer_file():
        """
        Copy or move a file between two cloud providers.
        JSON body:
          {
            "operation":   "copy" | "move",
            "source":      "<provider name>",
            "destination": "<provider name>",
            "file_id":     "<cloud file id>",
            "path":        "<destination remote path>"   (optional)
          }
        """
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required."}), 400

        operation   = data.get("operation", "copy")
        source_name = data.get("source")
        dest_name   = data.get("destination")
        file_id     = data.get("file_id")
        remote_path = data.get("path", "/")

        if not all([source_name, dest_name, file_id]):
            return jsonify({
                "error": "'source', 'destination', and 'file_id' are all required."
            }), 400

        try:
            source      = ProviderRegistry.get(source_name)
            destination = ProviderRegistry.get(dest_name)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404

        if operation == "copy":
            record = app.transfer_engine.copy(source, destination,
                                              file_id, remote_path)
        elif operation == "move":
            record = app.transfer_engine.move(source, destination,
                                              file_id, remote_path)
        else:
            return jsonify({"error": f"Unknown operation '{operation}'. "
                                     f"Use 'copy' or 'move'."}), 400

        app.db.save_transfer(record)

        status_code = 200 if record.status == "success" else 500
        return jsonify(record.to_dict()), status_code

    # -- History & stats routes ----------------------------------------------

    @app.route("/api/history", methods=["GET"])
    def transfer_history():
        """Return the last N transfer records from the database."""
        limit = int(request.args.get("limit", 50))
        records = app.db.get_transfer_history(limit)
        return jsonify({"history": records})

    @app.route("/api/quota", methods=["GET"])
    def quota():
        """
        Return quota information for a provider.
        Query param: provider (required)
        """
        provider_name = request.args.get("provider")
        if not provider_name:
            return jsonify({"error": "Query param 'provider' is required."}), 400
        try:
            provider = ProviderRegistry.get(provider_name)
            q = provider.get_quota()
            q["provider"] = provider_name
            return jsonify(q)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except CloudException as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/stats", methods=["GET"])
    def stats():
        """Return aggregated statistics from the local database."""
        return jsonify(app.db.get_stats())

    # -- Error handlers ------------------------------------------------------

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "File too large. Maximum upload is 500 MB."}), 413

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Endpoint not found."}), 404

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 60)
    print("  Multi-Cloud Platform Server")
    print("  Running at:  http://127.0.0.1:5000")
    print("  API base:    http://127.0.0.1:5000/api")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
