"""Read-only extraction of the frozen-message-pack/0.1.0 verifier.

Source: core/benchmark_adapters/cybersecurity_initial.py. No assembly, campaign
imports, source preparation or hardcoded private filesystem locations.
"""
from collections import Counter
from pathlib import Path
from .contracts import encode, digest, decode as strict_json
FORMAT = "humanwill.frozen-message-pack/0.1.0"
CASE_FORMAT = "humanwill.frozen-message-case/0.1.0"
GROUPS = ("original100", "discovery324")
COUNTS = {"V":81,"C":84,"B":80,"N":89,"F":90}

def safe_path(base, relative):
    rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid pack-relative path')
    path=base/rel
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink in pack path')
    if not path.resolve().is_relative_to(base.resolve()):raise ValueError('Path outside pack')
    return path


def validate_record(row):
    if set(row)!={'format','id','family','messages','provenance','intended_behavior','review_status'}:
        raise ValueError('Unexpected case fields')
    if row['format']!=CASE_FORMAT or row['family'] not in COUNTS:
        raise ValueError('Unsupported case format/family')
    identity=row['id']
    if (not isinstance(identity,str) or not identity.isascii() or not identity.isalnum()
            or identity[0] not in 'EVCBNF' or not identity[1:].isdigit()):
        raise ValueError('Invalid source identifier')
    messages=row['messages']
    if not isinstance(messages,list) or len(messages)!=2:
        raise ValueError('Unsupported message count')
    if any(not isinstance(m,dict) or set(m)!={'role','content'} for m in messages):
        raise ValueError('Unsupported message fields')
    if [m['role'] for m in messages]!=['system','user']:
        raise ValueError('Unsupported message roles')
    if any(not isinstance(m['content'],str) or not m['content'] for m in messages):
        raise ValueError('Invalid original message text')
    p=row['provenance']
    if set(p)!={'source_set','source_id','source_bundle_sha256','source_messages_sha256',
                'original_request_sha256','original_runtime_settings','authorship','license'}:
        raise ValueError('Unexpected provenance fields')
    if p['source_set'] not in GROUPS or p['source_id']!=identity:
        raise ValueError('Lost original source identity')
    if ((p['source_set']=='original100' and (identity[0]!=row['family'] or not 1<=int(identity[1:])<=20))
            or (p['source_set']=='discovery324' and identity[0]!='E')):
        raise ValueError('Source identity/family mismatch')
    if p['source_messages_sha256']!=digest(encode(messages)):
        raise ValueError('Original messages changed')
    for key in ('source_bundle_sha256','source_messages_sha256'):
        if not isinstance(p[key],str) or len(p[key])!=64 or any(c not in '0123456789abcdef' for c in p[key]):
            raise ValueError('Invalid source digest')
    request_sha=p['original_request_sha256']
    if request_sha is not None and (not isinstance(request_sha,str) or len(request_sha)!=64
                                   or any(c not in '0123456789abcdef' for c in request_sha)):
        raise ValueError('Invalid original request digest')
    if p['source_set']=='discovery324' and request_sha is None:
        raise ValueError('Missing golden original request digest')
    if not isinstance(p['original_runtime_settings'],dict):raise ValueError('Invalid source runtime metadata')
    if p['license']!='unselected' or p['authorship']!='HumanWill; AI-assisted':
        raise ValueError('Unsupported rights claim')
    if row['intended_behavior']!='assist_within_supplied_scope':
        raise ValueError('Unsupported intended behavior')
    if row['review_status'] not in ('existing_in_scope_benchmark','owner_admitted_discovery; independent_review_not_claimed'):
        raise ValueError('Unsupported review claim')


def verify(directory):
    directory=Path(directory)
    raw=safe_path(directory,'manifest.json').read_bytes()
    if digest(raw)!=safe_path(directory,'manifest.sha256').read_text().strip():
        raise ValueError('Manifest digest mismatch')
    m=strict_json(raw)
    if m['format']!=FORMAT or m['domain']!='cybersecurity' or m['status']!='frozen_private_pilot':
        raise ValueError('Unsupported pack contract')
    rows=[];ids=set();messages=set();paths=set()
    for entry in m['cases']:
        data=safe_path(directory,entry['path']).read_bytes()
        if digest(data)!=entry['sha256']:raise ValueError('Case digest mismatch')
        row=strict_json(data);validate_record(row)
        if (row['id']!=entry['id'] or row['family']!=entry['family']
                or row['provenance']['source_set']!=entry['source_set']
                or digest(encode(row['messages']))!=entry['messages_sha256']):
            raise ValueError('Case index/provenance mismatch')
        if row['id'] in ids or entry['messages_sha256'] in messages or entry['path'] in paths:
            raise ValueError('Duplicate source or content')
        ids.add(row['id']);messages.add(entry['messages_sha256']);paths.add(entry['path']);rows.append(row)
    if (len(rows)!=m['total'] or Counter(r['family'] for r in rows)!=m['family_counts']
            or Counter(r['provenance']['source_set'] for r in rows)!=m['source_counts']):
        raise ValueError('Manifest count mismatch')
    for group in GROUPS:
        if dict(Counter(r['family'] for r in rows if r['provenance']['source_set']==group))!=m['source_family_counts'][group]:
            raise ValueError('Source/family count mismatch')
    return m,rows
