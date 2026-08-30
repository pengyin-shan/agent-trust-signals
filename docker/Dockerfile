FROM python:3.12-slim-bookworm

ARG COSIGN_VERSION=2.4.1
ARG COSIGN_ARCH=arm64
ARG COSIGN_SHA256=3b2e2e3854d0356c45fe6607047526ccd04742d20bd44afb5be91fa2a6e7cb4a

ENV PIP_NO_INDEX=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git gnupg openssl coreutils inotify-tools ca-certificates curl \
        pkg-config cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /usr/local/bin/cosign \
        "https://github.com/sigstore/cosign/releases/download/v${COSIGN_VERSION}/cosign-linux-${COSIGN_ARCH}" \
    && echo "${COSIGN_SHA256}  /usr/local/bin/cosign" | sha256sum -c - \
    && chmod +x /usr/local/bin/cosign

RUN PIP_NO_INDEX=0 pip install --no-cache-dir \
        "setuptools>=70" wheel "cython>=3" "meson-python>=0.16" "scikit-build-core>=0.9" \
        hatchling flit-core pdm-backend poetry-core "numpy>=1.26,<3" packaging

RUN mkdir -p /work /log
WORKDIR /work

RUN python - <<'EOF'
import json, subprocess, sys
def v(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()[0]
    except Exception as e:
        return f"unavailable: {e}"
json.dump({
    "python": sys.version.split()[0],
    "pip": v(["pip", "--version"]),
    "gpg": v(["gpg", "--version"]),
    "openssl": v(["openssl", "version"]),
    "cosign": v(["cosign", "version"]),
    "inotifywait": v(["inotifywait", "--help"]),
    "git": v(["git", "--version"]),
}, open("/etc/study-image-tools.json", "w"), indent=2)
EOF

CMD ["sleep", "infinity"]
