"""
database.py
Uses SQLite — a lightweight database that lives in a single file
called multicloud.db.

We save two things:
  - files:     info about every uploaded file
  - transfers: a log of every copy/move attempted

"""

import sqlite3
from datetime import datetime
from cloud_provider import CloudFile
from transfer import TransferRecord


class Database:
    """Saves file info and transfer history to a local SQLite file."""

    def __init__(self, path: str = "multicloud.db"):
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # lets us access columns by name
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT, name TEXT, size INTEGER,
                provider TEXT, path TEXT, modified TEXT, synced TEXT
            );
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT, file_name TEXT, source TEXT,
                destination TEXT, status TEXT, message TEXT,
                timestamp TEXT, duration REAL
            );
        """)
        self._conn.commit()
        print(f"[Database] Connected to '{path}'")

    def save_file(self, f: CloudFile):
        self._conn.execute(
            "INSERT INTO files (file_id,name,size,provider,path,modified,synced) "
            "VALUES (?,?,?,?,?,?,?)",
            (f.file_id, f.name, f.size, f.provider, f.path,
             f.modified.isoformat(), datetime.now().isoformat()))
        self._conn.commit()

    def get_files(self, provider: str = None) -> list:
        q = ("SELECT * FROM files WHERE provider=? ORDER BY modified DESC"
             if provider else "SELECT * FROM files ORDER BY modified DESC")
        rows = self._conn.execute(q, (provider,) if provider else ()).fetchall()
        return [dict(r) for r in rows]

    def delete_file(self, file_id: str):
        # removes the database record only — the actual file is deleted separately
        self._conn.execute("DELETE FROM files WHERE file_id=?", (file_id,))
        self._conn.commit()

    def save_transfer(self, r: TransferRecord):
        self._conn.execute(
            "INSERT INTO transfers (operation,file_name,source,destination,"
            "status,message,timestamp,duration) VALUES (?,?,?,?,?,?,?,?)",
            (r.operation, r.file_name, r.source, r.destination,
             r.status, r.message, r.timestamp.isoformat(), r.duration))
        self._conn.commit()

    def get_transfers(self, limit: int = 50) -> list:
        rows = self._conn.execute(
            "SELECT * FROM transfers ORDER BY timestamp DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        files = self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        total = self._conn.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
        ok    = self._conn.execute("SELECT COUNT(*) FROM transfers WHERE status='success'").fetchone()[0]
        return {"total_files": files, "total_transfers": total,
                "successful": ok, "failed": total - ok}

    def close(self):
        if self._conn: self._conn.close()

    def __del__(self): self.close()
