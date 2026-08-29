# Study key material (public half)

Populated by `python scripts/make_study_keys.py` (run once):

- `study_keys.json`: descriptor (identities, fingerprints, key ids, roles)
- `release-key-A.asc`, `release-key-B.asc`: OpenPGP public keys
- `attestation-key-A.pub`, `attestation-key-B.pub`: ECDSA P-256 public keys (PEM)

Private material is written to `keys/` at the repository root, which is gitignored.
Identity A is the declared release identity named in every treated fork's KEYS file;
identity B signs only the issuer-mismatch conditions. See docs/DESIGN-DECISIONS.md R3/R4.
