"""Resolve secrets only at dispatch, never during planning."""
import os
from .contracts import HumanWillError, require


def available(reference):
    if reference.startswith("env:"):
        return bool(os.environ.get(reference[4:]))
    # Do not trigger Keychain permission UI during offline check.
    import sys
    return None if sys.platform == "darwin" else False


def resolve(reference):
    if reference.startswith("env:"):
        secret = os.environ.get(reference[4:])
    else:
        try:
            from .keychain import MacOSKeychain
            secret = MacOSKeychain(reference.split(":", 1)[1]).read()
        except Exception:
            raise HumanWillError("credential_unavailable", "Cannot read the referenced Keychain credential.") from None
    require(isinstance(secret, str) and 0 < len(secret) <= 8192
            and all(33 <= ord(c) <= 126 for c in secret),
            "credential_unavailable", "Credential is missing or has an invalid format.")
    return secret
