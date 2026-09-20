import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from adapters.cli import load_env
from agent.schema import Sender
from store.json_store import JsonStore

# The README says "put the key in .env" — pytest has to read it too, or the live tests skip.
load_env(str(Path(__file__).parent.parent / ".env"))

SEED = Path(__file__).parent / "fixtures" / "seed.json"
# Frozen clock: the Appendix B messages talk about "Sept 1" and "Sep 7" as upcoming.
NOW = datetime(2026, 8, 24, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))   # a Monday
SEED_COUNT = len(json.loads(SEED.read_text())["launches"])

ALEX = Sender("U_ALEX", "Alex Kim")            # announces the six new launches
PRIYA = Sender("U_PRIYA", "Priya Raman")       # DRI, saved views
MARCUS = Sender("U_MARCUS", "Marcus Chen")     # DRI, onboarding checklist
SAM = Sender("U_SAM", "Sam Okafor")            # DRI, connectors platform
JORDAN = Sender("U_JORDAN", "Jordan Lee")      # DRI of nothing — the hearsay sender


def seeded_store(tmp_dir: Path) -> JsonStore:
    path = tmp_dir / "calendar.json"
    shutil.copy(SEED, path)
    return JsonStore(path)


@pytest.fixture
def store(tmp_path):
    return seeded_store(tmp_path)
