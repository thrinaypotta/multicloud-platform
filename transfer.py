"""
transfer.py
-----------
Transfer engine for copying and moving files between cloud providers.
Acts as an orchestrator: it downloads from the source provider to a
temporary local buffer, then uploads to the destination provider.

Course concepts used: Object-Oriented Programming, Exception Handling,
                      File I/O
"""

import os
import shutil
import tempfile
from datetime import datetime
from dataclasses import dataclass, field

from cloud_provider import CloudProvider, CloudFile, CloudException


# ---------------------------------------------------------------------------
# TransferRecord: immutable log entry for a single transfer operation
# ---------------------------------------------------------------------------

@dataclass
class TransferRecord:
    """
    Stores the result of a single transfer/copy/move operation.

    Fields:
        operation     -- 'copy' or 'move'
        file_name     -- name of the transferred file
        source        -- source provider name
        destination   -- destination provider name
        status        -- 'success' or 'failed'
        message       -- human-readable result or error message
        timestamp     -- when the transfer occurred
        duration_secs -- how long the transfer took in seconds
    """
    operation:     str
    file_name:     str
    source:        str
    destination:   str
    status:        str
    message:       str = ""
    timestamp:     datetime = field(default_factory=datetime.now)
    duration_secs: float = 0.0

    def __str__(self):
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return (f"[{ts}] {self.operation.upper()} {self.file_name!r} "
                f"{self.source} → {self.destination} "
                f"| {self.status.upper()} ({self.duration_secs:.2f}s)"
                f"{' | ' + self.message if self.message else ''}")

    def to_dict(self) -> dict:
        """Serialise to plain dict for JSON API responses."""
        return {
            "operation":     self.operation,
            "file_name":     self.file_name,
            "source":        self.source,
            "destination":   self.destination,
            "status":        self.status,
            "message":       self.message,
            "timestamp":     self.timestamp.isoformat(),
            "duration_secs": self.duration_secs,
        }


# ---------------------------------------------------------------------------
# TransferEngine: orchestrates cross-provider transfers
# ---------------------------------------------------------------------------

class TransferEngine:
    """
    Handles copying and moving files between any two registered
    CloudProvider instances by using a temporary local buffer directory.

    Usage:
        engine = TransferEngine()
        record = engine.copy(src_provider, dst_provider, file_id, remote_path)
    """

    def __init__(self, temp_dir: str = None):
        """
        :param temp_dir: Optional path for the local transfer buffer.
                         If None, the system's default temp directory is used.
        """
        self._temp_dir = temp_dir or tempfile.mkdtemp(prefix="multicloud_")
        self._history: list[TransferRecord] = []

    # -- Public operations ---------------------------------------------------

    def copy(self, source: CloudProvider, destination: CloudProvider,
             file_id: str, remote_path: str = "/") -> TransferRecord:
        """
        Copy a file from source provider to destination provider.
        The original file is preserved on the source.

        :param source:      CloudProvider to copy from
        :param destination: CloudProvider to copy to
        :param file_id:     Unique file identifier on the source provider
        :param remote_path: Destination path on the target provider
        :return: TransferRecord describing the outcome
        """
        return self._transfer(source, destination, file_id,
                              remote_path, operation="copy")

    def move(self, source: CloudProvider, destination: CloudProvider,
             file_id: str, remote_path: str = "/") -> TransferRecord:
        """
        Move a file from source provider to destination provider.
        The original file is deleted from the source after a successful copy.

        :param source:      CloudProvider to move from
        :param destination: CloudProvider to move to
        :param file_id:     Unique file identifier on the source provider
        :param remote_path: Destination path on the target provider
        :return: TransferRecord describing the outcome
        """
        return self._transfer(source, destination, file_id,
                              remote_path, operation="move")

    def get_history(self) -> list[TransferRecord]:
        """Return the full list of transfer records for this session."""
        return list(self._history)

    def clear_history(self):
        """Clear the in-memory transfer history."""
        self._history.clear()

    # -- Internal helpers ----------------------------------------------------

    def _transfer(self, source: CloudProvider, destination: CloudProvider,
                  file_id: str, remote_path: str, operation: str) -> TransferRecord:
        """
        Internal implementation shared by copy() and move().
        Downloads to a temp buffer, uploads to destination, and — for 'move' —
        deletes the source file on success.
        """
        start_time = datetime.now()
        file_name = "unknown"

        try:
            # Step 1: Download from source into a temporary directory
            buffer_dir = os.path.join(self._temp_dir, f"transfer_{file_id[:8]}")
            os.makedirs(buffer_dir, exist_ok=True)

            local_path = source.download(file_id, buffer_dir)
            file_name = os.path.basename(local_path)

            # Step 2: Upload from temp buffer to destination
            cloud_file: CloudFile = destination.upload(local_path, remote_path)

            # Step 3 (move only): delete the original from source
            if operation == "move":
                source.delete(file_id)

            # Step 4: Clean up temp buffer
            shutil.rmtree(buffer_dir, ignore_errors=True)

            duration = (datetime.now() - start_time).total_seconds()
            record = TransferRecord(
                operation=operation,
                file_name=file_name,
                source=source.name,
                destination=destination.name,
                status="success",
                message=f"Stored at {cloud_file.path}/{cloud_file.name}",
                timestamp=start_time,
                duration_secs=duration,
            )

        except CloudException as exc:
            duration = (datetime.now() - start_time).total_seconds()
            record = TransferRecord(
                operation=operation,
                file_name=file_name,
                source=source.name,
                destination=destination.name,
                status="failed",
                message=str(exc),
                timestamp=start_time,
                duration_secs=duration,
            )

        self._history.append(record)
        print(record)
        return record

    def cleanup(self):
        """Remove the entire temporary buffer directory."""
        if os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir)
            print(f"[TransferEngine] Cleaned up temp dir: {self._temp_dir}")

    def __str__(self):
        return (f"TransferEngine(temp={self._temp_dir!r}, "
                f"transfers={len(self._history)})")


if __name__ == "__main__":
    # Smoke-test: copy a small file between two simulated providers
    import tempfile, os
    from cloud_provider import GoogleDriveProvider, OneDriveProvider

    google = GoogleDriveProvider({"api_key": "demo"}, "sim_google")
    onedrive = OneDriveProvider(
        {"client_id": "x", "client_secret": "y"}, "sim_onedrive")

    google.authenticate()
    onedrive.authenticate()

    # Create a test file and upload it to Google
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False,
                                     mode="w") as tmp:
        tmp.write("Hello from the multi-cloud platform!\n")
        tmp_path = tmp.name

    cloud_file = google.upload(tmp_path, "/")
    os.unlink(tmp_path)

    # Now copy it to OneDrive via TransferEngine
    engine = TransferEngine()
    record = engine.copy(google, onedrive, cloud_file.file_id, "/")
    print("Transfer record:", record)
    engine.cleanup()
