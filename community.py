"""Shared paths and helpers for the organizer scripts (run_agents.py, setup_zulip.py).

The Zulip client itself lives in the skill (skills/zulip-paper-community/scripts/booth.py),
so authors and organizers use the same code.
"""
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE / "skills" / "zulip-paper-community"
BOOTH_SCRIPT = SKILL / "scripts" / "booth.py"
HOSTS = HERE / "hosts"
KEYS = HERE / "zulip"
WORKSPACE = HERE / "workspace"
SHARED = WORKSPACE / "shared"
STATE = HERE / "state"
LOGS = HERE / "logs"


def load_roster(name="roster.json"):
    return json.loads((HERE / name).read_text())


def slug(name):
    """Folder-safe form of an agent name, e.g. 'Du2025 (sim)' -> 'Du2025-sim'."""
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")


def is_host(agent):
    """Hosts (Moderator, Referee) have their own instructions; paper agents use the skill."""
    return bool(agent.get("instructions"))


def zulip_client(rc_path):
    """The skill's Zulip client, loaded from booth.py."""
    spec = importlib.util.spec_from_file_location("booth", BOOTH_SCRIPT)
    booth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(booth)
    return booth.Zulip(rc_path)


def write_papers_list(roster):
    """hosts/PAPERS.md: every paper agent with its links and repo, for the hosts to read."""
    lines = ["# Papers in this community", "",
             "Read any of these repos directly (read-only). Each has an AGENTS.md and paper/.", ""]
    for a in roster["agents"]:
        if not is_host(a):
            lines.append(f"- **{a['name']}**: {a.get('links', '')}  \n"
                         f"  repo: `{(HERE / a['repo']).resolve()}`")
    (HOSTS / "PAPERS.md").write_text("\n".join(lines) + "\n")
