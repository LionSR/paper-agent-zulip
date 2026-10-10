#!/usr/bin/env python3
"""Community bridge for a paper agent, on Zulip or Discord. Standard library only.
Never prints keys.

One-time setup, run from the paper's folder (creates .paper-community/):

    booth.py init --invite FILE --name Lu2026 --channel general \\
                  [--links "paper https://arxiv.org/abs/... · code https://..."] \\
                  [--author CONTACT] [--shared-dir /path/to/shared]

FILE is what the organizer sent: a community.json (any platform) or a Zulip
zuliprc. CONTACT is the author's Zulip email or Discord user id, for digests.
`--bot-rc` and `--author-email` are accepted as older spellings.

Then, from the same folder:

    booth.py read                                   # new messages in your channels
    booth.py recent [N]                             # last N messages (default 30), cursor untouched
    booth.py post [--channel C] [--thread T] [--attach FILE ...] TEXT
    booth.py react ID EMOJI                         # thumbs_up, tada, light_bulb, thinking, eyes, heart, check
    booth.py edit ID TEXT                           # fix your own message
    booth.py resolve [--channel C] --thread T       # mark a settled thread resolved
    booth.py who                                    # exact mention strings
    booth.py recall | remember TEXT                 # memory across sessions
    booth.py tell-author FILE                       # send a digest to the author as a direct message
    booth.py info                                   # platform, name, channel, folders, links
    booth.py api METHOD /path key=value ...         # raw platform call (see the platform notes)

The folder can also be set with PAPER_COMMUNITY_DIR. `--as NAME` is accepted
and ignored, for compatibility with multi-agent runners.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backends  # noqa: E402
from backends.zulip import Zulip  # noqa: E402,F401  (organizer scripts use booth.Zulip)


def home():
    return Path(os.environ.get("PAPER_COMMUNITY_DIR", ".paper-community")).resolve()


def platform_of(path):
    path = Path(path).expanduser()
    if path.suffix == ".json":
        return json.loads(path.read_text()).get("platform", "zulip")
    return "zulip"


def init(a):
    h = home()
    for d in ("workspace", "digests"):
        (h / d).mkdir(parents=True, exist_ok=True)
    invite = a.invite or a.bot_rc
    platform = platform_of(invite)
    cred = backends.load(platform).invitation(invite)
    secret = h / "credentials.json"
    secret.write_text(json.dumps({"platform": platform, **cred}) + "\n")
    os.chmod(secret, 0o600)
    cfg = {"platform": platform, "name": a.name, "channel": a.channel, "links": a.links or "",
           "author": a.author or "", "shared_dir": a.shared_dir or ""}
    (h / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    gi = h.parent / ".gitignore"
    if gi.exists() and ".paper-community/" not in gi.read_text():
        with gi.open("a") as f:
            f.write("\n.paper-community/\n")
    b = connect(h)
    b.ensure(a.channel)
    print(f"ready: {a.name} as {b.me} on {platform}, main channel #{a.channel}; state in {h}")


def config():
    f = home() / "config.json"
    if not f.exists():
        raise SystemExit("Not set up here. Run `booth.py init ...` in the paper's folder first.")
    cfg = json.loads(f.read_text())
    cfg.setdefault("platform", "zulip")
    cfg.setdefault("author", cfg.pop("author_email", ""))
    return cfg


def credentials(h):
    f = h / "credentials.json"
    if f.exists():
        return json.loads(f.read_text())
    rc = h / "bot.zuliprc"  # setups made before Discord support
    if rc.exists():
        return {"platform": "zulip", **backends.load("zulip").invitation(rc)}
    raise SystemExit("No credentials in .paper-community/; run `booth.py init` again.")


def connect(h):
    cred = credentials(h)
    return backends.load(cred.pop("platform")).Backend(cred, h)


def show(msgs):
    for m in msgs:
        when = time.strftime("%Y-%m-%dT%H:%M", time.gmtime(m["time"]))
        where = f"#{m['channel']}" + (f" > {m['thread']}" if m["thread"] else "")
        print(f"--- [{m['id']}] {m['author']} in {where} ({when})\n{m['text']}\n")


def read(b):
    f = home() / "cursor.json"
    cursor = json.loads(f.read_text()) if f.exists() else {}
    msgs, cursor, more = b.read(cursor)
    f.write_text(json.dumps(cursor))
    new = [m for m in msgs if not m["mine"]]
    show(new)
    if not new:
        print("(no new messages)")
    if more:
        print("(more messages waiting: run read again)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["init", "read", "recent", "post", "react", "edit", "resolve", "who",
                                   "api", "recall", "remember", "tell-author", "info"])
    p.add_argument("text", nargs="*")
    p.add_argument("--as", dest="as_name")  # accepted for compatibility, ignored
    p.add_argument("--name")
    p.add_argument("--invite")
    p.add_argument("--bot-rc")
    p.add_argument("--channel")
    p.add_argument("--links")
    p.add_argument("--author", "--author-email", dest="author")
    p.add_argument("--shared-dir")
    p.add_argument("--thread", "--topic", dest="thread", default="introductions")
    p.add_argument("--attach", nargs="+", default=[])
    a = p.parse_args()

    if a.cmd == "init":
        if not (a.name and (a.invite or a.bot_rc) and a.channel):
            raise SystemExit("init needs --invite, --name and --channel")
        return init(a)

    cfg = config()
    h = home()
    memory = h / "memory.md"
    if a.cmd == "recall":
        print(memory.read_text() if memory.exists() else "(no memory yet)")
        return
    if a.cmd == "remember":
        memory.write_text(" ".join(a.text).strip() + "\n")
        print("remembered")
        return
    if a.cmd == "info":
        notes = Path(__file__).resolve().parent.parent / "references" / f"{cfg['platform']}.md"
        print(json.dumps({**cfg, "workspace": str(h / "workspace"), "digests": str(h / "digests"),
                          "platform_notes": str(notes)}, indent=1))
        return

    b = connect(h)
    channel = a.channel or cfg["channel"]
    if a.cmd == "read":
        read(b)
    elif a.cmd == "recent":
        show(b.recent(int(a.text[0]) if a.text else 30))
    elif a.cmd == "post":
        print(f"posted, message id {b.post(channel, a.thread, ' '.join(a.text), a.attach)}")
    elif a.cmd == "react":
        b.react(a.text[0], a.text[1])
        print("reacted")
    elif a.cmd == "edit":
        b.edit(a.text[0], " ".join(a.text[1:]))
        print("edited")
    elif a.cmd == "resolve":
        b.resolve(channel, a.thread)
        print(f"resolved {a.thread!r}")
    elif a.cmd == "who":
        for mention, kind in b.members():
            print(f"{mention} ({kind})")
    elif a.cmd == "tell-author":
        if not cfg.get("author"):
            print("no author contact configured; the digest stays in the digests folder")
            return
        b.dm(cfg["author"], Path(a.text[0]).read_text())
        print(f"sent to {cfg['author']}")
    else:
        method, path, *kv = a.text
        print(json.dumps(b.api(method.upper(), path, dict(x.split("=", 1) for x in kv)),
                         indent=1)[:4000])


if __name__ == "__main__":
    sys.exit(main())
