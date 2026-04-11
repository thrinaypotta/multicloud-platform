"""
cloud_provider.py

Instead of talking to real Google/Microsoft servers, we fake it
by using local folders on our PC — sim_google and sim_onedrive.

"""

import os, shutil, hashlib
from abc import ABC, abstractmethod
from datetime import datetime


class CloudException(Exception):
    def __init__(self, message: str, provider: str = "Unknown"):
        self.message, self.provider = message, provider
        super().__init__(message)
    def __str__(self):
        return f"[{self.provider}] {self.message}"

class FileNotFoundException(CloudException): pass   # file doesn't exist
class AuthenticationException(CloudException): pass # wrong password / key


class CloudFile:
    """A note that describes a file on a cloud provider."""

    def __init__(self, file_id: str, name: str, size: int,
                 provider: str, path: str = "/", modified: datetime = None):
        self.file_id  = file_id   # unique ID code for this file
        self.name     = name      # filename like "homework.pdf"
        self.size     = size      # size in bytes
        self.provider = provider  # which cloud it's on
        self.path     = path      # which folder inside that cloud
        self.modified = modified or datetime.now()

    def __str__(self):
        return f"CloudFile(name={self.name!r}, size={self._fmt(self.size)}, provider={self.provider!r})"

    @staticmethod
    def _fmt(b: int) -> str:
        """Turns 1048576 into something readable like '1.0 MB'."""
        for u in ["B", "KB", "MB", "GB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} TB"

    def to_dict(self) -> dict:
        return {"file_id": self.file_id, "name": self.name, "size": self.size,
                "provider": self.provider, "path": self.path,
                "modified": self.modified.isoformat()}


class CloudProvider(ABC):
    """The rulebook every cloud provider will follow."""
    """For future development to push login creds."""

    def __init__(self, name: str, credentials: dict):
        self.name   = name
        self._creds = credentials
        self._auth  = False        # not logged in yet

    @abstractmethod
    def authenticate(self) -> bool: pass

    @abstractmethod
    def list_files(self, path: str = "/") -> list: pass

    @abstractmethod
    def upload(self, local_path: str, remote_path: str = "/") -> CloudFile: pass

    @abstractmethod
    def download(self, file_id: str, local_path: str) -> str: pass

    @abstractmethod
    def delete(self, file_id: str) -> bool: pass

    @abstractmethod
    def get_quota(self) -> dict: pass

    def _require_auth(self):
        # bouncer check — not logged in means you can't do anything
        if not self._auth:
            raise AuthenticationException("Call authenticate() first.", self.name)

    @staticmethod
    def _make_id(name: str) -> str:
        """Same filename always gives the same ID — like a fingerprint."""
        return hashlib.sha1(name.encode()).hexdigest()[:16]

    def __str__(self):
        return f"{self.name} ({'authenticated' if self._auth else 'not authenticated'})"


class SimulatedProvider(CloudProvider):
    """
    Pretends to be a cloud by storing files in a local folder.
    Every file gets a tiny .mcid companion file storing its ID,
    so we can find it again later by ID without guessing.
    """

    QUOTA = 0   # each subclass sets how much fake storage it has

    def __init__(self, name: str, credentials: dict, storage_root: str):
        super().__init__(name, credentials)
        self._root = os.path.abspath(storage_root)
        os.makedirs(self._root, exist_ok=True)

    def _id_path(self, p: str) -> str: return p + ".mcid"

    def _save_id(self, p: str, fid: str):
        with open(self._id_path(p), "w") as f: f.write(fid)

    def _read_id(self, p: str) -> str:
        ip = self._id_path(p)
        if not os.path.exists(ip): return ""
        with open(ip) as f: return f.read().strip()

    def list_files(self, path: str = "/") -> list:
        self._require_auth()
        target = os.path.join(self._root, path.lstrip("/"))
        if not os.path.exists(target): return []
        # scan the folder, skip .mcid files, build a CloudFile for each real file
        return [
            CloudFile(
                file_id  = self._read_id(e.path) or self._make_id(e.name),
                name     = e.name,
                size     = e.stat().st_size,
                provider = self.name,
                path     = path,
                modified = datetime.fromtimestamp(e.stat().st_mtime)
            )
            for e in os.scandir(target) if not e.name.endswith(".mcid")
        ]

    def upload(self, local_path: str, remote_path: str = "/") -> CloudFile:
        self._require_auth()
        if not os.path.isfile(local_path):
            raise FileNotFoundException(f"Not found: {local_path}", self.name)
        dest_dir = os.path.join(self._root, remote_path.lstrip("/"))
        os.makedirs(dest_dir, exist_ok=True)
        name = os.path.basename(local_path)
        dest = os.path.join(dest_dir, name)
        shutil.copy2(local_path, dest)
        fid = self._make_id(name)
        self._save_id(dest, fid)   # write ID to the .mcid companion file
        print(f"[{self.name}] Uploaded '{name}' → {remote_path}")
        return CloudFile(fid, name, os.path.getsize(dest), self.name, remote_path,
                         datetime.fromtimestamp(os.path.getmtime(dest)))

    def download(self, file_id: str, local_path: str) -> str:
        self._require_auth()
        for root, _, files in os.walk(self._root):
            for fname in files:
                if fname.endswith(".mcid"): continue
                full = os.path.join(root, fname)
                if self._read_id(full) == file_id:   # found the right file
                    os.makedirs(local_path, exist_ok=True)
                    dest = os.path.join(local_path, fname)
                    shutil.copy2(full, dest)
                    print(f"[{self.name}] Downloaded '{fname}' → {dest}")
                    return dest
        raise FileNotFoundException(f"ID '{file_id}' not found.", self.name)

    def delete(self, file_id: str) -> bool:
        self._require_auth()
        for root, _, files in os.walk(self._root):
            for fname in files:
                if fname.endswith(".mcid"): continue
                full = os.path.join(root, fname)
                if self._read_id(full) == file_id:
                    os.remove(full)
                    if os.path.exists(self._id_path(full)):
                        os.remove(self._id_path(full))  # delete the .mcid too
                    print(f"[{self.name}] Deleted '{fname}'.")
                    return True
        raise FileNotFoundException(f"ID '{file_id}' not found.", self.name)

    def get_quota(self) -> dict:
        self._require_auth()
        used = sum(e.stat().st_size for e in os.scandir(self._root)
                   if e.is_file() and not e.name.endswith(".mcid"))
        return {"used": used, "total": self.QUOTA, "free": self.QUOTA - used}


class GoogleDriveProvider(SimulatedProvider):
    """Pretends to be Google Drive. Stores files in the sim_google/ folder."""

    QUOTA = 15 * 1024 ** 3  # 15 GB — same as Google's real free storage

    def __init__(self, credentials: dict, storage_root: str = "sim_google"):
        super().__init__("Google Drive", credentials, storage_root)

    def authenticate(self) -> bool:
        if not self._creds.get("api_key"):
            raise AuthenticationException("Missing 'api_key'.", self.name)
        self._auth = True
        print(f"[{self.name}] Authenticated successfully.")
        return True


class OneDriveProvider(SimulatedProvider):
    """Pretends to be Microsoft OneDrive. Stores files in the sim_onedrive/ folder."""

    QUOTA = 5 * 1024 ** 3  # 5 GB — same as Microsoft's real free storage

    def __init__(self, credentials: dict, storage_root: str = "sim_onedrive"):
        super().__init__("Microsoft OneDrive", credentials, storage_root)

    def authenticate(self) -> bool:
        if not {"client_id", "client_secret"}.issubset(self._creds):
            raise AuthenticationException("Missing 'client_id' or 'client_secret'.", self.name)
        self._auth = True
        print(f"[{self.name}] Authenticated successfully.")
        return True


class ProviderRegistry:
    """A phone book that maps provider names to their actual objects."""

    _store: dict = {}  # shared by the entire program

    @classmethod
    def register(cls, p: CloudProvider):
        cls._store[p.name] = p
        print(f"[Registry] Registered: '{p.name}'")

    @classmethod
    def get(cls, name: str) -> CloudProvider:
        if name not in cls._store:
            raise KeyError(f"'{name}' not registered. Available: {list(cls._store)}")
        return cls._store[name]

    @classmethod
    def names(cls) -> list: return list(cls._store.keys())
