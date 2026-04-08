"""
cloud_provider.py
-----------------
Core OOP abstraction layer for multi-cloud file management.
Defines the base CloudProvider class and concrete implementations
for Google Drive and Microsoft OneDrive (simulated for prototype).

Course concepts used: Object-Oriented Programming, Exception Handling
"""

import os
import shutil
import hashlib
from datetime import datetime
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class CloudException(Exception):
    """Base exception for all cloud-related errors."""

    def __init__(self, message: str, provider: str = "Unknown"):
        self.message = message
        self.provider = provider
        super().__init__(self.message)

    def __str__(self):
        return f"[{self.provider}] {self.message}"


class FileNotFoundException(CloudException):
    """Raised when a requested file does not exist on the provider."""
    pass


class AuthenticationException(CloudException):
    """Raised when cloud provider authentication fails."""
    pass


class QuotaExceededException(CloudException):
    """Raised when storage quota is exceeded."""
    pass


# ---------------------------------------------------------------------------
# CloudFile: represents a file/folder metadata object
# ---------------------------------------------------------------------------

class CloudFile:
    """
    Represents metadata for a file stored on a cloud provider.

    Attributes:
        file_id   -- unique identifier on the cloud provider
        name      -- display name of the file
        size      -- size in bytes
        mime_type -- MIME type string
        provider  -- name of the cloud provider
        created   -- creation datetime
        modified  -- last modification datetime
        path      -- virtual path within the provider
    """

    def __init__(self, file_id: str, name: str, size: int,
                 mime_type: str, provider: str,
                 created: datetime = None, modified: datetime = None,
                 path: str = "/"):
        self.file_id = file_id
        self.name = name
        self.size = size
        self.mime_type = mime_type
        self.provider = provider
        self.created = created or datetime.now()
        self.modified = modified or datetime.now()
        self.path = path

    def __str__(self):
        size_str = self._format_size(self.size)
        return (f"CloudFile(name={self.name!r}, provider={self.provider!r}, "
                f"size={size_str}, path={self.path!r})")

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Convert raw bytes to a human-readable size string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def to_dict(self) -> dict:
        """Serialise the CloudFile to a plain dict (for JSON responses)."""
        return {
            "file_id":   self.file_id,
            "name":      self.name,
            "size":      self.size,
            "mime_type": self.mime_type,
            "provider":  self.provider,
            "created":   self.created.isoformat(),
            "modified":  self.modified.isoformat(),
            "path":      self.path,
        }


# ---------------------------------------------------------------------------
# Abstract base: CloudProvider
# ---------------------------------------------------------------------------

class CloudProvider(ABC):
    """
    Abstract base class that every cloud provider must implement.
    Enforces a common interface for upload, download, list, delete,
    and quota operations.
    """

    def __init__(self, name: str, credentials: dict):
        """
        Initialise a provider.

        :param name:        Human-readable provider name (e.g. 'Google Drive')
        :param credentials: Dict of auth tokens / keys for this provider
        """
        self.name = name
        self._credentials = credentials
        self._authenticated = False

    # -- Authentication ------------------------------------------------------

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with the cloud provider using stored credentials.
        Must be called before any file operations.
        :return: True if authentication succeeded, False otherwise
        """
        pass

    # -- File operations -----------------------------------------------------

    @abstractmethod
    def list_files(self, path: str = "/") -> list:
        """
        List all files at the given path on the provider.
        :param path: Virtual path to list
        :return: List of CloudFile objects
        """
        pass

    @abstractmethod
    def upload(self, local_path: str, remote_path: str = "/") -> CloudFile:
        """
        Upload a local file to the provider.
        :param local_path:  Absolute path of the local file
        :param remote_path: Destination path on the provider
        :return: CloudFile metadata object for the uploaded file
        """
        pass

    @abstractmethod
    def download(self, file_id: str, local_path: str) -> str:
        """
        Download a file from the provider to a local path.
        :param file_id:    Provider-side unique file identifier
        :param local_path: Directory or full path to save to locally
        :return: Absolute path of the saved file
        """
        pass

    @abstractmethod
    def delete(self, file_id: str) -> bool:
        """
        Permanently delete a file from the provider.
        :param file_id: Provider-side unique file identifier
        :return: True if deletion succeeded
        """
        pass

    @abstractmethod
    def get_quota(self) -> dict:
        """
        Return storage quota information.
        :return: Dict with keys 'used', 'total', 'free' (all in bytes)
        """
        pass

    # -- Shared utility methods (not abstract) --------------------------------

    def _require_auth(self):
        """Helper: raise AuthenticationException if not yet authenticated."""
        if not self._authenticated:
            raise AuthenticationException(
                "Not authenticated. Call authenticate() first.", self.name)

    @staticmethod
    def _compute_checksum(file_path: str) -> str:
        """Compute MD5 checksum of a local file for integrity verification."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _generate_id(name: str) -> str:
        """
        Generate a stable, deterministic pseudo-ID from the file name.
        Uses only the name (not the timestamp) so that the same file
        always receives the same ID within a simulation session.
        """
        return hashlib.sha1(name.encode()).hexdigest()[:16]

    def __str__(self):
        status = "authenticated" if self._authenticated else "not authenticated"
        return f"{self.name} ({status})"


# ---------------------------------------------------------------------------
# Simulated Google Drive provider
# ---------------------------------------------------------------------------

class GoogleDriveProvider(CloudProvider):
    """
    Simulated Google Drive provider for prototype purposes.
    Files are stored locally under a designated simulation directory.
    A small sidecar file (<name>.mcid) persists each file's stable cloud ID
    so that download/delete lookups remain consistent across calls.
    """

    PROVIDER_NAME = "Google Drive"
    # Total simulated storage: 15 GB (Google's free tier)
    SIMULATED_QUOTA_TOTAL = 15 * 1024 ** 3

    def __init__(self, credentials: dict, storage_root: str = "sim_google"):
        """
        :param credentials:  Dict containing at least 'api_key'
        :param storage_root: Local directory that simulates Google Drive
        """
        super().__init__(self.PROVIDER_NAME, credentials)
        self._storage_root = os.path.abspath(storage_root)
        os.makedirs(self._storage_root, exist_ok=True)

    # -- Internal ID-persistence helpers ------------------------------------

    @staticmethod
    def _id_file(data_path: str) -> str:
        """Return the sidecar path that stores a file's stable cloud ID."""
        return data_path + ".mcid"

    def _save_id(self, data_path: str, file_id: str):
        """Write the cloud ID into a sidecar file next to the data file."""
        with open(self._id_file(data_path), "w") as fh:
            fh.write(file_id)

    def _load_id(self, data_path: str) -> str:
        """
        Read the persisted cloud ID for a data file.
        :return: ID string, or empty string if the sidecar does not exist.
        """
        id_path = self._id_file(data_path)
        if not os.path.exists(id_path):
            return ""
        with open(id_path) as fh:
            return fh.read().strip()

    # -- CloudProvider interface --------------------------------------------

    def authenticate(self) -> bool:
        """
        Simulate OAuth2 authentication by checking for 'api_key' in credentials.
        In a real implementation this would initiate the OAuth flow.
        """
        if "api_key" not in self._credentials or not self._credentials["api_key"]:
            raise AuthenticationException(
                "Missing 'api_key' in credentials.", self.name)
        self._authenticated = True
        print(f"[{self.name}] Authenticated successfully.")
        return True

    def list_files(self, path: str = "/") -> list:
        """List files stored in the simulated Google Drive directory."""
        self._require_auth()
        files = []
        target = os.path.join(self._storage_root, path.lstrip("/"))
        if not os.path.exists(target):
            return files
        for entry in os.scandir(target):
            # Skip the sidecar ID files — they are internal metadata
            if entry.name.endswith(".mcid"):
                continue
            stat = entry.stat()
            files.append(CloudFile(
                file_id=self._load_id(entry.path) or self._generate_id(entry.name),
                name=entry.name,
                size=stat.st_size,
                mime_type="application/octet-stream",
                provider=self.name,
                created=datetime.fromtimestamp(stat.st_ctime),
                modified=datetime.fromtimestamp(stat.st_mtime),
                path=path,
            ))
        return files

    def upload(self, local_path: str, remote_path: str = "/") -> CloudFile:
        """
        Copy a local file into the simulated Google Drive storage and
        persist a stable cloud ID in a companion sidecar file.
        """
        self._require_auth()
        if not os.path.isfile(local_path):
            raise FileNotFoundException(
                f"Local file not found: {local_path}", self.name)
        dest_dir = os.path.join(self._storage_root, remote_path.lstrip("/"))
        os.makedirs(dest_dir, exist_ok=True)
        filename  = os.path.basename(local_path)
        dest_path = os.path.join(dest_dir, filename)
        shutil.copy2(local_path, dest_path)
        # Generate and persist a stable ID alongside the data file
        file_id = self._generate_id(filename)
        self._save_id(dest_path, file_id)
        stat = os.stat(dest_path)
        print(f"[{self.name}] Uploaded '{filename}' → {remote_path}")
        return CloudFile(
            file_id=file_id,
            name=filename,
            size=stat.st_size,
            mime_type="application/octet-stream",
            provider=self.name,
            created=datetime.fromtimestamp(stat.st_ctime),
            modified=datetime.fromtimestamp(stat.st_mtime),
            path=remote_path,
        )

    def download(self, file_id: str, local_path: str) -> str:
        """
        Locate a file by reading its persisted sidecar ID, then copy it
        to the requested local directory.
        """
        self._require_auth()
        for root, _, files in os.walk(self._storage_root):
            for fname in files:
                if fname.endswith(".mcid"):
                    continue
                full = os.path.join(root, fname)
                if self._load_id(full) == file_id:
                    os.makedirs(local_path, exist_ok=True)
                    dest = os.path.join(local_path, fname)
                    shutil.copy2(full, dest)
                    print(f"[{self.name}] Downloaded '{fname}' → {dest}")
                    return dest
        raise FileNotFoundException(
            f"File with id '{file_id}' not found.", self.name)

    def delete(self, file_id: str) -> bool:
        """
        Remove a data file and its sidecar from simulated storage
        by matching the persisted cloud ID.
        """
        self._require_auth()
        for root, _, files in os.walk(self._storage_root):
            for fname in files:
                if fname.endswith(".mcid"):
                    continue
                full = os.path.join(root, fname)
                if self._load_id(full) == file_id:
                    os.remove(full)
                    id_path = self._id_file(full)
                    if os.path.exists(id_path):
                        os.remove(id_path)
                    print(f"[{self.name}] Deleted '{fname}'.")
                    return True
        raise FileNotFoundException(
            f"File with id '{file_id}' not found.", self.name)

    def get_quota(self) -> dict:
        """Calculate simulated quota from actual directory size."""
        self._require_auth()
        used = 0
        for entry in os.scandir(self._storage_root):
            if entry.is_file() and not entry.name.endswith(".mcid"):
                used += entry.stat().st_size
        return {
            "used":  used,
            "total": self.SIMULATED_QUOTA_TOTAL,
            "free":  self.SIMULATED_QUOTA_TOTAL - used,
        }


# ---------------------------------------------------------------------------
# Simulated Microsoft OneDrive provider
# ---------------------------------------------------------------------------

class OneDriveProvider(CloudProvider):
    """
    Simulated Microsoft OneDrive provider for prototype purposes.
    Mirrors the GoogleDriveProvider design — same sidecar ID mechanism,
    separate storage root, different simulated quota.
    """

    PROVIDER_NAME = "Microsoft OneDrive"
    # Total simulated storage: 5 GB (Microsoft's free tier)
    SIMULATED_QUOTA_TOTAL = 5 * 1024 ** 3

    def __init__(self, credentials: dict, storage_root: str = "sim_onedrive"):
        """
        :param credentials:  Dict containing at least 'client_id' and 'client_secret'
        :param storage_root: Local directory that simulates OneDrive
        """
        super().__init__(self.PROVIDER_NAME, credentials)
        self._storage_root = os.path.abspath(storage_root)
        os.makedirs(self._storage_root, exist_ok=True)

    @staticmethod
    def _id_file(data_path: str) -> str:
        return data_path + ".mcid"

    def _save_id(self, data_path: str, file_id: str):
        with open(self._id_file(data_path), "w") as fh:
            fh.write(file_id)

    def _load_id(self, data_path: str) -> str:
        id_path = self._id_file(data_path)
        if not os.path.exists(id_path):
            return ""
        with open(id_path) as fh:
            return fh.read().strip()

    def authenticate(self) -> bool:
        """
        Simulate Microsoft Identity Platform (MSAL) authentication.
        Requires 'client_id' and 'client_secret' in the credentials dict.
        """
        required = {"client_id", "client_secret"}
        if not required.issubset(self._credentials):
            raise AuthenticationException(
                f"Credentials must contain: {required}", self.name)
        self._authenticated = True
        print(f"[{self.name}] Authenticated successfully.")
        return True

    def list_files(self, path: str = "/") -> list:
        """List files stored in the simulated OneDrive directory."""
        self._require_auth()
        files = []
        target = os.path.join(self._storage_root, path.lstrip("/"))
        if not os.path.exists(target):
            return files
        for entry in os.scandir(target):
            if entry.name.endswith(".mcid"):
                continue
            stat = entry.stat()
            files.append(CloudFile(
                file_id=self._load_id(entry.path) or self._generate_id(entry.name),
                name=entry.name,
                size=stat.st_size,
                mime_type="application/octet-stream",
                provider=self.name,
                created=datetime.fromtimestamp(stat.st_ctime),
                modified=datetime.fromtimestamp(stat.st_mtime),
                path=path,
            ))
        return files

    def upload(self, local_path: str, remote_path: str = "/") -> CloudFile:
        """Upload (copy) a local file into the simulated OneDrive storage."""
        self._require_auth()
        if not os.path.isfile(local_path):
            raise FileNotFoundException(
                f"Local file not found: {local_path}", self.name)
        dest_dir = os.path.join(self._storage_root, remote_path.lstrip("/"))
        os.makedirs(dest_dir, exist_ok=True)
        filename  = os.path.basename(local_path)
        dest_path = os.path.join(dest_dir, filename)
        shutil.copy2(local_path, dest_path)
        file_id = self._generate_id(filename)
        self._save_id(dest_path, file_id)
        stat = os.stat(dest_path)
        print(f"[{self.name}] Uploaded '{filename}' → {remote_path}")
        return CloudFile(
            file_id=file_id,
            name=filename,
            size=stat.st_size,
            mime_type="application/octet-stream",
            provider=self.name,
            modified=datetime.fromtimestamp(stat.st_mtime),
            path=remote_path,
        )

    def download(self, file_id: str, local_path: str) -> str:
        """Download a file from simulated OneDrive to local path."""
        self._require_auth()
        for root, _, files in os.walk(self._storage_root):
            for fname in files:
                if fname.endswith(".mcid"):
                    continue
                full = os.path.join(root, fname)
                if self._load_id(full) == file_id:
                    os.makedirs(local_path, exist_ok=True)
                    dest = os.path.join(local_path, fname)
                    shutil.copy2(full, dest)
                    print(f"[{self.name}] Downloaded '{fname}' → {dest}")
                    return dest
        raise FileNotFoundException(
            f"File with id '{file_id}' not found.", self.name)

    def delete(self, file_id: str) -> bool:
        """Delete a file from simulated OneDrive by matching persisted ID."""
        self._require_auth()
        for root, _, files in os.walk(self._storage_root):
            for fname in files:
                if fname.endswith(".mcid"):
                    continue
                full = os.path.join(root, fname)
                if self._load_id(full) == file_id:
                    os.remove(full)
                    id_path = self._id_file(full)
                    if os.path.exists(id_path):
                        os.remove(id_path)
                    print(f"[{self.name}] Deleted '{fname}'.")
                    return True
        raise FileNotFoundException(
            f"File with id '{file_id}' not found.", self.name)

    def get_quota(self) -> dict:
        """Return simulated OneDrive quota information."""
        self._require_auth()
        used = 0
        for entry in os.scandir(self._storage_root):
            if entry.is_file() and not entry.name.endswith(".mcid"):
                used += entry.stat().st_size
        return {
            "used":  used,
            "total": self.SIMULATED_QUOTA_TOTAL,
            "free":  self.SIMULATED_QUOTA_TOTAL - used,
        }


# ---------------------------------------------------------------------------
# ProviderRegistry: central registry / factory for providers
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """
    Central registry that holds configured CloudProvider instances.
    Allows the rest of the application to resolve providers by name
    without hard-coding dependencies.
    """

    _providers: dict = {}

    @classmethod
    def register(cls, provider: CloudProvider):
        """
        Register a provider instance under its name.
        :param provider: A CloudProvider subclass instance
        """
        cls._providers[provider.name] = provider
        print(f"[Registry] Registered provider: '{provider.name}'")

    @classmethod
    def get(cls, name: str) -> CloudProvider:
        """
        Retrieve a registered provider by name.
        :param name: Provider name (e.g. 'Google Drive')
        :return: CloudProvider instance
        :raises KeyError: if provider is not registered
        """
        if name not in cls._providers:
            raise KeyError(f"Provider '{name}' not found in registry. "
                           f"Available: {list(cls._providers.keys())}")
        return cls._providers[name]

    @classmethod
    def all_providers(cls) -> list:
        """Return a list of all registered providers."""
        return list(cls._providers.values())

    @classmethod
    def provider_names(cls) -> list:
        """Return the names of all registered providers."""
        return list(cls._providers.keys())


if __name__ == "__main__":
    # Quick smoke-test: register both providers and list files
    google = GoogleDriveProvider(
        credentials={"api_key": "demo-key"},
        storage_root="sim_google",
    )
    onedrive = OneDriveProvider(
        credentials={"client_id": "demo-id", "client_secret": "demo-secret"},
        storage_root="sim_onedrive",
    )

    ProviderRegistry.register(google)
    ProviderRegistry.register(onedrive)

    for provider in ProviderRegistry.all_providers():
        provider.authenticate()
        quota = provider.get_quota()
        used_mb  = quota["used"]  / 1024 ** 2
        total_gb = quota["total"] / 1024 ** 3
        print(f"{provider.name}: {used_mb:.1f} MB used / {total_gb:.0f} GB total")
