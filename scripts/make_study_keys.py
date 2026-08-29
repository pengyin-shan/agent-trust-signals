#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trust_signals.treatments.keys import PRIVATE_DIR, PUBLIC_DIR, TreatmentError, generate_study_keys, stop_agent

def main() -> int:
    try:
        keys = generate_study_keys()
    except TreatmentError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    stop_agent(PRIVATE_DIR / "gnupg")
    print(f"private material: {PRIVATE_DIR}  (gitignored)")
    print(f"public material:  {PUBLIC_DIR}   (commit this directory)")
    for label, ident in keys.identities.items():
        print(f"identity {label}: {ident.uid}")
        print(f"  OpenPGP fingerprint : {ident.pgp_fingerprint}")
        print(f"  attestation key id  : sha256:{ident.ecdsa_keyid}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
