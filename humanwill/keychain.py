"""Standalone extraction of core.credentials.macos_keychain native binding.

No historical imports or command entry point; same existing service/account names.
"""
from contextlib import contextmanager
import ctypes as ct
import sys

SERVICE = "org.humanwill.evals.openai"
SERVICES = {"openai": SERVICE, "anthropic": "org.humanwill.evals.anthropic",
            "openrouter": "org.humanwill.evals.openrouter"}
LABELS = {"openai": "OpenAI", "anthropic": "Anthropic", "openrouter": "OpenRouter"}
ACCOUNT = "api-key"
NOT_FOUND = -25300
DUPLICATE = -25299


class CredentialError(Exception):
    """A content-free credential operation failure."""


class MacOSKeychain:
    """Small in-process binding to Security.framework's SecItem API.

    No subprocess, environment variable, or plaintext credential file is used.
    Keychain access is governed by macOS, not by a Python-module security boundary.
    """

    provider = "openai"

    def __init__(self, provider="openai"):
        if provider not in SERVICES:
            raise CredentialError("Unsupported credential provider.")
        self.provider = provider
        if sys.platform != "darwin":
            raise CredentialError("This credential helper requires macOS.")
        self.security = ct.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.cf = ct.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ptr = ct.c_void_p
        signatures = {
            "CFDictionaryCreateMutable": (ptr, [ptr, ct.c_long, ptr, ptr]),
            "CFDictionarySetValue": (None, [ptr, ptr, ptr]),
            "CFStringCreateWithCString": (ptr, [ptr, ct.c_char_p, ct.c_uint32]),
            "CFDataCreate": (ptr, [ptr, ct.c_char_p, ct.c_long]),
            "CFDataGetLength": (ct.c_long, [ptr]),
            "CFDataGetBytePtr": (ptr, [ptr]),
            "CFRelease": (None, [ptr]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.cf, name)
            function.restype, function.argtypes = result, arguments
        for name in ("SecItemAdd", "SecItemCopyMatching"):
            function = getattr(self.security, name)
            function.restype, function.argtypes = ct.c_int32, [ptr, ct.POINTER(ptr)]
        self.security.SecItemUpdate.restype = ct.c_int32
        self.security.SecItemUpdate.argtypes = [ptr, ptr]

    def _constant(self, name):
        library = self.cf if name.startswith("kCF") else self.security
        return ct.c_void_p.in_dll(library, name).value

    @contextmanager
    def _dictionary(self, values):
        # NULL callbacks: references below remain alive for the complete native call.
        dictionary = self.cf.CFDictionaryCreateMutable(None, 0, None, None)
        if not dictionary:
            raise CredentialError("Could not allocate Keychain request.")
        owned = []
        try:
            for key, value in values.items():
                if isinstance(value, bytes):
                    ref = self.cf.CFDataCreate(None, value, len(value))
                    owned.append(ref)
                elif isinstance(value, str) and not value.startswith("kSec"):
                    ref = self.cf.CFStringCreateWithCString(None, value.encode("utf-8"), 0x08000100)
                    owned.append(ref)
                else:
                    ref = self._constant("kCFBooleanTrue") if value is True else self._constant(value)
                if not ref:
                    raise CredentialError("Could not allocate Keychain value.")
                self.cf.CFDictionarySetValue(dictionary, self._constant(key), ref)
            yield dictionary
        finally:
            self.cf.CFRelease(dictionary)
            for ref in owned:
                if ref:
                    self.cf.CFRelease(ref)

    def _query(self):
        return {"kSecClass": "kSecClassGenericPassword",
                "kSecAttrService": SERVICES[self.provider], "kSecAttrAccount": ACCOUNT}

    @staticmethod
    def _check(status):
        if status != 0:
            raise CredentialError(f"Keychain operation failed (OSStatus {status}); check access in Keychain Access.")

    def exists(self):
        # Return attributes only: do not request the password just to show status.
        query = {**self._query(), "kSecReturnAttributes": True, "kSecMatchLimit": "kSecMatchLimitOne"}
        result = ct.c_void_p()
        with self._dictionary(query) as native:
            status = self.security.SecItemCopyMatching(native, ct.byref(result))
        try:
            if status == NOT_FOUND:
                return False
            self._check(status)
            return True
        finally:
            if result.value:
                self.cf.CFRelease(result)

    def save(self, secret, *, replace=False):
        validate_key(secret)
        with self._dictionary({**self._query(), "kSecValueData": secret.encode("ascii")}) as native:
            status = self.security.SecItemAdd(native, None)
        if status == DUPLICATE:
            if not replace:
                raise CredentialError("A key already exists. Use set --replace to replace it explicitly.")
            with self._dictionary(self._query()) as query:
                with self._dictionary({"kSecValueData": secret.encode("ascii")}) as changes:
                    status = self.security.SecItemUpdate(query, changes)
        self._check(status)

    def read(self):
        query = {**self._query(), "kSecReturnData": True, "kSecMatchLimit": "kSecMatchLimitOne"}
        result = ct.c_void_p()
        with self._dictionary(query) as native:
            status = self.security.SecItemCopyMatching(native, ct.byref(result))
        try:
            if status == NOT_FOUND:
                raise CredentialError(f"No {LABELS[self.provider]} key is stored. Run the setup command first.")
            self._check(status)
            if not result.value:
                raise CredentialError("Keychain returned no credential data.")
            raw = ct.string_at(self.cf.CFDataGetBytePtr(result), self.cf.CFDataGetLength(result))
            try:
                secret = raw.decode("ascii")
            except UnicodeError:
                raise CredentialError("Stored credential has an invalid format.") from None
            validate_key(secret)
            return secret
        finally:
            if result.value:
                self.cf.CFRelease(result)


def validate_key(secret):
    # Structural checks only; no attempt to authenticate or infer provider validity.
    if not isinstance(secret, str) or not secret or len(secret) > 8192 or any(
            ord(char) < 33 or ord(char) > 126 for char in secret):
        raise CredentialError("Enter a nonempty key without whitespace or control characters (maximum 8192 characters).")
