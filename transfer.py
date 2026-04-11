"""
transfer.py

Handles moving files from one cloud to another.
Since we can't copy directly between clouds, we used a temp folder
on our PC as a middle man


"""

import os, shutil, tempfile
from dataclasses import dataclass, field
from datetime import datetime
from cloud_provider import CloudProvider, CloudException


@dataclass
class TransferRecord:
    """A receipt that records what happened during a copy or move."""
    operation:   str
    file_name:   str
    source:      str
    destination: str
    status:      str
    message:     str      = ""
    timestamp:   datetime = field(default_factory=datetime.now)
    duration:    float    = 0.0

    def __str__(self):
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return (f"[{ts}] {self.operation.upper()} '{self.file_name}' "
                f"{self.source} → {self.destination} | "
                f"{self.status.upper()} ({self.duration:.2f}s)"
                f"{' | ' + self.message if self.message else ''}")

    def to_dict(self) -> dict:
        return {"operation": self.operation, "file_name": self.file_name,
                "source": self.source, "destination": self.destination,
                "status": self.status, "message": self.message,
                "timestamp": self.timestamp.isoformat(), "duration": self.duration}


class TransferEngine:
    """Does the actual work of copying or moving files between clouds."""

    def __init__(self):
        self._tmp     = tempfile.mkdtemp(prefix="mc_")  # temp folder used as middle ground
        self._history = []

    def copy(self, src: CloudProvider, dst: CloudProvider,
             file_id: str, path: str = "/") -> TransferRecord:
        return self._run(src, dst, file_id, path, "copy")

    def move(self, src: CloudProvider, dst: CloudProvider,
             file_id: str, path: str = "/") -> TransferRecord:
        return self._run(src, dst, file_id, path, "move")

    def history(self) -> list: return list(self._history)

    def _run(self, src, dst, file_id, path, op) -> TransferRecord:
        t0, fname = datetime.now(), "unknown"
        try:
            buf   = os.path.join(self._tmp, file_id[:8])
            os.makedirs(buf, exist_ok=True)
            local = src.download(file_id, buf)    # step 1: download to temp
            fname = os.path.basename(local)
            cf    = dst.upload(local, path)        # step 2: upload to destination
            if op == "move": src.delete(file_id)  # step 3: delete original if moving
            shutil.rmtree(buf, ignore_errors=True)
            rec = TransferRecord(op, fname, src.name, dst.name, "success",
                                 f"→ {cf.path}/{cf.name}",
                                 t0, (datetime.now() - t0).total_seconds())
        except CloudException as e:
            # something went wrong — record the failure instead of crashing
            rec = TransferRecord(op, fname, src.name, dst.name, "failed",
                                 str(e), t0, (datetime.now() - t0).total_seconds())
        self._history.append(rec)
        print(rec)
        return rec
