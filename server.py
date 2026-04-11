"""
server.py
The waiter of the project. The website asks for things, the server
does the work and sends the answer back as JSON.

Endpoints:
    GET    /                              sends back the website
    GET    /api/providers                 what clouds do we support?
    GET    /api/files?provider=X          list files on cloud X
    POST   /api/upload                    receive and store a file
    GET    /api/download/<cloud>/<id>     send a file to the browser
    DELETE /api/delete/<cloud>/<id>       delete a file
    POST   /api/transfer                  copy or move between clouds
    GET    /api/history                   show past transfers
    GET    /api/quota?provider=X          how full is cloud X?
    GET    /api/stats                     overall numbers

Run locally:   python server.py
Render:        gunicorn server:app


"""

import os, tempfile
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from cloud_provider import (GoogleDriveProvider, OneDriveProvider,
                            ProviderRegistry, CloudException)
from transfer import TransferEngine
from database import Database


def create_app() -> Flask:
    """Builds and boots up the whole Flask application."""

    app = Flask(__name__, static_folder=".", static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # max upload: 500 MB
    app.config["TMP"] = tempfile.mkdtemp(prefix="mc_up_")

    google   = GoogleDriveProvider({"api_key": "demo-key"})
    onedrive = OneDriveProvider({"client_id": "demo-id", "client_secret": "demo-secret"})
    google.authenticate()
    onedrive.authenticate()
    ProviderRegistry.register(google)
    ProviderRegistry.register(onedrive)

    app.engine = TransferEngine()
    app.db     = Database()

    @app.route("/")
    def index():
        return send_file("index.html")

    @app.route("/api/providers")
    def providers():
        return jsonify({"providers": ProviderRegistry.names()})

    @app.route("/api/files")
    def files():
        name = request.args.get("provider")
        path = request.args.get("path", "/")
        if not name: return jsonify({"error": "'provider' required"}), 400
        try:
            return jsonify({"provider": name, "path": path,
                            "files": [f.to_dict() for f in ProviderRegistry.get(name).list_files(path)]})
        except (KeyError, CloudException) as e: return jsonify({"error": str(e)}), 404

    @app.route("/api/upload", methods=["POST"])
    def upload():
        name = request.form.get("provider")
        path = request.form.get("path", "/")
        if not name or "file" not in request.files:
            return jsonify({"error": "Missing provider or file"}), 400
        f   = request.files["file"]
        # secure_filename strips out unwanted characters like "../" from the filename
        tmp = os.path.join(app.config["TMP"], secure_filename(f.filename))
        f.save(tmp)
        try:
            cf = ProviderRegistry.get(name).upload(tmp, path)
            app.db.save_file(cf)
            os.unlink(tmp)  # delete the temp copy once the cloud has it
            return jsonify({"message": "Upload successful.", "cloud_file": cf.to_dict()}), 201
        except (KeyError, CloudException) as e: return jsonify({"error": str(e)}), 500

    @app.route("/api/download/<pname>/<file_id>")
    def download(pname, file_id):
        try:
            d    = tempfile.mkdtemp()
            path = ProviderRegistry.get(pname).download(file_id, d)
            return send_file(path, as_attachment=True, download_name=os.path.basename(path))
        except (KeyError, CloudException) as e: return jsonify({"error": str(e)}), 404

    @app.route("/api/delete/<pname>/<file_id>", methods=["DELETE"])
    def delete(pname, file_id):
        try:
            ProviderRegistry.get(pname).delete(file_id)
            app.db.delete_file(file_id)
            return jsonify({"message": f"'{file_id}' deleted."})
        except (KeyError, CloudException) as e: return jsonify({"error": str(e)}), 404

    @app.route("/api/transfer", methods=["POST"])
    def transfer():
        # browser sends JSON: which file, from where, to where, copy or move
        d   = request.get_json(silent=True) or {}
        op  = d.get("operation", "copy")
        src = d.get("source"); dst = d.get("destination"); fid = d.get("file_id")
        if not all([src, dst, fid]):
            return jsonify({"error": "source, destination, file_id required"}), 400
        try:
            s = ProviderRegistry.get(src); t = ProviderRegistry.get(dst)
        except KeyError as e: return jsonify({"error": str(e)}), 404
        fn  = app.engine.copy if op == "copy" else app.engine.move
        rec = fn(s, t, fid, d.get("path", "/"))
        app.db.save_transfer(rec)
        return jsonify(rec.to_dict()), 200 if rec.status == "success" else 500

    @app.route("/api/history")
    def history():
        return jsonify({"history": app.db.get_transfers(int(request.args.get("limit", 50)))})

    @app.route("/api/quota")
    def quota():
        name = request.args.get("provider")
        if not name: return jsonify({"error": "'provider' required"}), 400
        try:
            q = ProviderRegistry.get(name).get_quota()
            q["provider"] = name
            return jsonify(q)
        except (KeyError, CloudException) as e: return jsonify({"error": str(e)}), 404

    @app.route("/api/stats")
    def stats():
        return jsonify(app.db.stats())

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  MultiCloud Platform  →  http://127.0.0.1:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)
