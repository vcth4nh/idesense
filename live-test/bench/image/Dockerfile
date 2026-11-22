# syntax=docker/dockerfile:1
# check=skip=InvalidDefaultArgInFrom
# Product image of the agent benchmark (idesense-bench-<product>:p2).
# `python3 -m bench.images build <product>` makes the build context (this file, entry.sh, aids/,
# ws/<slot id>/<product>/) and builds with `--build-arg PRODUCT=<caddy|beets>`,
# `--build-arg SLOTS_ROOT=<the slots root of the host>` and a `--build-arg` for each pin of
# live-test/manifest.json (BASE_IMAGE and the versions and SHA-256 values below). The trees come from their
# master manifests, with no agent instruction file of the product, no .idea, no .venv and no .git. In the image
# each tree is at its slot path SLOTS_ROOT/<slot id>/<product>, as on the host.
# PRODUCT, BASE_IMAGE and the pins have no default on purpose (so the check above is off): a build without them
# fails. An empty CLAUDE_CODE_VERSION fails too (`test -n`); else npm installs the latest version. `bench.images
# build` checks each pin before the build.
ARG PRODUCT
ARG BASE_IMAGE
ARG SLOTS_ROOT=/home/ubuntu/dev/ws

FROM ${BASE_IMAGE} AS base
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git jq ripgrep less file unzip \
      build-essential python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*
ENV LANG=C.UTF-8

# Node from the official archive; the SHA-256 is that of
# https://nodejs.org/dist/v<NODE_VERSION>/SHASUMS256.txt.
ARG NODE_VERSION
ARG NODE_SHA256
RUN curl -fsSLo /tmp/node.tar.gz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.gz" \
 && echo "${NODE_SHA256}  /tmp/node.tar.gz" | sha256sum -c - \
 && mkdir /opt/node \
 && tar -xzf /tmp/node.tar.gz -C /opt/node --strip-components=1 --no-same-owner \
 && rm /tmp/node.tar.gz
ENV PATH=/opt/node/bin:$PATH

ARG CLAUDE_CODE_VERSION
RUN test -n "${CLAUDE_CODE_VERSION}" \
 && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
 && npm cache clean --force
ENV DISABLE_AUTOUPDATER=1

ARG SLOTS_ROOT
RUN mkdir -p "${SLOTS_ROOT}" \
 && chown -R ubuntu:ubuntu /home/ubuntu "${SLOTS_ROOT}"

# caddy: Go from the official archive; the SHA-256 is that of https://go.dev/dl/?mode=json&include=all.
FROM base AS caddy-tools
ARG GO_VERSION
ARG GO_SHA256
RUN curl -fsSLo /tmp/go.tar.gz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
 && echo "${GO_SHA256}  /tmp/go.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/go.tar.gz -C /usr/local --no-same-owner \
 && rm /tmp/go.tar.gz
ENV PATH=/usr/local/go/bin:/home/ubuntu/go/bin:$PATH

# beets: uv from its GitHub release; the SHA-256 is that of the release file
# uv-x86_64-unknown-linux-gnu.tar.gz.sha256.
FROM base AS beets-tools
ARG UV_VERSION
ARG UV_SHA256
RUN curl -fsSLo /tmp/uv.tar.gz "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
 && echo "${UV_SHA256}  /tmp/uv.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1 --no-same-owner \
 && rm /tmp/uv.tar.gz

FROM ${PRODUCT}-tools AS product
ARG PRODUCT
ARG SLOTS_ROOT
COPY --chown=ubuntu:ubuntu ws/ ${SLOTS_ROOT}/
USER ubuntu
WORKDIR ${SLOTS_ROOT}

# Each tree: a new repository with one commit of all its files.
RUN <<'EOF'
set -eu
export GIT_AUTHOR_NAME=dev GIT_AUTHOR_EMAIL=dev@localhost GIT_AUTHOR_DATE=2026-01-01T00:00:00Z
export GIT_COMMITTER_NAME=dev GIT_COMMITTER_EMAIL=dev@localhost GIT_COMMITTER_DATE=2026-01-01T00:00:00Z
for t in */*/; do
  t="${t%/}"
  git -C "$t" init -q
  git -C "$t" add -A
  git -C "$t" commit -q -m "Initial commit"
  printf '.venv/\n.claude/\nCLAUDE.md\n' >> "$t/.git/info/exclude"
  # No file of the tree is untracked or ignored: the commit has each file.
  test -z "$(git -C "$t" status --porcelain --ignored)"
done
EOF

# Warm caches. caddy: module cache, build cache, and one run of the baseline test command in each
# tree (a failed test does not stop the build; the gate checks the tests). beets: the locked
# environment with the system Python 3.12.
RUN <<'EOF'
set -eu
for t in */*/; do
  t="${t%/}"
  case "$PRODUCT" in
    caddy)
      (cd "$t" && go mod download && go build ./...)
      if (cd "$t" && XDG_CONFIG_HOME=/tmp/xdg/config XDG_DATA_HOME=/tmp/xdg/data \
            go test -count=1 -p 1 ./... > /tmp/warm.log 2>&1); then rc=0; else rc=$?; fi
      echo "warm test $t: exit $rc, $(grep -c '^ok' /tmp/warm.log) ok, $(grep -c '^FAIL' /tmp/warm.log) FAIL"
      rm -rf /tmp/xdg /tmp/warm.log ;;
    beets)
      (cd "$t" && UV_PYTHON_DOWNLOADS=never uv sync --locked --python 3.12) ;;
    *)
      echo "unknown PRODUCT '$PRODUCT'" >&2
      exit 2 ;;
  esac
  test -z "$(git -C "$t" status --porcelain)"
done
EOF

# The entry script and the aids; the entry script removes this folder before it starts claude. The entry
# script finds the slots in BENCH_SLOTS_ROOT, and unsets it before it starts claude.
ENV BENCH_SLOTS_ROOT=${SLOTS_ROOT}
RUN mkdir /home/ubuntu/.init
COPY --chown=ubuntu:ubuntu --chmod=0755 entry.sh /home/ubuntu/.init/entry.sh
COPY --chown=ubuntu:ubuntu aids/ /home/ubuntu/.init/aids/
WORKDIR /home/ubuntu
ENTRYPOINT ["/home/ubuntu/.init/entry.sh"]
