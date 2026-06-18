"""Consistency checks for the Docker / docker-compose stack.

These are static assertions over the Dockerfiles, compose file, nginx config and
the one application-code touchpoint (`ui/src/App.jsx`). They guard against the
kinds of drift that silently break a containerized deploy — a port that no
longer lines up across server/Dockerfile/compose, a secret accidentally baked
into an image, or the frontend losing its build-time API base URL.

They are pure file reads (no Docker daemon required) so they run anywhere CI
runs the rest of the suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The port the backend binds and that everything else must agree on.
BACKEND_PORT = 8765


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── presence ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel",
    [
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "ui/Dockerfile",
        "ui/nginx.conf",
        "ui/.dockerignore",
    ],
)
def test_docker_artifact_exists(rel: str) -> None:
    assert (ROOT / rel).is_file(), f"missing Docker artifact: {rel}"


# ── backend Dockerfile ──────────────────────────────────────────────────────────


def test_backend_port_is_consistent_everywhere() -> None:
    """server.py, the backend Dockerfile EXPOSE/CMD, and compose must agree."""
    server = _read("server.py")
    assert f"port={BACKEND_PORT}" in server.replace(" ", "")

    dockerfile = _read("Dockerfile")
    assert f"EXPOSE {BACKEND_PORT}" in dockerfile
    assert f'"{BACKEND_PORT}"' in dockerfile  # uvicorn --port in CMD

    compose = _read("docker-compose.yml")
    assert f'"{BACKEND_PORT}:{BACKEND_PORT}"' in compose


def test_backend_runs_uvicorn_without_reload() -> None:
    dockerfile = _read("Dockerfile")
    assert "uvicorn" in dockerfile and "server:app" in dockerfile
    # Inspect only instruction lines, not comments (which may mention --reload).
    instructions = "\n".join(
        ln for ln in dockerfile.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "--reload" not in instructions, "production image must not use --reload"


def test_backend_bundles_chromium() -> None:
    dockerfile = _read("Dockerfile")
    assert "playwright install --with-deps chromium" in dockerfile


def test_backend_hf_cache_path_matches_compose_volume() -> None:
    """HF_HOME must point at the path the named cache volume mounts."""
    dockerfile = _read("Dockerfile")
    m = re.search(r"HF_HOME=(\S+)", dockerfile)
    assert m, "HF_HOME not set in backend Dockerfile"
    hf_home = m.group(1)

    compose = _read("docker-compose.yml")
    assert f"hf-cache:{hf_home}" in compose, (
        "hf-cache volume mount must match HF_HOME"
    )


# ── frontend Dockerfile ─────────────────────────────────────────────────────────


def test_frontend_uses_lockfile_install_and_build() -> None:
    dockerfile = _read("ui/Dockerfile")
    assert "npm ci" in dockerfile, "use reproducible lockfile install (npm ci)"
    assert "npm run build" in dockerfile


def test_frontend_threads_api_base_url_build_arg() -> None:
    """The build arg must be declared and promoted to an env var for Vite."""
    dockerfile = _read("ui/Dockerfile")
    assert "ARG VITE_API_BASE_URL" in dockerfile
    assert "ENV VITE_API_BASE_URL=$VITE_API_BASE_URL" in dockerfile


def test_compose_passes_api_base_url_with_localhost_default() -> None:
    compose = _read("docker-compose.yml")
    assert (
        f'VITE_API_BASE_URL: "${{VITE_API_BASE_URL:-http://localhost:{BACKEND_PORT}}}"'
        in compose
    )


# ── application touchpoint ──────────────────────────────────────────────────────


def test_app_jsx_reads_build_time_api_url_with_fallback() -> None:
    app = _read("ui/src/App.jsx")
    assert (
        'const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8765";'
        in app
    )


# ── nginx ────────────────────────────────────────────────────────────────────


def test_nginx_has_spa_fallback() -> None:
    conf = _read("ui/nginx.conf")
    assert "try_files $uri $uri/ /index.html;" in conf


# ── secret / state hygiene ──────────────────────────────────────────────────────


@pytest.mark.parametrize("pattern", [".env", "data/"])
def test_root_dockerignore_excludes_secrets_and_state(pattern: str) -> None:
    """Never bake the user's keys (.env) or writable state (data/) into the image."""
    lines = {ln.strip() for ln in _read(".dockerignore").splitlines()}
    assert pattern in lines, f".dockerignore must exclude {pattern!r}"


@pytest.mark.parametrize("pattern", ["node_modules", "dist"])
def test_ui_dockerignore_excludes_build_artifacts(pattern: str) -> None:
    lines = {ln.strip() for ln in _read("ui/.dockerignore").splitlines()}
    assert pattern in lines, f"ui/.dockerignore must exclude {pattern!r}"
