"""Frozen evidence for historical LIVE/reducer replays; not the current KB."""
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_KB_ROOT = PROJECT_ROOT / "tests/fixtures/kb_pre_b2"
