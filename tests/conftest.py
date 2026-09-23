import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "automation" / "inventory.yml"
CONFIGS = ROOT / "configs"


@pytest.fixture(scope="session")
def inventory():
    return yaml.safe_load(INVENTORY.read_text())


@pytest.fixture(scope="session")
def rendered(inventory):
    """Render from the current inventory and return {hostname: text}.

    Rendering rather than reading configs/ from disk means the tests check
    what the generator produces now, not what happened to be committed.
    """
    subprocess.run(
        [sys.executable, str(ROOT / "automation" / "render.py")],
        cwd=ROOT, check=True, capture_output=True,
    )
    return {p.stem: p.read_text() for p in CONFIGS.glob("*.cfg")}
