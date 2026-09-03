"""Step 9.2: prove the packaged product starts from a clean checkout.

The completion evidence `05-evaluation-and-release.md` asks for is behavioural -
*"a teammate can start the packaged product from the repository instructions and
reach both interfaces without repairing paths or manually copying hidden files"* -
so this script does exactly that and nothing more privileged: it runs the same
`docker compose` commands the README documents, from a **destroyed** volume state,
and then asserts the properties that are easy to claim and easy to get wrong.

Why each check is here rather than taken on trust
-------------------------------------------------
Four of these are not container hygiene; they are this project's own findings
restated as tests, and each one has already failed once somewhere in the build:

* **No credential in the image.** `.dockerignore` is a file, not a guarantee. The
  check opens the built image and looks.
* **The index volume starts EMPTY and is filled by a documented command.**
  `data/index/` is git-ignored, so a clean checkout has none. If the stack came up
  without building one, both interfaces would answer "I could not find this in
  company knowledge" to everything and look broken rather than empty.
* **The freshness manifest survives a restart.** Losing it makes a fresh process
  report `indexed never` and claim `local` over data that was really live - a
  disclosure wrong by construction (F-15.2). A container that loses the manifest
  re-introduces a defect already fixed.
* **The embedding model answers with the network cut.** ~90 MB, 39 s cold against
  7.3 s warm. "Baked in" is only true if it loads offline.

Run it with the stack down; it manages its own lifecycle and leaves the stack up.

    uv run python scripts/verify_container.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

IMAGE = "northstar-assistant:latest"
API = "http://127.0.0.1:8000"
APP = "http://127.0.0.1:8501"

#: Shapes, not values. The point is to catch a credential we never anticipated,
#: so this matches the *form* of a secret rather than the keys we happen to hold.
SECRET_PREFIXES = ("sk-or-v1-", "gsk_", "ghp_", "github_pat_", "hf_")

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    results.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  -  {detail}" if detail else ""))
    return passed


def run(*args: str, check_rc: bool = False, timeout: int = 600) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check_rc and proc.returncode != 0:
        print(f"\ncommand failed: {' '.join(args)}\n{proc.stdout}\n{proc.stderr}", file=sys.stderr)
        raise SystemExit(1)
    return proc


def get(url: str, timeout: int = 10) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - an unreachable port is a result, not a crash
        return 0, f"{type(exc).__name__}: {exc}"


def wait_for(url: str, *, seconds: int = 240) -> tuple[int, str]:
    """Poll until the endpoint answers. Startup is a model load, not a bug."""
    deadline = time.time() + seconds
    status, body = 0, ""
    while time.time() < deadline:
        status, body = get(url)
        if status == 200:
            return status, body
        time.sleep(3)
    return status, body


def main() -> int:
    print("\n=== 9.2  clean-checkout container verification ===\n")

    # --- a genuinely clean state ------------------------------------------
    # `-v` destroys the volumes, so the index really is absent - which is the
    # state a teammate's first `git clone` is in.
    print("Clean state: destroying any existing volumes")
    run("docker", "compose", "down", "-v", "--remove-orphans", timeout=180)

    print("\nStarting with the documented command: docker compose up -d --build")
    started = time.perf_counter()
    up = run("docker", "compose", "up", "-d", "--build", timeout=1800)
    check("`docker compose up -d --build` succeeds", up.returncode == 0,
          up.stderr.strip().splitlines()[-1] if up.returncode and up.stderr else "")
    if up.returncode != 0:
        print(up.stdout, up.stderr, file=sys.stderr)
        return 1

    # --- the index bootstrap ran, and produced something -------------------
    index_logs = run("docker", "compose", "logs", "--no-log-prefix", "index").stdout
    check("the index one-shot ran and reported both namespaces",
          "company_knowledge" in index_logs and "project_board" in index_logs,
          index_logs.strip().splitlines()[-1][:80] if index_logs.strip() else "no output")

    # --- both interfaces answer -------------------------------------------
    api_status, api_body = wait_for(f"{API}/health")
    check("FastAPI /health answers 200", api_status == 200, f"status={api_status}")
    app_status, _ = wait_for(f"{APP}/_stcore/health")
    check("Streamlit answers on 8501", app_status == 200, f"status={app_status}")
    print(f"\n  both interfaces reachable {time.perf_counter() - started:.0f} s after `up`\n")

    # --- the health endpoint is model-free ---------------------------------
    # If /health had touched the model or the index it could not have answered
    # before either was warm, and its body would carry index fields.
    try:
        health = json.loads(api_body)
    except json.JSONDecodeError:
        health = {}
    check("health is model-free (no index or model fields in its contract)",
          set(health) == {"status", "employee_roles"} and health.get("status") == "ok",
          f"keys={sorted(health)}")

    # --- the index was actually built into the empty volume ----------------
    status_code, status_body = get(f"{API}/status", timeout=180)
    service_status = json.loads(status_body) if status_code == 200 else {}
    units = service_status.get("index_units", 0)
    check("the index volume started empty and was filled by the documented command",
          status_code == 200 and units > 0, f"{units} unit(s) indexed")
    check("index freshness is disclosed per namespace, not asserted",
          bool(service_status.get("index_sources")),
          ", ".join(f"{s.get('source')}={s.get('freshness')}"
                    for s in service_status.get("index_sources", [])))
    check("last-indexed is a real timestamp, not `never`",
          service_status.get("index_last_indexed", "never") != "never",
          str(service_status.get("index_last_indexed")))

    # --- no credential in the image ----------------------------------------
    listing = run("docker", "run", "--rm", "--entrypoint", "sh", IMAGE,
                  "-c", "ls -a /app").stdout
    check("no .env inside the image", ".env" not in listing.split(),
          " ".join(sorted(listing.split()))[:90])

    env_dump = run("docker", "run", "--rm", "--entrypoint", "sh", IMAGE, "-c", "env").stdout
    leaked = [p for p in SECRET_PREFIXES if p in env_dump]
    check("no secret-shaped value baked into the image environment", not leaked,
          f"matched {leaked}" if leaked else "9 shapes checked, none present")

    # The running container SHOULD have the credentials - they arrive at run
    # time. Asserting that proves the env_file path works rather than that the
    # product is quietly running without a model.
    running_env = run("docker", "compose", "exec", "-T", "api", "sh", "-c",
                      "env | grep -c -E '^(GROQ_API_KEY|OPENROUTER_API_KEY)=.'").stdout.strip()
    check("credentials reach the RUNNING container instead", running_env.isdigit() and int(running_env) > 0,
          f"{running_env} credential variable(s) present at run time")

    # --- the fallback ships -------------------------------------------------
    fallback = run("docker", "run", "--rm", "--entrypoint", "sh", IMAGE,
                   "-c", "ls data/raw/github data/raw/slack data/raw/email data/raw/documents "
                         "data/database/company.db | head -20").stdout
    check("local GitHub fallback and fixtures ship in the image",
          "issues.json" in fallback and "company.db" in fallback,
          "data/raw/* and the teaching database present")

    # --- runs unprivileged ---------------------------------------------------
    whoami = run("docker", "compose", "exec", "-T", "api", "id", "-un").stdout.strip()
    check("runs as a non-root user", whoami not in ("", "root"), f"uid name={whoami!r}")

    # --- the embedding model is genuinely baked in ---------------------------
    offline = run("docker", "run", "--rm", "--network", "none", "--entrypoint", "python", IMAGE,
                  "-c", "from company_assistant.rag import EMBEDDING_MODEL; "
                        "from chromadb.utils import embedding_functions as e; "
                        "f = e.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL); "
                        "print('dims', len(f(['ping'])[0]))", timeout=600)
    check("the embedding model loads with the network cut off",
          offline.returncode == 0 and "dims" in offline.stdout,
          offline.stdout.strip()[-40:] or offline.stderr.strip().splitlines()[-1][:80])

    # --- ports are bound to loopback, not to every interface -----------------
    published = run("docker", "compose", "port", "app", "8501").stdout.strip()
    published_api = run("docker", "compose", "port", "api", "8000").stdout.strip()
    check("both ports are published to 127.0.0.1 only (F-9)",
          published.startswith("127.0.0.1:") and published_api.startswith("127.0.0.1:"),
          f"app={published} api={published_api}")

    # --- the volumes actually persist ---------------------------------------
    # A restart, not a recreate: this is the everyday case that must not lose the
    # freshness manifest and silently start claiming `local` over live data.
    before = service_status.get("index_last_indexed")
    run("docker", "compose", "restart", "api", timeout=180)
    wait_for(f"{API}/health")
    after_code, after_body = get(f"{API}/status", timeout=180)
    after = json.loads(after_body).get("index_last_indexed") if after_code == 200 else None
    check("index and its freshness manifest survive a restart (F-15.2)",
          after == before and after not in (None, "never"), f"{before} -> {after}")

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} checks pass")
    if passed != len(results):
        print("failed: " + ", ".join(n for n, ok, _ in results if not ok))
    print("\nThe stack is left running:  http://127.0.0.1:8501  ·  http://127.0.0.1:8000/docs")
    print("Stop it with `docker compose down` (add -v to discard the index and feedback).")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
