"""Account-only credentials: Windows Credential Manager or private atomic POSIX file."""

import ctypes
import hashlib
import json
import os
import stat
import tempfile
from ctypes import wintypes
from pathlib import Path


class StorageError(Exception):
    pass


class CredentialStore:
    def __init__(self, origin):
        self.target = "Wizard/account/" + hashlib.sha256(origin.encode()).hexdigest()
        self.path = (
            Path.home()
            / ".config"
            / "wizard"
            / "accounts"
            / (self.target.rsplit("/", 1)[1] + ".json")
        )

    def _windows(self, value=None):
        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(Credential)),
        ]
        api.CredReadW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        if value is not None:
            raw = json.dumps(value).encode()
            blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
            credential = Credential(
                Type=1,
                TargetName=self.target,
                CredentialBlobSize=len(raw),
                CredentialBlob=blob,
                Persist=2,
                UserName="Wizard account",
            )
            if not api.CredWriteW(ctypes.byref(credential), 0):
                raise StorageError(
                    "Windows Credential Manager write failed (Windows error "
                    + str(ctypes.get_last_error())
                    + ")"
                )
            return value
        pointer = ctypes.POINTER(Credential)()
        if not api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            raise StorageError(
                "Windows Credential Manager could not read the account credential"
            )
        try:
            raw = ctypes.string_at(
                pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
            )
            return json.loads(raw)
        finally:
            api.CredFree(pointer)

    def _directory(self):
        parent = self.path.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        # Reject symlinks at every existing level. Fail closed on shared storage.
        for item in [parent, *parent.parents]:
            if item.is_symlink():
                raise StorageError("Account credential directory cannot use symlinks")
            home = Path.home()
            if item == home or home in item.parents:
                info = item.stat()
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
                    raise StorageError(
                        "Account credential path must be user-owned and not writable by other users"
                    )
        info = parent.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise StorageError(
                "Account credential directory must be owned by this user with mode 0700"
            )
        return parent

    def load(self):
        try:
            if os.name == "nt":
                return self._windows()
            self._directory()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(self.path, flags)
            except FileNotFoundError:
                return None
            with os.fdopen(descriptor) as stream:
                info = os.fstat(stream.fileno())
                if (
                    info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077
                    or not stat.S_ISREG(info.st_mode)
                ):
                    raise StorageError("Account credential file must be private (0600)")
                return json.load(stream)
        except StorageError:
            raise
        except Exception:  # noqa: BLE001 -- sanitize platform and filesystem exceptions
            raise StorageError("Account credential storage is unavailable") from None

    def save(self, value):
        try:
            if os.name == "nt":
                self._windows(value)
                return
            parent = self._directory()
            descriptor, temporary = tempfile.mkstemp(prefix=".account-", dir=parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    json.dump(value, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                # The atomic replacement already succeeded. A directory fsync failure
                # must not report that the old credential is still installed.
                try:
                    directory = os.open(
                        parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    )
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except OSError:
                    pass  # Some filesystems lack directory fsync; file data was synced.
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except Exception:  # noqa: BLE001 -- sanitize platform and filesystem exceptions
            raise StorageError(
                "Account credential could not be saved; existing credentials were not replaced before the atomic write"
            ) from None
