"""Settings read from the environment, in one place."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# name -> (parser, default). A default of None means the variable is required.
_VARS = {
    "ANTHROPIC_API_KEY": (str, None),
    "AGENT_MODEL": (str, "claude-sonnet-5-5"),
    "JUDGE_MODEL": (str, "claude-sonnet-5-5"),
    "PRICE_IN_PER_MTOK": (float, None),
    "PRICE_OUT_PER_MTOK": (float, None),
    "DATABASE_URL": (str, None),
    "HUBSPOT_TOKEN": (str, None),
    "HUBSPOT_PORTAL_ID": (str, None),
}


def __getattr__(name: str) -> str | float:
    # Values are read on access, so a script only fails on the variables it actually uses.
    if name not in _VARS:
        raise AttributeError(f"module 'config' has no attribute {name!r}")
    parse, default = _VARS[name]
    raw = os.environ.get(name, "").strip()
    if not raw:
        if default is None:
            raise RuntimeError(f"{name} is not set. Add it to .env (see .env.example).")
        return default
    try:
        return parse(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a number, got {raw!r}.") from None
