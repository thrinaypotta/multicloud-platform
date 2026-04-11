"""
cli.py

The text version of the website — do everything from the terminal
instead of clicking buttons in a browser.

Usage:
    python cli.py list     --provider "Google Drive"
    python cli.py upload   --provider "Google Drive" --file ./report.pdf
    python cli.py download --provider "Google Drive" --id <file_id>
    python cli.py delete   --provider "Google Drive" --id <file_id>
    python cli.py copy     --src "Google Drive" --dst "Microsoft OneDrive" --id <file_id>
    python cli.py move     --src "Google Drive" --dst "Microsoft OneDrive" --id <file_id>
    python cli.py quota    --provider "Google Drive"
    python cli.py history  --limit 20
    python cli.py providers


"""

import os, argparse
from cloud_provider import (GoogleDriveProvider, OneDriveProvider,
                            ProviderRegistry, CloudException, CloudFile)
from transfer import TransferEngine
from database import Database


class CLIApp:
    """The terminal version of our Multi-Cloud Platform."""

    def __init__(self):
        root = os.path.dirname(os.path.abspath(__file__))
        g    = GoogleDriveProvider({"api_key": "demo-key"},
                                   os.path.join(root, "sim_google"))
        o    = OneDriveProvider({"client_id": "demo-id", "client_secret": "demo-secret"},
                                os.path.join(root, "sim_onedrive"))
        g.authenticate(); o.authenticate()
        ProviderRegistry.register(g); ProviderRegistry.register(o)
        self._e  = TransferEngine()
        self._db = Database(os.path.join(root, "multicloud.db"))

    def run(self, argv: list = None):
        p   = argparse.ArgumentParser(prog="cli", description="Multi-Cloud Platform CLI")
        sub = p.add_subparsers(dest="cmd"); sub.required = True

        def add(name, **kw):
            s = sub.add_parser(name)
            for k, v in kw.items(): s.add_argument(f"--{k}", **v)

        add("list",     provider={"required": True}, path={"default": "/"})
        add("upload",   provider={"required": True}, file={"required": True}, path={"default": "/"})
        add("download", provider={"required": True}, id={"required": True, "dest": "file_id"}, dest={"default": "./downloads"})
        add("delete",   provider={"required": True}, id={"required": True, "dest": "file_id"})
        add("copy",     src={"required": True}, dst={"required": True}, id={"required": True, "dest": "file_id"}, path={"default": "/"})
        add("move",     src={"required": True}, dst={"required": True}, id={"required": True, "dest": "file_id"}, path={"default": "/"})
        add("quota",    provider={"required": True})
        add("history",  limit={"type": int, "default": 20})
        sub.add_parser("providers")

        a = p.parse_args(argv)
        getattr(self, f"_{a.cmd}")(a)

    def _list(self, a):
        try: files = ProviderRegistry.get(a.provider).list_files(a.path)
        except (KeyError, CloudException) as e: print(f"Error: {e}"); return
        if not files: print(f"No files at '{a.path}'."); return
        print(f"\n  {'NAME':<30} {'SIZE':>10}  ID")
        print("  " + "-" * 60)
        for f in files: print(f"  {f.name:<30} {CloudFile._fmt(f.size):>10}  {f.file_id}")
        print()

    def _upload(self, a):
        if not os.path.isfile(a.file): print(f"File not found: {a.file}"); return
        try:
            cf = ProviderRegistry.get(a.provider).upload(a.file, a.path)
            self._db.save_file(cf)
            print(f"\n✅  '{cf.name}'  ID: {cf.file_id}\n")
        except (KeyError, CloudException) as e: print(f"Error: {e}")

    def _download(self, a):
        try:
            path = ProviderRegistry.get(a.provider).download(a.file_id, a.dest)
            print(f"\n✅  Saved to: {path}\n")
        except (KeyError, CloudException) as e: print(f"Error: {e}")

    def _delete(self, a):
        if input(f"Delete '{a.file_id}'? [y/N]: ").strip().lower() != "y": return
        try:
            ProviderRegistry.get(a.provider).delete(a.file_id)
            self._db.delete_file(a.file_id)
            print("\n✅  Deleted.\n")
        except (KeyError, CloudException) as e: print(f"Error: {e}")

    def _copy(self, a): self._transfer(a, "copy")
    def _move(self, a): self._transfer(a, "move")

    def _transfer(self, a, op):
        try: s, d = ProviderRegistry.get(a.src), ProviderRegistry.get(a.dst)
        except KeyError as e: print(f"Error: {e}"); return
        fn  = self._e.copy if op == "copy" else self._e.move
        rec = fn(s, d, a.file_id, a.path)
        self._db.save_transfer(rec)
        print(f"\n{'✅' if rec.status=='success' else '❌'}  {op.capitalize()}: {rec.message}\n")

    def _quota(self, a):
        try: q = ProviderRegistry.get(a.provider).get_quota()
        except (KeyError, CloudException) as e: print(f"Error: {e}"); return
        pct = (q["used"] / q["total"] * 100) if q["total"] else 0
        bar = int(40 * pct / 100)
        print(f"\n  {a.provider}")
        print(f"  [{'█'*bar}{'░'*(40-bar)}] {pct:.1f}%")
        print(f"  {CloudFile._fmt(q['used'])} / {CloudFile._fmt(q['total'])}\n")

    def _history(self, a):
        for r in self._db.get_transfers(a.limit):
            print(f"  {r['timestamp'][:16]}  {r['operation']:<5}  "
                  f"{r['file_name']:<20}  {r['source']} → {r['destination']}  {r['status']}")

    def _providers(self, _):
        for n in ProviderRegistry.names(): print(f"  • {n}")


if __name__ == "__main__":
    CLIApp().run()
