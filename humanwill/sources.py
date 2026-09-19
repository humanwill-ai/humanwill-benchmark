"""Pack adapters preserving original schemas and provenance in local snapshots."""
from . import packs
from .contracts import decode, digest, fingerprint, require, HumanWillError
from pathlib import Path


def load(path):
    path = Path(path)
    raw = packs.read(path)
    manifest = decode(raw)
    if isinstance(manifest, dict) and manifest.get("format") == "humanwill.question-pack/1":
        from . import authoring
        return authoring.load(path)
    if isinstance(manifest, dict) and manifest.get("format") == "humanwill.frozen-message-pack/0.1.0":
        from .frozen_pack import verify
        require(path.name == "manifest.json", message="Expected frozen manifest.json.")
        try: manifest, rows = verify(path.parent)
        except (ValueError, KeyError, TypeError, OSError):
            raise HumanWillError("invalid_pack", "Frozen pack validation failed.") from None
        return {"manifest": manifest, "cases": rows, "manifest_sha256": digest(raw), "cases_sha256": fingerprint(rows)}
    return packs.load(path)


def validate(snapshot):
    manifest, rows = snapshot["manifest"], snapshot["cases"]
    if manifest.get("format") == "humanwill.question-pack/1":
        from . import authoring
        authoring.validate(manifest, rows)
        return
    if manifest.get("format") != "humanwill.frozen-message-pack/0.1.0":
        packs.validate(manifest, rows); return
    from .frozen_pack import validate_record
    require(manifest.get("domain") == "cybersecurity" and manifest.get("status") == "frozen_private_pilot", message="Unsupported frozen pack.")
    try:
        for row in rows: validate_record(row)
    except (ValueError, KeyError, TypeError):
        raise HumanWillError("invalid_pack", "Invalid frozen snapshot.") from None
    require(len(rows) == manifest["total"] and fingerprint(rows) == snapshot["cases_sha256"], message="Frozen population changed.")
    require(len({r['id'] for r in rows}) == len(rows) == len({fingerprint(r['messages']) for r in rows}), message="Duplicate frozen input.")


def identity(snapshot):
    m = snapshot["manifest"]
    return m.get("id", m.get("pack_id"))
