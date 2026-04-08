"""
tests/test_multicloud.py
------------------------
Unit tests for the Multi-Cloud Platform.
Covers cloud providers, transfer engine, and database layer.

Run with:   python -m pytest tests/ -v
Or:         python tests/test_multicloud.py

Course concepts used: Object-Oriented Programming, File I/O,
                      Database Integration
"""

import os
import sys
import tempfile
import unittest
import shutil

# Make the project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud_provider import (
    GoogleDriveProvider,
    OneDriveProvider,
    ProviderRegistry,
    CloudFile,
    CloudException,
    AuthenticationException,
    FileNotFoundException,
)
from transfer import TransferEngine, TransferRecord
from database import Database


# ---------------------------------------------------------------------------
# Helper: create a small temporary text file
# ---------------------------------------------------------------------------

def _make_temp_file(content: str = "test content\n") -> str:
    """Write content to a named temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write(content)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Test: CloudFile
# ---------------------------------------------------------------------------

class TestCloudFile(unittest.TestCase):
    """Tests for the CloudFile data class."""

    def setUp(self):
        self.cf = CloudFile(
            file_id="abc123",
            name="report.pdf",
            size=204800,
            mime_type="application/pdf",
            provider="Google Drive",
            path="/documents",
        )

    def test_str_contains_name(self):
        """__str__ should include the file name."""
        self.assertIn("report.pdf", str(self.cf))

    def test_to_dict_keys(self):
        """to_dict() should return all expected keys."""
        d = self.cf.to_dict()
        for key in ["file_id", "name", "size", "mime_type", "provider", "path"]:
            self.assertIn(key, d)

    def test_format_size_bytes(self):
        """_format_size should return 'B' for small values."""
        self.assertIn("B", CloudFile._format_size(512))

    def test_format_size_mb(self):
        """_format_size should return 'MB' for megabyte-range values."""
        self.assertIn("MB", CloudFile._format_size(2 * 1024 ** 2))


# ---------------------------------------------------------------------------
# Test: GoogleDriveProvider
# ---------------------------------------------------------------------------

class TestGoogleDriveProvider(unittest.TestCase):
    """Tests for the simulated Google Drive provider."""

    def setUp(self):
        self._tmp_root = tempfile.mkdtemp(prefix="test_google_")
        self.provider = GoogleDriveProvider(
            credentials={"api_key": "test-key"},
            storage_root=self._tmp_root,
        )

    def tearDown(self):
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_authenticate_success(self):
        """authenticate() should return True with valid credentials."""
        result = self.provider.authenticate()
        self.assertTrue(result)

    def test_authenticate_missing_key(self):
        """authenticate() should raise AuthenticationException with no key."""
        bad = GoogleDriveProvider(
            credentials={}, storage_root=self._tmp_root)
        with self.assertRaises(AuthenticationException):
            bad.authenticate()

    def test_upload_and_list(self):
        """Uploaded files should appear in list_files()."""
        self.provider.authenticate()
        tmp = _make_temp_file("hello google")
        try:
            cf = self.provider.upload(tmp, "/")
            files = self.provider.list_files("/")
            names = [f.name for f in files]
            self.assertIn(cf.name, names)
        finally:
            os.unlink(tmp)

    def test_upload_nonexistent_file(self):
        """Uploading a non-existent path should raise FileNotFoundException."""
        self.provider.authenticate()
        with self.assertRaises(FileNotFoundException):
            self.provider.upload("/no/such/file.txt", "/")

    def test_download(self):
        """Downloaded file should exist at the local destination."""
        self.provider.authenticate()
        tmp = _make_temp_file("download me")
        try:
            cf = self.provider.upload(tmp, "/")
            dest_dir = tempfile.mkdtemp()
            saved = self.provider.download(cf.file_id, dest_dir)
            self.assertTrue(os.path.isfile(saved))
            shutil.rmtree(dest_dir)
        finally:
            os.unlink(tmp)

    def test_delete(self):
        """Deleted files should no longer appear in list_files()."""
        self.provider.authenticate()
        tmp = _make_temp_file("delete me")
        try:
            cf = self.provider.upload(tmp, "/")
            self.provider.delete(cf.file_id)
            files = self.provider.list_files("/")
            names = [f.name for f in files]
            self.assertNotIn(cf.name, names)
        finally:
            os.unlink(tmp)

    def test_get_quota(self):
        """get_quota() should return a dict with 'used', 'total', 'free'."""
        self.provider.authenticate()
        q = self.provider.get_quota()
        for key in ["used", "total", "free"]:
            self.assertIn(key, q)

    def test_require_auth_raises(self):
        """Operations without authentication should raise AuthenticationException."""
        with self.assertRaises(AuthenticationException):
            self.provider.list_files("/")


# ---------------------------------------------------------------------------
# Test: OneDriveProvider
# ---------------------------------------------------------------------------

class TestOneDriveProvider(unittest.TestCase):
    """Tests for the simulated Microsoft OneDrive provider."""

    def setUp(self):
        self._tmp_root = tempfile.mkdtemp(prefix="test_onedrive_")
        self.provider = OneDriveProvider(
            credentials={"client_id": "id", "client_secret": "secret"},
            storage_root=self._tmp_root,
        )

    def tearDown(self):
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_authenticate_success(self):
        """authenticate() should return True with complete credentials."""
        self.assertTrue(self.provider.authenticate())

    def test_authenticate_missing_credentials(self):
        """authenticate() should raise AuthenticationException without creds."""
        bad = OneDriveProvider(credentials={}, storage_root=self._tmp_root)
        with self.assertRaises(AuthenticationException):
            bad.authenticate()

    def test_upload_and_list(self):
        """Uploaded file should be listed on the provider."""
        self.provider.authenticate()
        tmp = _make_temp_file("hello onedrive")
        try:
            cf = self.provider.upload(tmp, "/")
            names = [f.name for f in self.provider.list_files("/")]
            self.assertIn(cf.name, names)
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Test: TransferEngine
# ---------------------------------------------------------------------------

class TestTransferEngine(unittest.TestCase):
    """Tests for the cross-provider transfer engine."""

    def setUp(self):
        self._google_root   = tempfile.mkdtemp(prefix="test_g_")
        self._onedrive_root = tempfile.mkdtemp(prefix="test_od_")
        self._engine_temp   = tempfile.mkdtemp(prefix="test_eng_")

        self.google = GoogleDriveProvider(
            {"api_key": "key"}, self._google_root)
        self.onedrive = OneDriveProvider(
            {"client_id": "id", "client_secret": "s"}, self._onedrive_root)
        self.google.authenticate()
        self.onedrive.authenticate()
        self.engine = TransferEngine(temp_dir=self._engine_temp)

    def tearDown(self):
        for d in [self._google_root, self._onedrive_root, self._engine_temp]:
            shutil.rmtree(d, ignore_errors=True)

    def _upload_test_file(self, content: str = "transfer test") -> CloudFile:
        """Helper: upload a temp file to Google and return the CloudFile."""
        tmp = _make_temp_file(content)
        cf  = self.google.upload(tmp, "/")
        os.unlink(tmp)
        return cf

    def test_copy_success(self):
        """copy() should report success and file should appear on destination."""
        cf = self._upload_test_file()
        record = self.engine.copy(self.google, self.onedrive, cf.file_id, "/")
        self.assertEqual(record.status, "success")
        # Original should still exist on Google
        google_files = [f.name for f in self.google.list_files("/")]
        self.assertIn(cf.name, google_files)

    def test_move_deletes_source(self):
        """move() should remove the file from the source provider."""
        cf = self._upload_test_file("move me")
        self.engine.move(self.google, self.onedrive, cf.file_id, "/")
        google_files = [f.name for f in self.google.list_files("/")]
        self.assertNotIn(cf.name, google_files)

    def test_copy_bad_id_fails(self):
        """copy() with a nonexistent file_id should produce a failed record."""
        record = self.engine.copy(
            self.google, self.onedrive, "nonexistentid123", "/")
        self.assertEqual(record.status, "failed")

    def test_history_accumulates(self):
        """Each transfer should add an entry to the history."""
        initial = len(self.engine.get_history())
        cf = self._upload_test_file()
        self.engine.copy(self.google, self.onedrive, cf.file_id, "/")
        self.assertEqual(len(self.engine.get_history()), initial + 1)


# ---------------------------------------------------------------------------
# Test: Database
# ---------------------------------------------------------------------------

class TestDatabase(unittest.TestCase):
    """Tests for the SQLite database layer."""

    def setUp(self):
        self._db_path = tempfile.mktemp(suffix=".db")
        self.db = Database(self._db_path)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def _make_cloud_file(self, name: str = "test.txt") -> CloudFile:
        return CloudFile(
            file_id=f"id-{name}",
            name=name,
            size=1024,
            mime_type="text/plain",
            provider="Google Drive",
            path="/",
        )

    def test_save_and_retrieve_file(self):
        """Saved CloudFile should be retrievable from the database."""
        cf = self._make_cloud_file("hello.txt")
        self.db.save_file(cf)
        files = self.db.get_files()
        names = [f["name"] for f in files]
        self.assertIn("hello.txt", names)

    def test_get_files_filtered_by_provider(self):
        """get_files(provider=...) should only return matching provider records."""
        self.db.save_file(self._make_cloud_file("a.txt"))
        files = self.db.get_files(provider="Google Drive")
        for f in files:
            self.assertEqual(f["provider"], "Google Drive")

    def test_delete_file_record(self):
        """delete_file_record() should remove the file from the database."""
        cf = self._make_cloud_file("delete.txt")
        self.db.save_file(cf)
        deleted = self.db.delete_file_record(cf.file_id)
        self.assertTrue(deleted)
        files = [f["name"] for f in self.db.get_files()]
        self.assertNotIn("delete.txt", files)

    def test_save_and_retrieve_transfer(self):
        """Saved TransferRecord should appear in transfer history."""
        rec = TransferRecord(
            operation="copy",
            file_name="test.txt",
            source="Google Drive",
            destination="Microsoft OneDrive",
            status="success",
            duration_secs=0.5,
        )
        self.db.save_transfer(rec)
        history = self.db.get_transfer_history()
        self.assertGreater(len(history), 0)
        self.assertEqual(history[0]["file_name"], "test.txt")

    def test_stats_counts(self):
        """Stats should correctly count files and transfers."""
        self.db.save_file(self._make_cloud_file("x.txt"))
        self.db.save_file(self._make_cloud_file("y.txt"))
        stats = self.db.get_stats()
        self.assertGreaterEqual(stats["total_files"], 2)


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
