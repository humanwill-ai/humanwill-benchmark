"""Local-only release selection, distribution inspection and offline test gate.

No git writes, provider calls, credentials, uploads or publication permissions.
The explicit source inventory is a review boundary, not a licensing decision.
"""
import argparse
from email.parser import BytesParser
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import tomllib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('test_humanwill', 'test_humanwill_execution', 'test_humanwill_sources',
          'test_humanwill_reporting', 'test_humanwill_release', 'test_humanwill_authoring', 'test_humanwill_policies', 'test_humanwill_labels')
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{40,}')


def inventory(root=ROOT):
    names = [n for n in (root/'release/files.txt').read_text().splitlines() if n and not n.startswith('#')]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate source inventory entry')
    for name in names:
        safe_name(name)
    return names


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or str(path) != name:
        raise ValueError('Unsafe archive/inventory path')


def content_check(name, raw):
    if SECRET.search(raw):
        raise ValueError('Potential credential material in selected file: '+name)


def license_config(root=ROOT):
    """Read explicit package licensing; require literal, selected notice paths."""
    path = root/'pyproject.toml'
    if not path.exists(): return None
    project = tomllib.loads(path.read_text()).get('project', {})
    expression = project.get('license')
    notices = project.get('license-files')
    if expression is None and notices is None: return None
    if not isinstance(expression, str) or not expression.strip() or not isinstance(notices, list) or not notices:
        raise ValueError('Incomplete distribution licensing metadata')
    if not all(isinstance(n, str) for n in notices) or len(notices) != len(set(notices)):
        raise ValueError('Invalid or duplicate license files')
    for name in notices:
        safe_name(name)
        if name not in inventory(root):
            raise ValueError('License file is not explicitly selected: '+name)
    return {'expression':expression, 'files':notices}


def license_metadata(raw, licensing):
    metadata = BytesParser().parsebytes(raw)
    if metadata.get_all('License-Expression') != [licensing['expression']]:
        raise ValueError('Distribution license expression differs from source')
    names = metadata.get_all('License-File', [])
    if sorted(names) != sorted(licensing['files']):
        raise ValueError('Distribution license-file metadata differs from source')


def selected(root=ROOT):
    result = {}
    for name in inventory(root):
        path = root/name
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise ValueError('Missing or unsafe selected source: '+name)
        raw = path.read_bytes()
        content_check(name, raw)
        result[name] = raw
    # The public candidate has a standalone front page, not the research history.
    result['README.md'] = result['release/README.md'].replace(b'](../', b'](')
    return result


def stage(destination, root=ROOT):
    raw_path = Path(destination).expanduser().absolute()
    if any(p.is_symlink() for p in (raw_path, *raw_path.parents)):
        raise ValueError('Stage destination cannot contain symlinks')
    path = raw_path.resolve()
    if '.local' not in path.parts:
        raise ValueError('Unapproved release candidates must stay under .local')
    if path.exists():
        raise ValueError('Stage destination already exists')
    licensing = license_config(root)
    files = selected(root)
    path.mkdir(parents=True, mode=0o700)
    for name, raw in files.items():
        target = path/name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with target.open('xb') as stream:
            stream.write(raw)
        target.chmod(0o600)
    manifest = {'format':'humanwill.release-candidate/1', 'publication_authorized':False,
                'license_decision':'selected' if licensing else 'pending',
                'license_expression':licensing['expression'] if licensing else None,
                'files':{n:hashlib.sha256(v).hexdigest() for n,v in sorted(files.items())}}
    target = path/'release-candidate.json'
    target.write_text(json.dumps(manifest, indent=2)+'\n'); target.chmod(0o600)
    return {'directory':str(path), 'files':len(files), 'publication_authorized':False}


def archive(path, root=ROOT):
    """Read member bytes directly: never extract untrusted archive paths."""
    path = Path(path)
    package = {n for n in inventory(root) if n.startswith('humanwill/')}
    source_files = set(inventory(root)) | {'README.md'}
    seen, payloads = set(), {}
    wheel = path.suffix == '.whl'
    licensing = license_config(root)
    if wheel:
        with zipfile.ZipFile(path) as bundle:
            for member in bundle.infolist():
                if member.is_dir(): continue
                name = member.filename; safe_name(name)
                if name in seen or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Duplicate or symlink archive member')
                seen.add(name); payloads[name] = bundle.read(member)
    else:
        with tarfile.open(path, 'r:gz') as bundle:
            roots = set()
            for member in bundle:
                safe_name(member.name.rstrip('/'))
                roots.add(PurePosixPath(member.name).parts[0])
                if member.isdir(): continue
                if not member.isfile(): raise ValueError('Non-file source archive member')
                parts = PurePosixPath(member.name).parts
                if len(parts) < 2: raise ValueError('Missing source archive root')
                name = '/'.join(parts[1:])
                if name in seen: raise ValueError('Duplicate source archive member')
                seen.add(name)
                with bundle.extractfile(member) as stream: payloads[name] = stream.read()
            if len(roots) != 1: raise ValueError('Multiple source archive roots')
    license_members = {}
    if licensing:
        if wheel:
            entries = [n for n in seen if len(PurePosixPath(n).parts)==2 and
                       PurePosixPath(n).parts[0].startswith('humanwill_evals-') and
                       PurePosixPath(n).parts[0].endswith('.dist-info') and n.endswith('/METADATA')]
            if len(entries) != 1:
                raise ValueError('Expected exactly one wheel metadata file')
            prefix = entries[0].rsplit('/', 1)[0]+'/licenses/'
            license_members = {prefix+n:n for n in licensing['files']}
            metadata_raw = payloads[entries[0]]
        else:
            if 'PKG-INFO' not in payloads: raise ValueError('Missing source metadata')
            metadata_raw = payloads['PKG-INFO']
        license_metadata(metadata_raw, licensing)
    metadata = {'METADATA','WHEEL','entry_points.txt','top_level.txt','RECORD'}
    source_metadata = {'PKG-INFO','SOURCES.txt','dependency_links.txt','entry_points.txt','requires.txt','top_level.txt'}
    allowed = package if wheel else set(inventory(root)) | {'README.md','PKG-INFO','setup.cfg'}
    for name, raw in payloads.items():
        parts = PurePosixPath(name).parts
        generated = (len(parts)==2 and parts[0].startswith('humanwill_evals-') and
                     parts[0].endswith('.dist-info') and parts[1] in metadata) if wheel else (
                     len(parts)==2 and parts[0]=='humanwill_evals.egg-info' and parts[1] in source_metadata)
        if name not in allowed and name not in license_members and not generated:
            raise ValueError('Unexpected distribution file: '+name)
        content_check(name, raw)
        if name in (package if wheel else source_files) and raw != (root/name).read_bytes():
            raise ValueError('Distribution differs from source: '+name)
        if name in license_members and raw != (root/license_members[name]).read_bytes():
            raise ValueError('Distribution license notice differs from source: '+name)
    required = package if wheel else set(inventory(root)) | {'README.md','PKG-INFO'}
    required = required | set(license_members)
    if not required <= seen: raise ValueError('Distribution omitted required files')
    return {'file':path.name, 'kind':'wheel' if wheel else 'sdist', 'files':len(seen),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'source_matches':True}


def suite(require_extras=False, root=ROOT):
    if require_extras and not all(importlib.util.find_spec(m) for m in ('httpx','matplotlib','reportlab','PIL','pypdf')):
        raise ValueError('Full gate requires live/reports extras and test-only pypdf')
    sys.path.insert(0, str(root))
    loader = unittest.TestLoader(); tests = unittest.TestSuite()
    for name in SUITES:
        tests.addTests(loader.discover(str(root/'tests'), pattern=name+'.py'))
    result = unittest.TextTestRunner(verbosity=1).run(tests)
    if not result.wasSuccessful() or (require_extras and result.skipped):
        raise ValueError('Release tests failed or required tests were skipped')
    return {'tests':result.testsRun, 'skipped':len(result.skipped), 'passed':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('stage').add_argument('--output',required=True)
    sub.add_parser('archive').add_argument('paths',nargs='+')
    sub.add_parser('test').add_argument('--require-extras',action='store_true')
    args=parser.parse_args()
    if args.command=='stage': value=stage(args.output)
    elif args.command=='archive': value=[archive(p) for p in args.paths]
    else: value=suite(args.require_extras)
    print(json.dumps(value,indent=2))


if __name__=='__main__':
    main()
