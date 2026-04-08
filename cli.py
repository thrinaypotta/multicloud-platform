"""
cli.py
------
Command Line Interface for the Multi-Cloud Platform.
Allows users to list, upload, download, transfer, and check quota
from a terminal without launching the web server.

Usage examples:
  python cli.py list   --provider "Google Drive"
  python cli.py upload --provider "Google Drive" --file ./report.pdf
  python cli.py download --provider "Google Drive" --id <file_id> --dest ./downloads
  python cli.py copy   --src "Google Drive" --dst "Microsoft OneDrive" --id <file_id>
  python cli.py move   --src "Google Drive" --dst "Microsoft OneDrive" --id <file_id>
  python cli.py quota  --provider "Google Drive"
  python cli.py history

Course concepts used: Command Line Interface, Object-Oriented Programming,
                      Database Integration
"""

import argparse
import sys
import os

# Ensure the project root is importable even when CLI is run from any dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud_provider import (
    GoogleDriveProvider,
    OneDriveProvider,
    ProviderRegistry,
    CloudException,
    CloudFile,
)
from transfer import TransferEngine
from database import Database


# ---------------------------------------------------------------------------
# CLIApp: encapsulates the full CLI lifecycle (OOP pattern)
# ---------------------------------------------------------------------------

class CLIApp:
    """
    Command-line application that exposes cloud management commands.
    All provider initialisation is done once in __init__, then the
    appropriate command handler is dispatched based on parsed arguments.
    """

    def __init__(self):
        """Initialise providers, registry, engine, and database."""
        # Simulated Google Drive
        self._google = GoogleDriveProvider(
            credentials={"api_key": "demo-google-key"},
            storage_root=os.path.join(os.path.dirname(__file__), "sim_google"),
        )
        # Simulated Microsoft OneDrive
        self._onedrive = OneDriveProvider(
            credentials={"client_id": "demo-id", "client_secret": "demo-secret"},
            storage_root=os.path.join(os.path.dirname(__file__), "sim_onedrive"),
        )
        self._google.authenticate()
        self._onedrive.authenticate()

        ProviderRegistry.register(self._google)
        ProviderRegistry.register(self._onedrive)

        self._engine = TransferEngine()
        self._db = Database(
            os.path.join(os.path.dirname(__file__), "multicloud.db")
        )

    # -- Argument parser -----------------------------------------------------

    def build_parser(self) -> argparse.ArgumentParser:
        """
        Construct the top-level argument parser with sub-commands.
        :return: Configured ArgumentParser instance
        """
        parser = argparse.ArgumentParser(
            prog="multicloud",
            description="Multi-Cloud Platform CLI — manage files across Google Drive and OneDrive",
        )
        sub = parser.add_subparsers(dest="command", metavar="COMMAND")
        sub.required = True

        # -- list ------------------------------------------------------------
        p_list = sub.add_parser("list", help="List files on a provider")
        p_list.add_argument("--provider", required=True,
                            help='Provider name, e.g. "Google Drive"')
        p_list.add_argument("--path", default="/",
                            help='Remote path to list (default: /)')

        # -- upload ----------------------------------------------------------
        p_upload = sub.add_parser("upload", help="Upload a local file to a provider")
        p_upload.add_argument("--provider", required=True,
                              help='Target provider name')
        p_upload.add_argument("--file", required=True,
                              help="Path to the local file to upload")
        p_upload.add_argument("--path", default="/",
                              help="Remote destination path (default: /)")

        # -- download --------------------------------------------------------
        p_dl = sub.add_parser("download", help="Download a file from a provider")
        p_dl.add_argument("--provider", required=True,
                          help="Provider name")
        p_dl.add_argument("--id", required=True, dest="file_id",
                          help="Cloud file ID (from list command)")
        p_dl.add_argument("--dest", default="./downloads",
                          help="Local directory to save the file (default: ./downloads)")

        # -- delete ----------------------------------------------------------
        p_del = sub.add_parser("delete", help="Delete a file from a provider")
        p_del.add_argument("--provider", required=True,
                           help="Provider name")
        p_del.add_argument("--id", required=True, dest="file_id",
                           help="Cloud file ID")

        # -- copy ------------------------------------------------------------
        p_copy = sub.add_parser("copy", help="Copy a file between providers")
        p_copy.add_argument("--src",  required=True, help="Source provider name")
        p_copy.add_argument("--dst",  required=True, help="Destination provider name")
        p_copy.add_argument("--id",   required=True, dest="file_id",
                            help="Cloud file ID on the source provider")
        p_copy.add_argument("--path", default="/",
                            help="Destination path (default: /)")

        # -- move ------------------------------------------------------------
        p_move = sub.add_parser("move", help="Move a file between providers")
        p_move.add_argument("--src",  required=True, help="Source provider name")
        p_move.add_argument("--dst",  required=True, help="Destination provider name")
        p_move.add_argument("--id",   required=True, dest="file_id",
                            help="Cloud file ID on the source provider")
        p_move.add_argument("--path", default="/",
                            help="Destination path (default: /)")

        # -- quota -----------------------------------------------------------
        p_quota = sub.add_parser("quota", help="Show storage quota for a provider")
        p_quota.add_argument("--provider", required=True,
                             help="Provider name")

        # -- history ---------------------------------------------------------
        p_hist = sub.add_parser("history", help="Show recent transfer history")
        p_hist.add_argument("--limit", type=int, default=20,
                            help="Maximum number of records to show (default: 20)")

        # -- providers -------------------------------------------------------
        sub.add_parser("providers", help="List all registered providers")

        return parser

    # -- Command handlers ----------------------------------------------------

    def cmd_list(self, args):
        """Handle the 'list' command."""
        try:
            provider = ProviderRegistry.get(args.provider)
            files = provider.list_files(args.path)
        except (KeyError, CloudException) as exc:
            self._error(exc)
            return

        if not files:
            print(f"No files found at '{args.path}' on {args.provider}.")
            return

        self._print_separator()
        print(f"  Files on {args.provider} — path: {args.path}")
        self._print_separator()
        print(f"  {'NAME':<30} {'SIZE':>10}  {'FILE ID'}")
        self._print_separator()
        for f in files:
            size_str = CloudFile._format_size(f.size)
            print(f"  {f.name:<30} {size_str:>10}  {f.file_id}")
        self._print_separator()

    def cmd_upload(self, args):
        """Handle the 'upload' command."""
        if not os.path.isfile(args.file):
            self._error(f"File not found: {args.file}")
            return
        try:
            provider = ProviderRegistry.get(args.provider)
            cloud_file = provider.upload(args.file, args.path)
            self._db.save_file(cloud_file)
            print(f"\n✅  Uploaded '{cloud_file.name}' ({CloudFile._format_size(cloud_file.size)})"
                  f" to {args.provider} at '{cloud_file.path}'")
            print(f"    File ID: {cloud_file.file_id}\n")
        except (KeyError, CloudException) as exc:
            self._error(exc)

    def cmd_download(self, args):
        """Handle the 'download' command."""
        try:
            provider   = ProviderRegistry.get(args.provider)
            saved_path = provider.download(args.file_id, args.dest)
            print(f"\n✅  Downloaded to: {saved_path}\n")
        except (KeyError, CloudException) as exc:
            self._error(exc)

    def cmd_delete(self, args):
        """Handle the 'delete' command."""
        confirm = input(f"Delete file '{args.file_id}' from {args.provider}? [y/N]: ")
        if confirm.strip().lower() != "y":
            print("Aborted.")
            return
        try:
            provider = ProviderRegistry.get(args.provider)
            provider.delete(args.file_id)
            self._db.delete_file_record(args.file_id)
            print(f"\n✅  File deleted from {args.provider}.\n")
        except (KeyError, CloudException) as exc:
            self._error(exc)

    def cmd_copy(self, args):
        """Handle the 'copy' command."""
        self._do_transfer(args, operation="copy")

    def cmd_move(self, args):
        """Handle the 'move' command."""
        self._do_transfer(args, operation="move")

    def _do_transfer(self, args, operation: str):
        """
        Shared implementation for copy and move commands.
        :param args:      Parsed CLI namespace with src, dst, file_id, path
        :param operation: 'copy' or 'move'
        """
        try:
            src = ProviderRegistry.get(args.src)
            dst = ProviderRegistry.get(args.dst)
        except KeyError as exc:
            self._error(exc)
            return

        if operation == "copy":
            record = self._engine.copy(src, dst, args.file_id, args.path)
        else:
            record = self._engine.move(src, dst, args.file_id, args.path)

        self._db.save_transfer(record)

        if record.status == "success":
            print(f"\n✅  {operation.capitalize()} succeeded in {record.duration_secs:.2f}s\n")
        else:
            print(f"\n❌  {operation.capitalize()} failed: {record.message}\n")

    def cmd_quota(self, args):
        """Handle the 'quota' command."""
        try:
            provider = ProviderRegistry.get(args.provider)
            q = provider.get_quota()
        except (KeyError, CloudException) as exc:
            self._error(exc)
            return

        used_str  = CloudFile._format_size(q["used"])
        free_str  = CloudFile._format_size(q["free"])
        total_str = CloudFile._format_size(q["total"])
        pct = (q["used"] / q["total"] * 100) if q["total"] > 0 else 0
        bar_width = 40
        filled    = int(bar_width * pct / 100)

        print(f"\n  Storage quota — {args.provider}")
        print(f"  [{'█' * filled}{'░' * (bar_width - filled)}] {pct:.1f}%")
        print(f"  Used: {used_str}  |  Free: {free_str}  |  Total: {total_str}\n")

    def cmd_history(self, args):
        """Handle the 'history' command."""
        records = self._db.get_transfer_history(args.limit)
        if not records:
            print("No transfer history found.")
            return
        self._print_separator()
        print(f"  Transfer History (last {args.limit} records)")
        self._print_separator()
        print(f"  {'TIME':<17} {'OP':<6} {'FILE':<22} {'SRC':>14} → {'DST':<20} {'STATUS'}")
        self._print_separator()
        for r in records:
            ts = r["timestamp"][:16].replace("T", " ")
            print(f"  {ts:<17} {r['operation']:<6} {r['file_name'][:21]:<22} "
                  f"{r['source']:>14} → {r['destination']:<20} {r['status']}")
        self._print_separator()

    def cmd_providers(self, _args):
        """Handle the 'providers' command."""
        print("\n  Registered providers:")
        for name in ProviderRegistry.provider_names():
            print(f"    • {name}")
        print()

    # -- Utilities -----------------------------------------------------------

    @staticmethod
    def _print_separator():
        print("  " + "-" * 78)

    @staticmethod
    def _error(msg):
        print(f"\n❌  Error: {msg}\n", file=sys.stderr)

    # -- Main entry point ----------------------------------------------------

    def run(self):
        """Parse arguments and dispatch to the appropriate command handler."""
        parser = self.build_parser()
        args   = parser.parse_args()

        dispatch = {
            "list":      self.cmd_list,
            "upload":    self.cmd_upload,
            "download":  self.cmd_download,
            "delete":    self.cmd_delete,
            "copy":      self.cmd_copy,
            "move":      self.cmd_move,
            "quota":     self.cmd_quota,
            "history":   self.cmd_history,
            "providers": self.cmd_providers,
        }

        handler = dispatch.get(args.command)
        if handler:
            handler(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    app = CLIApp()
    app.run()
