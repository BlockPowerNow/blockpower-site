"""Minimal Typeform API client. Reads the PAT from 1Password at runtime.

The tokens in ~/.env~ are dead (403 since 2026-05-22). 1Password is canonical.
Never print the token.
"""

import json
import subprocess
import urllib.error
import urllib.request

API_ROOT = "https://api.typeform.com"
OP_ITEM = "Typeform API - Hub3 Account"
OP_VAULT = "Dev"

_TOKEN: str | None = None


def get_token() -> str:
    """Read the Typeform PAT from 1Password, once per process.

    Cached deliberately: `op` is slow and can prompt for biometrics, so calling
    it per request would prompt repeatedly.
    Never log the return value.
    """
    global _TOKEN
    if _TOKEN is not None:
        return _TOKEN
    result = subprocess.run(
        ["op", "item", "get", OP_ITEM, "--vault", OP_VAULT,
         "--fields", "credential", "--reveal"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"1Password read failed (exit {result.returncode})")
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("1Password returned an empty credential")
    _TOKEN = token
    return _TOKEN


def api(method: str, path: str, body: dict | None = None) -> dict:
    """Call the Typeform API. Raises RuntimeError on non-2xx."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_ROOT}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {get_token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} -> connection failed: {exc.reason}") from exc
