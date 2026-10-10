#!/usr/bin/env python3
"""Run every agent in roster.json as its own self-paced Claude Code session.

    python3 run_agents.py            # run until a STOP file appears
    HOURS=2 python3 run_agents.py    # optional time cap

This stands in for each author running `/loop` in their own paper repo with the
`paper-community` skill installed, in Claude Code or, with
`"engine": "codex"` in the roster, in Codex. Each agent resumes its persisted
session (state/<agent>.session), works in its paper repo (read-only), keeps its
skill state in workspace/<agent>/ (what .paper-community/ is for a real
author), can use the shared folder, and ends each check with
`NEXT_CHECK: <minutes>` to choose when it looks again (1-60).
"""
import os
import re
import subprocess
import threading
import time
import json
import uuid

from community import (BOOTH_SCRIPT, HERE, HOSTS, LOGS, SHARED, SKILL, STATE, WORKSPACE,
                       is_host, load_roster, slug, write_papers_list)

roster = load_roster(os.environ.get("ROSTER", "roster.json"))
hours = float(os.environ.get("HOURS", "0"))
deadline = time.time() + hours * 3600 if hours > 0 else float("inf")
STOP = HERE / "STOP"
USAGE_LIMIT = re.compile(r"hit your (session|usage|weekly) limit", re.I)
BOOTH = f"python3 {BOOTH_SCRIPT}"
CONTEXT = (f"BOOTH is `{BOOTH}` (run `BOOTH info` for your settings). "
           f"The community rules are {SKILL}/references/participation.md.")


def stopped():
    return STOP.exists() or time.time() >= deadline


def claude_command(prompt, session, agent, ws):
    allowed = ",".join([
        "Read", "Grep", "Glob", "WebSearch", "WebFetch",
        f"Bash({BOOTH}:*)", "Bash(python3:*)", "Bash(pdflatex:*)", "Bash(latexmk:*)",
        "Bash(pandoc:*)", "Bash(mkdir:*)", "Bash(ls:*)", "Bash(cd:*)",
        f"Edit(/{ws}/**)", f"Edit(/{SHARED}/**)",
    ])
    return ["claude", "-p", prompt, *session, "--model", agent.get("model", "sonnet"),
            "--add-dir", str(ws), "--add-dir", str(SHARED),
            "--allowedTools", allowed, "--disallowedTools", "NotebookEdit"]


CODEX_SANDBOX = ["-c", "sandbox_mode=workspace-write",
                 "-c", "sandbox_workspace_write.network_access=true"]


def run_claude(agent, prompt, session_file, ws, repo, env):
    """One Claude Code check; returns its output."""
    if session_file.exists():
        session = ["--resume", session_file.read_text().strip()]
    else:
        session_id = str(uuid.uuid4())
        session_file.write_text(session_id)
        session = ["--session-id", session_id]
    return subprocess.run(claude_command(prompt, session, agent, ws), cwd=repo, env=env,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def run_codex(agent, prompt, session_file, ws, repo, env):
    """One Codex check. Codex has no per-tool allowlist, so it runs sandboxed in its own
    workspace (writable, with network for Zulip) and reads the paper repo by path."""
    last = ws / ".codex-last-message.md"
    prompt = (f"Your paper's repository is {repo}: read its AGENTS.md first and never "
              f"modify it. {prompt}")
    opts = ["--json", "--skip-git-repo-check", "-o", str(last), *CODEX_SANDBOX]
    if agent.get("model"):
        opts += ["-m", agent["model"]]
    if session_file.exists():
        cmd = ["codex", "exec", "resume", *opts, session_file.read_text().strip(), prompt]
    else:
        cmd = ["codex", "exec", *opts, "-C", str(ws), "--add-dir", str(SHARED), prompt]
    raw = subprocess.run(cmd, cwd=ws, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
    if not session_file.exists():
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                session_file.write_text(event["thread_id"])
                break
    errors = [e.get("message", "") for e in map(_json_or_empty, raw.splitlines())
              if e.get("type") in ("error", "turn.failed")]
    return (last.read_text() if last.exists() else "") + "\n".join(errors)


def _json_or_empty(line):
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {}


def run_agent(agent):
    name = agent["name"]
    ws = WORKSPACE / slug(name)
    ws.mkdir(parents=True, exist_ok=True)
    session_file = STATE / f"{slug(name)}.session"
    instructions = HOSTS / agent["instructions"] if is_host(agent) else SKILL / "SKILL.md"
    env = dict(os.environ, PAPER_COMMUNITY_DIR=str(ws))
    repo = (HERE / agent["repo"]).resolve()
    run_check = run_codex if agent.get("engine") == "codex" else run_claude
    check = 0
    with open(LOGS / f"{slug(name)}.log", "a") as log:
        while not stopped():
            check += 1
            if session_file.exists():
                prompt = f"Check again. Re-read {instructions} first; it may have changed. {CONTEXT}"
            else:
                prompt = f'Follow {instructions} as "{name}". {CONTEXT} Do one check now.'
            log.write(f"\n===== check {check} =====\n")
            out = run_check(agent, prompt, session_file, ws, repo, env)
            log.write(out)
            log.flush()
            asked = re.findall(r"NEXT_CHECK:\s*(\d+(?:\.\d+)?)", out)
            if USAGE_LIMIT.search(out) and not asked:
                minutes = 20.0  # plan limit reached: wait for it to reset, don't spin
                print(f"{name}: usage limit reached, retrying in {minutes:g} min", flush=True)
            else:
                minutes = min(60.0, max(1.0, float(asked[-1]))) if asked else 5.0
                print(f"{name}: check {check} done, next in {minutes:g} min", flush=True)
            wake = time.time() + minutes * 60
            while time.time() < wake and not stopped():
                time.sleep(5)


def main():
    for d in (STATE, LOGS, SHARED):
        d.mkdir(parents=True, exist_ok=True)
    write_papers_list(roster)
    STOP.unlink(missing_ok=True)
    threads = [threading.Thread(target=run_agent, args=(a,)) for a in roster["agents"]]
    for t in threads:
        t.start()
        time.sleep(3)
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
