"""FRIDAY Core: the laptop brain (fast path, tools, memory, voice, phone gateway)."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # E:\friday
DATA = ROOT / "data"                                  # git-ignored runtime state
CONFIG = tomllib.loads((ROOT / "core" / "config" / "friday.toml").read_text(encoding="utf-8"))
