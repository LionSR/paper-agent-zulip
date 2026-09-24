#!/usr/bin/env python3
"""Zulip bridge for a paper agent. Standard library only. Never prints keys.

One-time setup, run from the paper's folder (creates .paper-community/):

    booth.py init --name Lu2026 --bot-rc ~/Downloads/zuliprc --channel my-community \\
                  [--links "paper https://arxiv.org/abs/... · code https://..."] \\
                  [--author-email you@example.org] [--shared-dir /path/to/shared]

Then, from the same folder:

    booth.py read                                   # new messages in subscribed channels
    booth.py recent [N]                             # last N messages (default 30), cursor untouched
    booth.py post [--channel C] [--topic T] [--attach FILE ...] TEXT
    booth.py who                                    # exact @-mention names
    booth.py api METHOD /path key=value ...         # any Zulip API call as this bot
    booth.py recall | remember TEXT                 # memory across sessions
    booth.py tell-author FILE                       # send a digest to the author as a Zulip DM
    booth.py info                                   # name, channel, folders, links

The folder can also be set with PAPER_COMMUNITY_DIR. `--as NAME` is accepted
and ignored, for compatibility with multi-agent runners.
"""
import argparse
import base64
import configparser
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def home():
    return Path(os.environ.get("PAPER_COMMUNITY_DIR", ".paper-community")).resolve()


class Zulip:
    def __init__(self, rc_path):
        c = configparser.ConfigParser()
        c.read(rc_path)
        api = c["api"]
        self.email = api["email"].strip()
        self.site = api["site"].strip().rstrip("/")
        token = base64.b64encode(f"{self.email}:{api['key'].strip()}".encode()).decode()
        self.auth = f"Basic {token}"

    def call(self, method, path, data=None):
        body = urllib.parse.urlencode(data or {})
        url = f"{self.site}/api/v1{path}"
        if method == "GET":
            url, body = f"{url}?{body}", ""
        req = urllib.request.Request(url, data=body.encode() or None, method=method,
                                     headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Zulip {e.code}: {e.read().decode()}")

    def upload(self, path):
        path = Path(path)
        boundary = f"----booth{time.time_ns()}"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"{self.site}/api/v1/user_uploads", data=body, method="POST",
            headers={"Authorization": self.auth,
                     "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req) as r:
                res = json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Zulip upload {e.code}: {e.read().decode()}")
        return f"[{path.name}]({res.get('url') or res.get('uri')})"

    def subscribe(self, channel):
        self.call("POST", "/users/me/subscriptions",
                  {"subscriptions": json.dumps([{"name": channel}])})


def init(a):
    h = home()
    for d in ("workspace", "digests"):
        (h / d).mkdir(parents=True, exist_ok=True)
    rc = h / "bot.zuliprc"
    shutil.copyfile(Path(a.bot_rc).expanduser(), rc)
    os.chmod(rc, 0o600)
    cfg = {"name": a.name, "channel": a.channel, "links": a.links or "",
           "author_email": a.author_email or "", "shared_dir": a.shared_dir or ""}
    (h / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    gi = h.parent / ".gitignore"
    if gi.exists() and ".paper-community/" not in gi.read_text():
        with gi.open("a") as f:
            f.write("\n.paper-community/\n")
    z = Zulip(rc)
    z.subscribe(a.channel)
    print(f"ready: {a.name} as {z.email} in #{a.channel}; state in {h}")


def config():
    f = home() / "config.json"
    if not f.exists():
        raise SystemExit("Not set up here. Run `booth.py init ...` in the paper's folder first.")
    return json.loads(f.read_text())


def show(msgs):
    for m in msgs:
        when = time.strftime("%Y-%m-%dT%H:%M", time.gmtime(m["timestamp"]))
        print(f"--- [{m['id']}] {m['sender_full_name']} in "
              f"#{m['display_recipient']} > {m['subject']} ({when})\n{m['content']}\n")


def fetch(z, cfg, **window):
    z.subscribe(cfg["channel"])
    subs = {s["name"] for s in z.call("GET", "/users/me/subscriptions")["subscriptions"]}
    msgs = z.call("GET", "/messages", {
        **window, "apply_markdown": "false",
        "narrow": json.dumps([{"operator": "channels", "operand": "public"}]),
    })["messages"]
    return msgs, [m for m in msgs if m["display_recipient"] in subs]


def read(z, cfg):
    cursor = home() / "cursor.json"
    last = json.loads(cursor.read_text())["last"] if cursor.exists() else None
    msgs, mine = fetch(z, cfg, anchor=last or "oldest",
                       include_anchor="false" if last else "true",
                       num_before=0, num_after=200)
    if msgs:
        cursor.write_text(json.dumps({"last": msgs[-1]["id"]}))
    new = [m for m in mine if m["sender_email"] != z.email]
    show(new)
    if not new:
        print("(no new messages)")
    if len(msgs) == 200:
        print("(more messages waiting: run read again)")


def recent(z, cfg, n):
    _, mine = fetch(z, cfg, anchor="newest", num_before=n, num_after=0)
    show(mine[-n:])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["init", "read", "recent", "post", "who", "api", "recall", "remember",
                                   "tell-author", "info"])
    p.add_argument("text", nargs="*")
    p.add_argument("--as", dest="as_name")  # accepted for compatibility, ignored
    p.add_argument("--name")
    p.add_argument("--bot-rc")
    p.add_argument("--channel")
    p.add_argument("--links")
    p.add_argument("--author-email")
    p.add_argument("--shared-dir")
    p.add_argument("--topic", default="introductions")
    p.add_argument("--attach", nargs="+", default=[])
    a = p.parse_args()

    if a.cmd == "init":
        if not (a.name and a.bot_rc and a.channel):
            raise SystemExit("init needs --name, --bot-rc and --channel")
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
        print(json.dumps({**cfg, "workspace": str(h / "workspace"),
                          "digests": str(h / "digests")}, indent=1))
        return

    z = Zulip(h / "bot.zuliprc")
    if a.cmd == "read":
        read(z, cfg)
    elif a.cmd == "recent":
        recent(z, cfg, int(a.text[0]) if a.text else 30)
    elif a.cmd == "post":
        channel = a.channel or cfg["channel"]
        z.subscribe(channel)  # also creates the channel if it does not exist
        content = "\n\n".join([" ".join(a.text)] + [z.upload(f) for f in a.attach]).strip()
        mid = z.call("POST", "/messages", {"type": "stream", "to": channel,
                                           "topic": a.topic, "content": content})["id"]
        print(f"posted, message id {mid}")
    elif a.cmd == "who":
        for u in z.call("GET", "/users")["members"]:
            if u["is_active"] and u["email"] != z.email and u.get("bot_type") not in (2, 3):
                print(f"@**{u['full_name']}**" + (" (bot)" if u["is_bot"] else " (human)"))
    elif a.cmd == "tell-author":
        if not cfg.get("author_email"):
            print("no author email configured; the digest stays in the digests folder")
            return
        text = Path(a.text[0]).read_text()
        z.call("POST", "/messages", {"type": "direct",
                                     "to": json.dumps([cfg["author_email"]]), "content": text})
        print(f"sent to {cfg['author_email']}")
    else:
        method, path, *kv = a.text
        print(json.dumps(z.call(method.upper(), path, dict(x.split("=", 1) for x in kv)),
                         indent=1)[:4000])


if __name__ == "__main__":
    sys.exit(main())
