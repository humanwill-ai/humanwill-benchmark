"""Read-only adapters for the two pinned historical HTTPX capture schemas.

No historical runner imports, migrations, writes, automatic directory scanning,
or invented request/usage fields. Caller explicitly selects one metadata file.
"""
import base64
from pathlib import Path
from .contracts import digest, fields, require
from . import runs
from .live import SAFE_HEADERS


def inspect_capture(metadata_path, *, include_http=False):
    require(type(include_http) is bool, message='Expected boolean HTTP option.')
    path=Path(metadata_path).expanduser()
    require(not any(p.is_symlink() for p in [path,*path.parents]), 'unsafe_path','Historical capture path contains a symlink.')
    path=path.resolve();metadata=runs.read(path)
    common={'http_status','response_headers','body_sha256','body_bytes','representation'}
    if 'capture_error' in metadata:
        fields(metadata,common|{'capture_error'})
        require(path.name=='response-001.json', message='Unsupported historical stream filename.')
        filename='response-001.body';complete=metadata['capture_error'] is None
        source='core.runners.openrouter_stream_recovery/http-v1'
    else:
        fields(metadata,common|{'http_version','body_file'})
        filename=metadata['body_file'];complete=True
        require(filename==path.with_suffix('.body').name and path.name.startswith('response-'), message='Unsupported historical body filename.')
        source='core.model_adapters.http_capture/http-v1'
    body_path=path.parent/filename
    require(not body_path.is_symlink() and Path(filename).name==filename, message='Unsafe historical body path.')
    body=body_path.read_bytes()
    require(digest(body)==metadata['body_sha256'] and len(body)==metadata['body_bytes'], 'integrity_error','Historical capture hash or length mismatch.')
    result={'format':'humanwill.history-inspection/1','read_only':True,'source_format':source,
            'metadata_path':str(path),'metadata_sha256':digest(path.read_bytes()),'http_body_path':str(body_path),
            'http_status':metadata['http_status'],'capture_status':'complete' if complete else 'partial',
            'body_sha256':digest(body),'body_bytes':len(body),'representation':metadata['representation'],
            'headers':[(k,v) for k,v in metadata['response_headers'] if k.lower() in SAFE_HEADERS],
            'header_policy':'allowlist/1','request':None,'accounting':None,
            'unavailable':['request','accounting','provider_identity','semantic_judgment']}
    if include_http: result.update(http_body_base64=base64.b64encode(body).decode('ascii'),http_body_encoding='base64')
    return result
