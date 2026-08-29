from __future__ import annotations
import base64
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from .base import TreatmentError
from ..paths import ROOT

PRIVATE_DIR = ROOT / "keys"
PUBLIC_DIR = ROOT / "reference" / "keys"
DESCRIPTOR = PUBLIC_DIR / "study_keys.json"

IDENTITIES = {
    "A": {"name": "agent-trust-signals release key",
          "email": "release-key@agent-trust-signals.invalid"},
    "B": {"name": "agent-trust-signals unrelated key",
          "email": "unrelated-key@agent-trust-signals.invalid"},
}

def gpg_binary() -> str:
    exe = shutil.which("gpg") or shutil.which("gpg2")
    if not exe:
        raise TreatmentError("gpg not found on PATH (install GnuPG, e.g. brew install gnupg)")
    return exe

_SOCKET_PATH_LIMIT = 96

def _ensure_socketdir(gnupghome: Path, env: dict) -> None:
    if len(str(gnupghome / "S.gpg-agent")) <= _SOCKET_PATH_LIMIT:
        return
    gpgconf = shutil.which("gpgconf")
    if gpgconf:
        subprocess.run([gpgconf, "--create-socketdir"], env=env, capture_output=True, check=False)

def _gpg(gnupghome: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, GNUPGHOME=str(gnupghome))
    _ensure_socketdir(gnupghome, env)
    return subprocess.run([gpg_binary(), "--batch", "--yes", "--no-tty", *args],
                          input=stdin, capture_output=True, env=env, check=False)

def stop_agent(gnupghome: Path) -> None:
    gpgconf = shutil.which("gpgconf")
    if gpgconf:
        env = dict(os.environ, GNUPGHOME=str(gnupghome))
        subprocess.run([gpgconf, "--kill", "gpg-agent"], env=env, capture_output=True, check=False)
        subprocess.run([gpgconf, "--remove-socketdir"], env=env, capture_output=True, check=False)

@dataclass(frozen=True)
class Identity:
    label: str                
    name: str
    email: str
    pgp_fingerprint: str
    pgp_public_armored: str
    ecdsa_private_pem_path: Path
    ecdsa_public_pem: str
    ecdsa_keyid: str

    @property
    def uid(self) -> str:
        return f"{self.name} <{self.email}>"

    def ecdsa_private(self) -> ec.EllipticCurvePrivateKey:
        data = self.ecdsa_private_pem_path.read_bytes()
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise TreatmentError("attestation key is not an EC private key")
        return key

@dataclass(frozen=True)
class StudyKeys:
    gnupghome: Path
    identities: dict[str, Identity]

    def __getitem__(self, label: str) -> Identity:
        return self.identities[label]
    
    def sign_detached(self, label: str, target: Path, out: Path) -> None:
        ident = self.identities[label]
        r = _gpg(self.gnupghome, "--armor", "--detach-sign", "--local-user", ident.pgp_fingerprint,
                 "--output", str(out), str(target))
        if r.returncode != 0:
            raise TreatmentError(f"gpg detach-sign failed: {r.stderr.decode(errors='replace')}")

    def verify_detached(self, signature: Path, target: Path) -> tuple[bool, str]:
        r = _gpg(self.gnupghome, "--verify", str(signature), str(target))
        return r.returncode == 0, r.stderr.decode(errors="replace")

    def dsse_sign(self, label: str, payload_type: str, payload: bytes) -> dict:
        ident = self.identities[label]
        pae = b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type.encode() + \
              b" " + str(len(payload)).encode() + b" " + payload
        sig = ident.ecdsa_private().sign(pae, ec.ECDSA(hashes.SHA256()))
        return {
            "payloadType": payload_type,
            "payload": base64.b64encode(payload).decode(),
            "signatures": [{"keyid": ident.ecdsa_keyid, "sig": base64.b64encode(sig).decode()}],
        }

def ecdsa_keyid(public_pem: str) -> str:
    pub = serialization.load_pem_public_key(public_pem.encode())
    der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()

def dsse_verify(envelope: dict, public_pem: str) -> bool:
    pub = serialization.load_pem_public_key(public_pem.encode())
    payload = base64.b64decode(envelope["payload"])
    pt = envelope["payloadType"]
    pae = b"DSSEv1 " + str(len(pt)).encode() + b" " + pt.encode() + b" " + str(len(payload)).encode() + b" " + payload
    for s in envelope.get("signatures", []):
        try:
            pub.verify(base64.b64decode(s["sig"]), pae, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            continue
    return False

def generate_study_keys(private_dir: Path = PRIVATE_DIR, public_dir: Path = PUBLIC_DIR,
                        overwrite: bool = False) -> StudyKeys:
    descriptor = public_dir / "study_keys.json"
    if descriptor.exists() and not overwrite:
        raise TreatmentError(f"{descriptor} exists; the study key set is generated once (pass overwrite=True only in tests)")
    gnupghome = private_dir / "gnupg"
    if gnupghome.exists() and overwrite:
        shutil.rmtree(gnupghome)
    gnupghome.mkdir(parents=True, exist_ok=True)
    os.chmod(gnupghome, 0o700)
    public_dir.mkdir(parents=True, exist_ok=True)

    identities: dict[str, Identity] = {}
    for label, who in IDENTITIES.items():
        params = (
            "%no-protection\n"
            "Key-Type: eddsa\nKey-Curve: ed25519\nKey-Usage: sign\n"
            f"Name-Real: {who['name']}\nName-Email: {who['email']}\n"
            "Expire-Date: 2y\n%commit\n"
        )
        r = _gpg(gnupghome, "--gen-key", stdin=params.encode())
        if r.returncode != 0:
            raise TreatmentError(f"gpg --gen-key failed for {label}: {r.stderr.decode(errors='replace')}")
        r = _gpg(gnupghome, "--with-colons", "--list-keys", who["email"])
        fprs = [ln.split(":")[9] for ln in r.stdout.decode().splitlines() if ln.startswith("fpr:")]
        if not fprs:
            raise TreatmentError(f"could not read fingerprint for identity {label}")
        fpr = fprs[0]
        r = _gpg(gnupghome, "--armor", "--export", fpr)
        armored = r.stdout.decode()
        (public_dir / f"release-key-{label}.asc").write_text(armored, encoding="utf-8")

        priv = ec.generate_private_key(ec.SECP256R1())
        priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption())
        pub_pem = priv.public_key().public_bytes(serialization.Encoding.PEM,
                                                 serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        priv_path = private_dir / f"attestation-key-{label}.pem"
        priv_path.write_bytes(priv_pem)
        os.chmod(priv_path, 0o600)
        (public_dir / f"attestation-key-{label}.pub").write_text(pub_pem, encoding="utf-8")
        identities[label] = Identity(label, who["name"], who["email"], fpr, armored, priv_path,
                                     pub_pem, ecdsa_keyid(pub_pem))

    descriptor.write_text(json.dumps({
        "generated_with": "scripts/make_study_keys.py",
        "identities": {
            lab: {"name": i.name, "email": i.email, "pgp_fingerprint": i.pgp_fingerprint,
                  "pgp_algorithm": "ed25519", "ecdsa_curve": "P-256", "ecdsa_keyid_sha256": i.ecdsa_keyid,
                  "public_files": [f"release-key-{lab}.asc", f"attestation-key-{lab}.pub"],
                  "role": "declared release identity" if lab == "A" else "issuer-mismatch identity (never named in KEYS)"}
            for lab, i in identities.items()
        },
    }, indent=2) + "\n", encoding="utf-8")
    return StudyKeys(gnupghome, identities)

def load_study_keys(private_dir: Path = PRIVATE_DIR, public_dir: Path = PUBLIC_DIR) -> StudyKeys:
    descriptor = public_dir / "study_keys.json"
    if not descriptor.exists():
        raise TreatmentError("study keys not generated; run scripts/make_study_keys.py once")
    doc = json.loads(descriptor.read_text(encoding="utf-8"))
    gnupghome = private_dir / "gnupg"
    if not gnupghome.exists():
        raise TreatmentError(f"private GnuPG home missing: {gnupghome}")
    identities = {}
    for label, d in doc["identities"].items():
        pub_pem = (public_dir / f"attestation-key-{label}.pub").read_text(encoding="utf-8")
        priv_path = private_dir / f"attestation-key-{label}.pem"
        if not priv_path.exists():
            raise TreatmentError(f"private attestation key missing: {priv_path}")
        identities[label] = Identity(label, d["name"], d["email"], d["pgp_fingerprint"],
                                     (public_dir / f"release-key-{label}.asc").read_text(encoding="utf-8"),
                                     priv_path, pub_pem, ecdsa_keyid(pub_pem))
    return StudyKeys(gnupghome, identities)
