# syntax=docker/dockerfile:1
#
# Northstar Release Coordinator - one image, two entry points.
#
# Both interfaces run the same code: `service.AssistantService` is the single
# application layer and neither Streamlit nor FastAPI holds any behaviour, so
# shipping one image and varying only the command is the packaging that matches
# the architecture. Two images would let the API and the app drift apart.
#
# Five requirements shape this file, and each comes from something this project
# measured rather than from container convention:
#
#   1. Secrets stay OUT of the image. `.env` is in `.dockerignore`; credentials
#      arrive at run time through `env_file`. An image layer is permanent.
#   2. The embedding model is BAKED IN. It is ~90 MB and cost 39 s cold against
#      7.3 s warm; downloading it on every start makes a working product look
#      broken, and makes the container depend on Hugging Face being reachable.
#   3. The index and the feedback file are VOLUMES. `data/index/` carries
#      `freshness_manifest.json`; losing it makes a fresh process report
#      "indexed never" and claim `local` over data that was really live or a
#      degraded fallback - a disclosure wrong by construction (F-15.2).
#   4. The local GitHub export SHIPS. Without `data/raw/github/` a failed live
#      fetch has nothing to degrade to, and EVAL-012 has no fallback path.
#   5. HEALTH is model-free. `/health` deliberately touches neither the model nor
#      the index, so a readiness probe cannot burn tokens on a tier where
#      tokens-per-minute is the binding limit (F-27).
#
# Known size limitation, recorded rather than hidden: the image is 3.24 GB, and
# 2.7 GB of the unpacked virtual environment is `site-packages/nvidia` - the CUDA
# stack `torch` pulls in on Linux, which a CPU-only MiniLM never executes. Fixing
# it means pinning the CPU-only torch index, which regenerates `uv.lock` - the
# environment every evaluation ran against - so it is a human-team decision.
#
# This container is NOT production-ready and does not claim to be. Authentication,
# secret management, backups, monitoring and source-level authorization are all
# still absent - see `deliverables/THREAT_MODEL.md`.

# ---------------------------------------------------------------------------
# Stage 1 - resolve the locked environment
#
# Separate so that uv, the compilers and the build caches never reach the runtime
# image. `--frozen` fails rather than silently re-resolving: the point of
# committing `uv.lock` is that the container runs the versions the evaluation
# measured, and a lock file that quietly updates during a build is not a lock.
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS deps

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies resolve from the lock alone, so this layer is cached until the
# lock changes - editing application code does not re-download PyTorch.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


# ---------------------------------------------------------------------------
# Stage 1b - bake the embedding model, keyed to the LOCK rather than to the code
#
# Its own stage on purpose. Baked in the runtime image it sat downstream of the
# venv copy, so any source edit invalidated it and re-downloaded ~90 MB on every
# rebuild. Built from `deps`, it depends only on uv.lock and survives code changes.
# ---------------------------------------------------------------------------
FROM deps AS model

ENV HF_HOME="/opt/hf-cache"
RUN /app/.venv/bin/python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
print('embedding model cached')"


# ---------------------------------------------------------------------------
# Stage 1c - install the project itself
# ---------------------------------------------------------------------------
FROM deps AS builder

# `--no-editable` so the package is copied into the venv rather than linked back
# at a source path that the runtime stage would have to reproduce exactly.
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


# ---------------------------------------------------------------------------
# Stage 2 - runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME="/home/northstar" \
    # One cache location for both the build-time bake and the run-time load, or
    # the baked model would be invisible and downloaded again on first use.
    HF_HOME="/opt/hf-cache" \
    # Chroma phones home by default. An internal permission-aware assistant
    # should not emit telemetry about how it is used.
    ANONYMIZED_TELEMETRY=False \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# A non-root account, and the data directories created HERE rather than by the
# volume mount. Docker seeds a fresh named volume from the image path including
# its ownership, so creating them owned by northstar is what makes the volumes
# writable without granting root.
RUN useradd --create-home --uid 10001 northstar \
    && mkdir -p /app/data/index /app/data/feedback /opt/hf-cache \
    && chown -R northstar:northstar /app /opt/hf-cache

WORKDIR /app

COPY --from=builder --chown=northstar:northstar /app/.venv /app/.venv

# The model cache, copied from a stage that depends only on the lock. Copied
# BEFORE `HF_HUB_OFFLINE` is set below, so the one permitted download happened at
# build time and never at run time.
COPY --from=model --chown=northstar:northstar /opt/hf-cache /opt/hf-cache

# Now that the model is present, forbid network access to the hub entirely. If
# the bake ever silently failed, this turns a slow first answer into a loud
# startup error - which is the failure mode we want.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# Application code and the fixtures the product reads at run time.
# `data/raw/` is requirement 4: the fallback the live GitHub connector degrades
# to. `data/database/` is the reproducible teaching fixture the narrow SQL
# lookups query - it is queried, never embedded, so it belongs in the image
# rather than in the index volume.
COPY --chown=northstar:northstar app.py ./
COPY --chown=northstar:northstar assets/ ./assets/
COPY --chown=northstar:northstar src/ ./src/
COPY --chown=northstar:northstar scripts/build_index.py ./scripts/build_index.py
COPY --chown=northstar:northstar data/raw/ ./data/raw/
COPY --chown=northstar:northstar data/database/company.db ./data/database/company.db

USER northstar

# 8000 FastAPI · 8501 Streamlit. Publishing them to the HOST is deliberately left
# to compose, which binds both to 127.0.0.1: Streamlit binds every interface by
# default and advertised a LAN URL during step 0.3 (F-9), and an unauthenticated
# assistant whose identity is simulated should not become network-reachable by
# accident.
EXPOSE 8000 8501

# Model-free (requirement 5), and uses the interpreter rather than curl so the
# slim image needs no extra package.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "company_assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]
