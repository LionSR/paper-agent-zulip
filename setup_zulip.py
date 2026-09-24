#!/usr/bin/env python3
"""Organizer tools, using zulip/admin.zuliprc. Never prints keys.

    setup_zulip.py bots                  # create a Generic bot per roster agent
    setup_zulip.py retire SHORT ...      # deactivate bots, e.g. kitp-zhao
    setup_zulip.py archive CHANNEL ...   # archive channels
    setup_zulip.py papers                # regenerate hosts/PAPERS.md
"""
import os
import sys
from pathlib import Path

from zulip_api import HERE, ZULIP, Client, load_roster


def bots(admin, roster):
    for a in roster["agents"]:
        out = ZULIP / f"{a['short']}.zuliprc"
        if out.exists():
            print(f"{a['name']}: already set up")
            continue
        r = admin.call("POST", "/bots", {"full_name": a.get("display", a["name"])[:100],
                                         "short_name": a["short"], "bot_type": 1})
        email = admin.call("GET", f"/users/{r['user_id']}")["user"]["email"]
        out.write_text(f"[api]\nemail={email}\nkey={r['api_key']}\nsite={admin.site}\n")
        os.chmod(out, 0o600)
        print(f"{a['name']}: created ({email})")


def retire(admin, shorts):
    for u in admin.call("GET", "/users")["members"]:
        short = u["email"].split("-bot@")[0]
        if u["is_bot"] and u["is_active"] and short in shorts:
            admin.call("DELETE", f"/bots/{u['user_id']}")
            (ZULIP / f"{short}.zuliprc").unlink(missing_ok=True)
            print(f"retired {u['full_name']}")


def archive(admin, names):
    for s in admin.call("GET", "/streams")["streams"]:
        if s["name"] in names:
            admin.call("DELETE", f"/streams/{s['stream_id']}")
            print(f"archived #{s['name']}")


def papers(roster):
    lines = ["# Papers in this community", "",
             "Read any of these repos directly (read-only). Each has an AGENTS.md and paper/.", ""]
    for a in roster["agents"]:
        if a.get("attend"):
            continue  # hosts (Moderator, Referee), not papers
        lines.append(f"- **{a['name']}**: {a.get('links', '')}  \n"
                     f"  repo: `{(HERE / a['repo']).resolve()}`")
    (HERE / "hosts" / "PAPERS.md").write_text("\n".join(lines) + "\n")
    print("wrote hosts/PAPERS.md")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    roster = load_roster(os.environ.get("ROSTER", "roster.json"))
    if cmd == "papers":
        return papers(roster)
    admin = Client.admin()
    {"bots": lambda: bots(admin, roster),
     "retire": lambda: retire(admin, set(args)),
     "archive": lambda: archive(admin, set(args))}[cmd]()


if __name__ == "__main__":
    main()
