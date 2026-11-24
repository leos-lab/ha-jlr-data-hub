"""Keys, the portal certificate, client assertions and DPoP proofs (all PS256: RSASSA-PSS, SHA-256, 32-byte salt).

Mirrors Packages/JLRDataHub (Swift). Kept free of web-framework code so a Home Assistant integration can reuse it.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class RSAKey:
    def __init__(self, key: rsa.RSAPrivateKey):
        self.key = key

    @classmethod
    def generate(cls) -> "RSAKey":
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=2048))

    @classmethod
    def from_pem(cls, pem: bytes) -> "RSAKey":
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("not an RSA key")
        return cls(key)

    @classmethod
    def load_or_create(cls, path: Path) -> "RSAKey":
        if path.exists():
            return cls.from_pem(path.read_bytes())
        key = cls.generate()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key.pem())
        return key

    def pem(self) -> bytes:
        return self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption())

    def sign(self, data: bytes) -> bytes:
        return self.key.sign(data, PSS, hashes.SHA256())

    @property
    def jwk(self) -> dict:
        n = self.key.public_key().public_numbers()
        def enc(i: int) -> str:
            return b64url(i.to_bytes((i.bit_length() + 7) // 8, "big"))
        return {"kty": "RSA", "n": enc(n.n), "e": enc(n.e)}

    def certificate_pem(self, common_name: str = "jlr-data-hub", days: int = 365) -> str:
        """Self-signed certificate to upload in the JLR portal, built like the Data Hub's own sample."""
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(self.key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(minutes=5))
                .not_valid_after(now + dt.timedelta(days=days))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(self.key.public_key()), critical=False)
                .sign(self.key, hashes.SHA256(), rsa_padding=PSS))
        return cert.public_bytes(serialization.Encoding.PEM).decode()


def jws(header: dict, claims: dict, key: RSAKey) -> str:
    h = b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    c = b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    return f"{h}.{c}.{b64url(key.sign(f'{h}.{c}'.encode()))}"


def jwt_claims(token: str) -> dict:
    """Claims of a JWT, unverified (for reading our own tokens)."""
    try:
        return json.loads(b64url_decode(token.split(".")[1]))
    except Exception:
        return {}


def client_assertion(client_id: str, audience: str, key: RSAKey) -> str:
    """private_key_jwt (RFC 7523). There is no client secret."""
    now = int(time.time())
    return jws({"alg": "PS256", "typ": "JWT"},
               {"iss": client_id, "sub": client_id, "aud": audience, "jti": str(uuid.uuid4()), "iat": now,
                "exp": now + 300}, key)


class DPoP:
    """RFC 9449 proofs: fresh per request, bound to method, URL and (for the API) the access token."""

    def __init__(self, key: RSAKey):
        self.key = key
        self.nonces: dict[str, str] = {}

    @staticmethod
    def htu(url: str) -> str:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))

    def proof(self, method: str, url: str, access_token: str | None = None) -> str:
        claims = {"jti": str(uuid.uuid4()), "htm": method.upper(), "htu": self.htu(url), "iat": int(time.time())}
        if access_token:
            claims["ath"] = b64url(hashlib.sha256(access_token.encode()).digest())
        nonce = self.nonces.get(urlsplit(url).netloc)
        if nonce:
            claims["nonce"] = nonce
        return jws({"alg": "PS256", "typ": "dpop+jwt", "jwk": self.key.jwk}, claims, self.key)

    def note_nonce(self, url: str, headers) -> bool:
        nonce = headers.get("DPoP-Nonce")
        if not nonce:
            return False
        host = urlsplit(url).netloc
        changed = self.nonces.get(host) != nonce
        self.nonces[host] = nonce
        return changed


def pkce() -> tuple[str, str]:
    verifier = b64url(secrets.token_bytes(32))
    return verifier, b64url(hashlib.sha256(verifier.encode()).digest())
