"""Private, non-overwriting export bundles shared by reports, images and readers."""
import os
from pathlib import Path
from . import runs
from .contracts import digest, encode, require, HumanWillError


def destination(value, *, restricted=False):
    path = Path(value).expanduser().absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'unsafe_path', 'Export paths cannot contain symlinks.')
    path = path.resolve()
    # Question-content release is independent of report/code release. Public paths
    # are never implied by export authorization: restricted readers stay in .local.
    if restricted:
        require('.local' in path.parts, 'private_destination', 'Question exports require a private .local directory.')
    require(not path.exists(), 'already_exists', 'Export destination already exists; choose a new directory.')
    # Avoid appending exports inside a run: they would invalidate its state hash.
    for parent in path.parents:
        require(not ((parent / 'attempts').is_dir() and (parent / 'plan.json').is_file()),
                'unsafe_destination', 'Export outside the immutable run directory.')
    return path


def publish(path, files, *, kind, metadata):
    """Bytes are fully prepared before claiming a destination; no partial rendering."""
    require(files and all(isinstance(v, bytes) for v in files.values()), message='Expected export bytes.')
    for name in files:
        require(Path(name).name == name and name not in ('.', '..', 'manifest.json'), message='Unsafe export filename.')
    manifest = {'format': 'humanwill.export/1', 'kind': kind, **metadata,
                'files': {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in sorted(files.items())}}
    runs.directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        raise HumanWillError('already_exists', 'Export destination already exists.') from None
    for name, raw in {**files, 'manifest.json': encode(manifest)}.items():
        fd = os.open(path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    return {'format': 'humanwill.export-result/1', 'kind': kind, 'directory': str(path),
            'manifest': str(path / 'manifest.json'), 'files': [str(path / n) for n in sorted(files)], **metadata}
