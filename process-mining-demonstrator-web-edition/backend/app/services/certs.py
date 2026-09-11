"""TLS certificate helpers — self-signed generation, inspection and validation.

Uses `cryptography` (already a dependency). No shelling out to openssl.
"""

from __future__ import annotations

import datetime
import ipaddress
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@dataclass
class CertInfo:
    subject: str
    issuer: str
    not_before: str
    not_after: str
    sans: list[str]
    is_self_signed: bool


class CertError(ValueError):
    """Raised when a certificate or key is malformed or mismatched."""


def _san_entry(value: str) -> x509.GeneralName:
    """Interpret a SAN string as an IP address if it parses, else a DNS name."""
    value = value.strip()
    try:
        return x509.IPAddress(ipaddress.ip_address(value))
    except ValueError:
        return x509.DNSName(value)


def generate_self_signed(
    *,
    common_name: str,
    sans: list[str],
    days: int = 825,
    key_size: int = 2048,
) -> tuple[str, str]:
    """Return (cert_pem, key_pem) for a fresh self-signed certificate.

    The common name is always added to the SAN list, since modern clients ignore
    the legacy CN field. IPv4/IPv6 SANs are detected automatically.
    """
    if not common_name.strip():
        raise CertError("A common name (host) is required.")
    if key_size < 2048:
        raise CertError("Key size must be at least 2048 bits.")
    days = max(1, min(days, 3650))

    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name.strip())])

    san_values = [common_name.strip(), *[s for s in sans if s.strip()]]
    seen: set[str] = set()
    entries: list[x509.GeneralName] = []
    for value in san_values:
        v = value.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            entries.append(_san_entry(v))

    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    cert = builder.sign(key, hashes.SHA256())

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return cert_pem, key_pem


def inspect(cert_pem: str) -> CertInfo:
    """Parse a PEM certificate and summarise it for display."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise CertError("The certificate is not valid PEM.") from exc

    sans: list[str] = []
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for gn in ext.value:
            if isinstance(gn, x509.DNSName):
                sans.append(gn.value)
            elif isinstance(gn, x509.IPAddress):
                sans.append(str(gn.value))
    except x509.ExtensionNotFound:
        pass

    # `not_valid_before_utc` exists on modern cryptography; fall back otherwise.
    nb = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
    na = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after

    return CertInfo(
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        not_before=nb.isoformat(),
        not_after=na.isoformat(),
        sans=sans,
        is_self_signed=cert.subject == cert.issuer,
    )


def validate_pair(cert_pem: str, key_pem: str) -> CertInfo:
    """Validate that a private key matches its certificate. Returns CertInfo."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise CertError("The certificate is not valid PEM.") from exc
    try:
        key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise CertError(
            "The private key is not valid PEM, or it is password-protected "
            "(remove the passphrase before uploading)."
        ) from exc

    cert_pub = cert.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key_pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if cert_pub != key_pub:
        raise CertError("The private key does not match the certificate.")

    return inspect(cert_pem)
