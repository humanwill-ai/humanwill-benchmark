"""Offline integrity gate for the approved reference delivery in the Git checkout.

Print metadata only. This check never executes questions or contacts providers.
"""
import hashlib
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from humanwill import api, config, sources
from humanwill.contracts import fingerprint
from humanwill.result_context import REFERENCE_PACKS, REFERENCE_POLICY

CHECKSUMS_SHA256 = 'fc1503478158a4cbc961b877566f9d1cfce0163d5fdeeb5817f56ec4ae46520e'
PACK_SHA256 = '6e3c4ee98ed358d31e51e8c670a7d713658ae8a43149eab335b4f9da739e0488'


def check(root=ROOT):
    pack = root / 'packs/cybersecurity/0.1.0'
    inventory = pack / 'CHECKSUMS.json'
    if not inventory.is_file() or inventory.is_symlink():
        raise ValueError('Run from the Git checkout with the approved reference pack present.')
    raw = inventory.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CHECKSUMS_SHA256:
        raise ValueError('Approved delivery checksum inventory changed.')
    hashes = json.loads(raw)
    if set(p.name for p in pack.iterdir()) != set(hashes) | {'CHECKSUMS.json'}:
        raise ValueError('Unexpected or missing reference delivery file.')
    for name, expected in hashes.items():
        path = pack / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Reference delivery differs from approved bytes.')
    snapshot = sources.load(pack / 'manifest.json')
    sources.validate(snapshot)
    if fingerprint(snapshot) != PACK_SHA256 or REFERENCE_PACKS[PACK_SHA256][1] != len(snapshot['cases']):
        raise ValueError('Reference identity or population changed.')
    if hashlib.sha256((pack / 'POLICY.md').read_bytes()).hexdigest() != REFERENCE_POLICY:
        raise ValueError('Reference policy changed.')
    review = json.loads((pack / 'REVIEW_STATUS.json').read_bytes())
    if review['approved_questions'] != 424 or review['recommendation'] != 'approve' or not review['owner_acceptance_recorded']:
        raise ValueError('Reference review binding incomplete.')
    # Validate the shipped template at its documented copied location. These
    # synthetic settings only permit offline checking, never real execution.
    value = tomllib.loads((root / 'examples/reference.toml').read_text())
    value['budget_micro_usd'] = 1_000_000
    for spec in [*value['models'], value['judge']]:
        spec['model'] = 'offline-template-validation-only'
        spec['prices'] = dict(input_micro_usd_per_million=1_000_000,
                             output_micro_usd_per_million=1_000_000,
                             source='synthetic offline validation, not provider pricing',
                             verified_at='2026-09-19')
    settings = config.from_dict(value, base=root / '.local')
    checked = api.check(settings)
    return {'approved_questions': len(snapshot['cases']), 'delivery_files': len(hashes) + 1,
            'snapshot_sha256': PACK_SHA256, 'policy_sha256': REFERENCE_POLICY,
            'template_valid': True, 'provider_calls': 0}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
