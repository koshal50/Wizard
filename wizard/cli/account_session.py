"""Cross-process login/logout ordering. The generation file contains no secrets."""

import os
import threading
from contextlib import contextmanager
from uuid import uuid4

from wizard.cli.account_storage import StorageError

_lock = threading.RLock()


@contextmanager
def session_guard(store):
    """Hold across local persistence only, never across a network operation."""
    # In-memory test stores have no filesystem; production always has a path.
    path = getattr(store, "path", None)
    with _lock:
        if path is None:
            yield None
            return
        descriptor = None
        try:
            parent = path.parent
            if os.name == "nt":
                parent.mkdir(parents=True, exist_ok=True)
            else:
                store._directory()
            target = path.with_suffix(".session")
            if target.is_symlink():
                raise StorageError("Account session file cannot be a symlink")
            descriptor = os.open(
                target, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
            with os.fdopen(descriptor, "r+b", buffering=0) as stream:
                descriptor = None
                # Lock a fixed byte; the remainder is a random generation identifier.
                if os.name == "nt":
                    import msvcrt

                    if os.fstat(stream.fileno()).st_size == 0:
                        stream.write(b" ")
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield stream
                finally:
                    if os.name == "nt":
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except StorageError:
            raise
        except OSError:
            raise StorageError("Account session storage is unavailable") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)


_generations = {}


def generation(store, stream, advance=False):
    if stream is None:
        key = id(store)
        if advance:
            _generations[key] = uuid4().hex
        return _generations.get(key, "")
    if advance:
        stream.seek(0)
        stream.write((" " + uuid4().hex).encode("ascii"))
        stream.truncate()
        os.fsync(stream.fileno())
    stream.seek(1)
    return stream.read().decode("ascii")


def current_generation(store):
    with session_guard(store) as stream:
        return generation(store, stream)
