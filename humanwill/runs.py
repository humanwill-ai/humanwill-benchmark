"""Private, exclusive run directories and atomic, non-overwriting JSON records."""
import os
from pathlib import Path
import uuid

from .contracts import HumanWillError, decode, encode, identifier, require


def directory(path: Path):
    if path.exists():
        require(path.is_dir() and not path.is_symlink(), "unsafe_path", "Unsafe run directory.")
        return
    directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        require(path.is_dir() and not path.is_symlink(), "unsafe_path", "Unsafe run directory.")


def write(path: Path, value):
    """Publish complete bytes atomically; a prior record is never replaced."""
    raw = encode(value)
    temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        if os.name == "posix":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except FileExistsError as exc:
        raise HumanWillError("already_exists", "Record already exists; refusing overwrite.") from exc
    finally:
        temporary.unlink(missing_ok=True)


def read(path: Path):
    require(not path.is_symlink(), "unsafe_path", "Run records cannot be symlinks.")
    try:
        return decode(path.read_bytes())
    except OSError as exc:
        raise HumanWillError("run_unavailable", "Run record is unavailable.") from exc


def root(workspace, run_id):
    identifier(run_id)
    path = Path(workspace).expanduser().resolve() / run_id
    require(not path.is_symlink(), "unsafe_path", "Run cannot be a symlink.")
    return path


def create(workspace, run_id):
    path = root(workspace, run_id)
    directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise HumanWillError("run_exists", "Run ID already exists; choose a new ID.") from exc
    (path / "attempts").mkdir(mode=0o700)
    return path
