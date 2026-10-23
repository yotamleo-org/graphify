"""uv.lock must not pin a version below the first patched release of any Critical or High advisory."""
import os
import re
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")

LOCK = Path(os.environ.get("GRAPHIFY_LOCK_PATH", Path(__file__).resolve().parent.parent / "uv.lock"))

# First fixed version per package, from the OSV records behind the Snyk forks scan of 2026-10-23.
FIRST_FIXED = {
    "pillow": "13.0.0",
    "cryptography": "50.0.0",
    "pypdf": "6.19.0",
    "soupsieve": "2.8.4",
}


def _key(version):
    return [int(p) for p in re.findall(r"\d+", version)]


def _locked_versions():
    data = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    out = {}
    for pkg in data["package"]:
        out.setdefault(pkg["name"], []).append(pkg["version"])
    return out


@pytest.mark.parametrize("name", sorted(FIRST_FIXED))
def test_locked_versions_are_patched(name):
    locked = _locked_versions().get(name, [])
    stale = [v for v in locked if _key(v) < _key(FIRST_FIXED[name])]
    assert not stale, f"{name} locked at {stale}, first patched release is {FIRST_FIXED[name]}"
