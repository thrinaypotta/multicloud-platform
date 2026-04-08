"""
database.py
-----------
SQLite database layer for persisting file metadata and transfer history.
Provides a clean OOP wrapper around the sqlite3 standard library module.

Course concepts used: Database Integration, Object-Oriented Programming,
                      File I/O
"""

import sqlite3
import os
from datetime import datetime
from cloud_provider import CloudFile
from transfer import TransferRecord


# ---------------------------------------------------------------------------
# Database: thin OOP wrapper around SQLite
# ---------------------------------------------------------------------------

class Database:
    """
    Manages a local SQLite database that stores:
      - Cloud file metadata (table: cloud_files)
      - Transfer / operation history (table: transfer_history)

    All methods use parameterised queries to prevent SQL injection.
    The database file is created automatically if it does not exist.
    """

    def __init__(self, db_path: str = "multicloud.db"):
        """
        :param db_path: Filesystem path for the SQLite database file.
        """
        self._db_path = db_path
        self._conn: sqlite3.Connection = None
        self._connect()
        self._create_tables()

    # -- Connection management -----------------------------------------------

    def _connect(self):
        """Open (or create) the SQLite database file and enable WAL mode."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row   # allows dict-like access
        # WAL mode: allows concurrent reads during writes
        self._conn.execute("PRAGMA journal_mode=WAL;")
        print(f"[Database] Connected to '{self._db_path}'")

    def _create_tables(self):
        """Create the required tables if they do not already exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS cloud_files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id     TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                size        INTEGER NOT NULL DEFAULT 0,
                mime_type   TEXT    NOT NULL DEFAULT 'application/octet-stream',
                provider    TEXT    NOT NULL,
                path        TEXT    NOT NULL DEFAULT '/',
                created     TEXT    NOT NULL,
                modified    TEXT    NOT NULL,
                synced_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transfer_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                operation     TEXT    NOT NULL,
                file_name     TEXT    NOT NULL,
                source        TEXT    NOT NULL,
                destination   TEXT    NOT NULL,
                status        TEXT    NOT NULL,
                message       TEXT    DEFAULT '',
                timestamp     TEXT    NOT NULL,
                duration_secs REAL    NOT NULL DEFAULT 0.0
            );
        """)
        self._conn.commit()

    # -- Cloud file operations -----------------------------------------------

    def save_file(self, cloud_file: CloudFile) -> int:
        """
        Insert or update a CloudFile record in the database.

        :param cloud_file: CloudFile object to persist
        :return: Row ID of the inserted/updated record
        """
        cursor = self._conn.execute("""
            INSERT INTO cloud_files
                (file_id, name, size, mime_type, provider, path, created, modified, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cloud_file.file_id,
            cloud_file.name,
            cloud_file.size,
            cloud_file.mime_type,
            cloud_file.provider,
            cloud_file.path,
            cloud_file.created.isoformat(),
            cloud_file.modified.isoformat(),
            datetime.now().isoformat(),
        ))
        self._conn.commit()
        return cursor.lastrowid

    def get_files(self, provider: str = None) -> list[dict]:
        """
        Retrieve cloud file records, optionally filtered by provider.

        :param provider: Provider name to filter by, or None for all providers
        :return: List of row dicts
        """
        if provider:
            rows = self._conn.execute(
                "SELECT * FROM cloud_files WHERE provider = ? ORDER BY modified DESC",
                (provider,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM cloud_files ORDER BY modified DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_file_record(self, file_id: str) -> bool:
        """
        Remove a file record from the database by its cloud file_id.

        :param file_id: Cloud-provider file identifier
        :return: True if a record was deleted, False if none found
        """
        cursor = self._conn.execute(
            "DELETE FROM cloud_files WHERE file_id = ?", (file_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Transfer history operations -----------------------------------------

    def save_transfer(self, record: TransferRecord) -> int:
        """
        Persist a TransferRecord to the transfer_history table.

        :param record: TransferRecord object to store
        :return: Row ID of the new record
        """
        cursor = self._conn.execute("""
            INSERT INTO transfer_history
                (operation, file_name, source, destination,
                 status, message, timestamp, duration_secs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.operation,
            record.file_name,
            record.source,
            record.destination,
            record.status,
            record.message,
            record.timestamp.isoformat(),
            record.duration_secs,
        ))
        self._conn.commit()
        return cursor.lastrowid

    def get_transfer_history(self, limit: int = 100) -> list[dict]:
        """
        Return the most recent transfer records.

        :param limit: Maximum number of records to return
        :return: List of row dicts ordered newest-first
        """
        rows = self._conn.execute(
            "SELECT * FROM transfer_history ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """
        Compute summary statistics across all stored data.

        :return: Dict with keys 'total_files', 'total_transfers',
                 'successful_transfers', 'failed_transfers'
        """
        total_files = self._conn.execute(
            "SELECT COUNT(*) FROM cloud_files").fetchone()[0]
        total_transfers = self._conn.execute(
            "SELECT COUNT(*) FROM transfer_history").fetchone()[0]
        successful = self._conn.execute(
            "SELECT COUNT(*) FROM transfer_history WHERE status = 'success'"
        ).fetchone()[0]
        return {
            "total_files":         total_files,
            "total_transfers":     total_transfers,
            "successful_transfers": successful,
            "failed_transfers":    total_transfers - successful,
        }

    # -- Lifecycle -----------------------------------------------------------

    def close(self):
        """Close the database connection gracefully."""
        if self._conn:
            self._conn.close()
            print(f"[Database] Connection to '{self._db_path}' closed.")

    def __str__(self):
        stats = self.get_stats()
        return (f"Database(path={self._db_path!r}, "
                f"files={stats['total_files']}, "
                f"transfers={stats['total_transfers']})")

    def __del__(self):
        """Ensure the connection is closed when the object is garbage-collected."""
        self.close()


if __name__ == "__main__":
    # Quick smoke-test
    from cloud_provider import CloudFile
    from transfer import TransferRecord

    db = Database("test_multicloud.db")

    # Save a dummy CloudFile
    cf = CloudFile(
        file_id="abc123",
        name="report.pdf",
        size=204800,
        mime_type="application/pdf",
        provider="Google Drive",
        path="/documents",
    )
    row_id = db.save_file(cf)
    print(f"Saved CloudFile with row_id={row_id}")

    # Save a dummy TransferRecord
    tr = TransferRecord(
        operation="copy",
        file_name="report.pdf",
        source="Google Drive",
        destination="Microsoft OneDrive",
        status="success",
        duration_secs=1.23,
    )
    db.save_transfer(tr)

    # Print stats
    print(db)
    print("Stats:", db.get_stats())
    db.close()

    # Clean up test database
    os.unlink("test_multicloud.db")
