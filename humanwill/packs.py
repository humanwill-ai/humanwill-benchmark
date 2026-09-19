"""Exact-message pack loader; no campaign imports or model calls.

Generalizes the identity/hash/duplicate checks in cybersecurity_initial without
changing its pinned contract. Version 1 below is a separate portable contract.
"""
from pathlib import Path

from .contracts import decode, digest, fields, fingerprint, identifier, nonempty, require, HumanWillError


def read(path):
    require(not path.is_symlink(), "unsafe_path", "Pack files cannot be symlinks.")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise HumanWillError("pack_unavailable", "Cannot read the local pack.") from exc


def validate(manifest, rows):
    fields(manifest, {"format", "id", "version", "domain", "license", "review_status",
                      "cases_file", "cases_sha256", "count"})
    require(manifest["format"] == "humanwill.message-pack/1", "unsupported_version", "Unsupported pack format.")
    identifier(manifest["id"])
    for key in ("version", "license", "review_status"):
        nonempty(manifest[key])
    require(manifest["domain"] == "demonstration", message="Phase 2 executes demonstration packs only.")
    require(manifest["cases_file"] == "cases.jsonl", message="Expected cases.jsonl in the manifest directory.")
    require(type(manifest["count"]) is int and manifest["count"] == len(rows) and len(rows) > 0,
            message="Pack count mismatch or empty pack.")
    identities, message_hashes, source_identities = set(), set(), set()
    for row in rows:
        fields(row, {"id", "family", "messages", "provenance"})
        identifier(row["id"])
        identifier(row["family"])
        require(row["id"].casefold() not in identities, message="Duplicate question ID.")
        identities.add(row["id"].casefold())
        messages = row["messages"]
        require(isinstance(messages, list) and len(messages) == 2, message="Expected system and user messages.")
        for message, role in zip(messages, ("system", "user")):
            fields(message, {"role", "content"})
            require(message["role"] == role, message="Unexpected message role/order.")
            nonempty(message["content"])
        sha = fingerprint(messages)
        require(sha not in message_hashes, message="Duplicate exact messages require explicit provenance review.")
        message_hashes.add(sha)
        provenance = row["provenance"]
        fields(provenance, {"source_id", "source", "authorship", "license", "messages_sha256"})
        for key in ("source_id", "source", "authorship", "license"):
            nonempty(provenance[key])
        source_identity = (provenance["source"], provenance["source_id"])
        require(source_identity not in source_identities, message="Duplicate source identity requires explicit review.")
        source_identities.add(source_identity)
        require(provenance["messages_sha256"] == sha, message="Source message hash mismatch.")
    return manifest, rows


def load(path: str | Path):
    path = Path(path)
    manifest_raw = read(path)
    manifest = decode(manifest_raw)
    require(isinstance(manifest, dict) and manifest.get("cases_file") == "cases.jsonl",
            message="Unsupported pack case path.")
    raw = read(path.parent / "cases.jsonl")
    require(digest(raw) == manifest.get("cases_sha256"), message="Pack content hash mismatch.")
    rows = [decode(line) for line in raw.splitlines() if line.strip()]
    validate(manifest, rows)
    return {"manifest": manifest, "cases": rows,
            "manifest_sha256": digest(manifest_raw), "cases_sha256": digest(raw)}
