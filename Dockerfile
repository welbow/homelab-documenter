# --- Stage 1: fetch and verify the Bitwarden CLI --------------------------
FROM debian:trixie-slim AS bw

# Pinned release; Renovate bumps it (see renovate.json).
# renovate: datasource=github-releases depName=bitwarden/clients extractVersion=^cli-v(?<version>.+)$
ARG BW_VERSION=2026.9.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl jq unzip \
 && rm -rf /var/lib/apt/lists/*

# Verify the zip against the SHA-256 digest GitHub publishes for the release
# asset, then unpack. Fails the build on a mismatch or a missing digest.
RUN set -eu; \
    zip="bw-linux-${BW_VERSION}.zip"; \
    base="https://github.com/bitwarden/clients/releases"; \
    curl -fsSLo "$zip" "$base/download/cli-v${BW_VERSION}/$zip"; \
    want="$(curl -fsSL "https://api.github.com/repos/bitwarden/clients/releases/tags/cli-v${BW_VERSION}" \
      | jq -r --arg n "$zip" '.assets[] | select(.name == $n) | .digest // empty' \
      | sed 's/^sha256://')"; \
    test -n "$want"; \
    echo "$want  $zip" | sha256sum -c -; \
    unzip -q "$zip"; \
    install -m 0755 bw /usr/local/bin/bw

# --- Stage 2: the app ----------------------------------------------------
FROM python:3.12-slim-trixie

WORKDIR /app

# Dependencies first, so code changes don't re-run these layers.
COPY apt-pkgs.txt requirements.txt ./
RUN apt-get update \
 && xargs -a apt-pkgs.txt apt-get install -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -r requirements.txt

COPY --from=bw /usr/local/bin/bw /app/bin/bw

COPY . .

# Fail the build, not the run, if a bundled tool can't execute.
RUN /app/bin/bw --version && nmap --version > /dev/null

ENTRYPOINT ["/app/entrypoint.sh"]
