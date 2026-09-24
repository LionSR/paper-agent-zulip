#!/usr/bin/env python3
"""Run every agent in roster.json as its own self-paced Claude Code session.

    python3 run_agents.py            # run until a STOP file appears
    HOURS=2 python3 run_agents.py    # optional time cap

This stands in for each author running `/loop` in their own paper repo with the
`zulip-paper-community` skill installed. Every agent resumes its persisted
session (state/<agent>.session), works in its paper repo (read-only), keeps its
skill state in workspace/<agent>/ (as .paper-community/ would be for a real
author), can use the shared folder, and ends each check with
`NEXT_CHECK: <minutes>` to choose when it looks again (1-60).
"""
import os
import re
import subprocess
import threading
import time
import uuid

from zulip_api import HERE, load_roster

ROSTER = os.environ.get("ROSTER", "roster.json")
roster = load_roster(ROSTER)
hours = float(os.environ.get("HOURS", "0"))
deadline = time.time() + hours * 3600 if hours > 0 else float("inf")
STOP = HERE / "STOP"
SKILL = HERE / "skills" / "zulip-paper-community"
BOOTH = f"python3 {SKILL}/scripts/booth.py"
SHARED = HERE / "workspace" / "shared"



def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")


def stopped():
    return STOP.exists() or time.time() >= deadline


def run_agent(a):
    s = slug(a["name"])
    ws = HERE / "workspace" / s
    ws.mkdir(parents=True, exist_ok=True)
    session_file = HERE / "state" / f"{s}.session"
    host = a.get("attend")  # Moderator/Referee instructions; paper agents use the skill
    instructions = HERE / "prompts" / host if host else SKILL / "SKILL.md"
    env = dict(os.environ, PAPER_COMMUNITY_DIR=str(ws))
    context = (f"BOOTH is `{BOOTH}` (run `BOOTH info` for your settings). "
               f"The community rules are {SKILL}/references/participation.md.")
    allowed = ",".join(["Read", "Grep", "Glob", f"Bash({BOOTH}:*)",
                        f"Edit(/{ws}/**)", f"Edit(/{SHARED}/**)", "Bash(python3:*)",
                        "Bash(pdflatex:*)", "Bash(latexmk:*)", "Bash(pandoc:*)",
                        "Bash(mkdir:*)", "Bash(ls:*)", "Bash(cd:*)",
                        "WebSearch", "WebFetch"])
    check = 0
    with open(HERE / "logs" / f"{s}.log", "a") as log:
        while not stopped():
            check += 1
            if session_file.exists():
                session = ["--resume", session_file.read_text().strip()]
                prompt = f"Check again. Re-read {instructions} first; it may have changed. {context}"
            else:
                sid = str(uuid.uuid4())
                session_file.write_text(sid)
                session = ["--session-id", sid]
                prompt = f'Follow {instructions} as "{a["name"]}". {context} Do one check now.'
            log.write(f"\n===== check {check} =====\n")
            out = subprocess.run(
                ["claude", "-p", prompt, *session, "--model", a.get("model", "sonnet"),
                 "--add-dir", str(ws), "--add-dir", str(SHARED),
                 "--allowedTools", allowed,
                 "--disallowedTools", "NotebookEdit"],
                cwd=(HERE / a["repo"]).resolve(), env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
            log.write(out)
            log.flush()
            asked = re.findall(r"NEXT_CHECK:\s*(\d+(?:\.\d+)?)", out)
            minutes = min(60.0, max(1.0, float(asked[-1]))) if asked else 5.0
            print(f"{a['name']}: check {check} done, next in {minutes:g} min", flush=True)
            wake = time.time() + minutes * 60
            while time.time() < wake and not stopped():
                time.sleep(5)


def main():
    for d in ("state", "logs"):
        (HERE / d).mkdir(exist_ok=True)
    SHARED.mkdir(parents=True, exist_ok=True)
    STOP.unlink(missing_ok=True)
    threads = [threading.Thread(target=run_agent, args=(a,)) for a in roster["agents"]]
    for t in threads:
        t.start()
        time.sleep(3)
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
