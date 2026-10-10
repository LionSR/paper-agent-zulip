"""Discord backend: a channel is a forum channel (or a text channel), a thread is
a forum post (or a thread in the text channel).

The bot needs the Message Content intent, ideally the Server Members intent
(for `who`), and in the server: View Channels, Read Message History, Send
Messages, Send Messages in Threads, Create Public Threads, Attach Files, Add
Reactions, Embed Links, Manage Threads (to mark threads resolved) and Manage
Channels (to open collaboration channels).
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from backends import EMOJI

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/LionSR/paper-agent-community, 1.0)"
LIMIT = 1900          # Discord caps a message at 2000 characters
EPOCH_MS = 1420070400000
TEXT, FORUM = 0, 15
INDEX_KEEP = 5000


def invitation(path):
    """community.json with platform "discord", the bot token and the server (guild) id."""
    d = json.loads(Path(path).expanduser().read_text())
    return {"token": d["token"], "guild": str(d["guild"])}


def chunks(text):
    """Split at paragraph or line breaks so no piece exceeds the limit."""
    out, cur = [], ""
    for para in re.split(r"(\n\n|\n)", text):
        if len(cur) + len(para) > LIMIT and cur:
            out.append(cur)
            cur = ""
        while len(para) > LIMIT:
            out.append(para[:LIMIT])
            para = para[LIMIT:]
        cur += para
    if cur.strip() or not out:
        out.append(cur)
    return [c.strip() for c in out if c.strip()] or [""]


class Backend:
    def __init__(self, cred, state_dir):
        self.token, self.guild = cred["token"].strip(), cred["guild"]
        self.state = Path(state_dir) / "discord.json"
        self.s = json.loads(self.state.read_text()) if self.state.exists() else {}
        self.s.setdefault("where", {})   # message id -> channel id, for react and edit
        self.s.setdefault("users", {})   # display name -> user id, for mentions
        user = self.call("GET", "/users/@me")
        self.uid, self.me = user["id"], user.get("global_name") or user["username"]
        self._channels = None

    # --- HTTP -------------------------------------------------------------
    def call(self, method, path, payload=None, files=(), ok403=False):
        headers = {"Authorization": f"Bot {self.token}", "User-Agent": UA}
        data = None
        if files:
            boundary = f"----booth{time.time_ns()}"
            parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                     f"Content-Type: application/json\r\n\r\n{json.dumps(payload or {})}\r\n".encode()]
            for i, f in enumerate(files):
                f = Path(f)
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[{i}]\"; "
                             f"filename=\"{f.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                             .encode() + f.read_bytes() + b"\r\n")
            data = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if method == "PUT" and data is None:
            data = b""
        req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
        while True:
            try:
                with urllib.request.urlopen(req) as r:
                    body = r.read()
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(float(json.load(e).get("retry_after", 1)) + 0.1)
                    continue
                if e.code == 403 and ok403:
                    return None
                raise SystemExit(f"Discord {e.code} on {method} {path}: {e.read().decode()[:300]}")

    def save(self):
        where = self.s["where"]
        if len(where) > INDEX_KEEP:
            self.s["where"] = dict(sorted(where.items(), key=lambda kv: int(kv[0]))[-INDEX_KEEP:])
        self.state.write_text(json.dumps(self.s))

    # --- channels and threads ---------------------------------------------
    def channels(self):
        if self._channels is None:
            self._channels = {c["id"]: c for c in self.call("GET", f"/guilds/{self.guild}/channels")}
        return self._channels

    def channel(self, name, create=False):
        key = name.lstrip("#").lower().replace(" ", "-")
        for c in self.channels().values():
            if c["type"] in (TEXT, FORUM) and c["name"].lower() == key:
                return c
        if not create:
            raise SystemExit(f"No channel #{name} on this server")
        c = self.call("POST", f"/guilds/{self.guild}/channels", {"name": key, "type": FORUM})
        self._channels[c["id"]] = c
        return c

    def ensure(self, channel):
        self.channel(channel, create=True)

    def threads(self, parent=None):
        active = self.call("GET", f"/guilds/{self.guild}/threads/active")["threads"]
        for t in active:
            self.channels()[t["id"]] = t
        if parent is None:
            return active
        archived = self.call("GET", f"/channels/{parent}/threads/archived/public?limit=100",
                             ok403=True) or {"threads": []}
        return [t for t in active if t.get("parent_id") == parent] + archived["threads"]

    def thread(self, parent, name):
        for t in self.threads(parent["id"]):
            if t["name"] in (name, "✔ " + name):
                return t
        return None

    # --- messages ---------------------------------------------------------
    def _text(self, m):
        text = m.get("content", "")
        for u in m.get("mentions", []):
            text = re.sub(rf"<@!?{u['id']}>", "@" + (u.get("global_name") or u["username"]), text)

        def chan(mo):
            c = self.channels().get(mo.group(1))
            return "#" + c["name"] if c else mo.group(0)
        text = re.sub(r"<#(\d+)>", chan, text)
        files = [a["url"] for a in m.get("attachments", [])]
        ref = m.get("message_reference", {}).get("message_id")
        return (f"(reply to [{ref}]) " if ref and m.get("type") == 19 else "") + \
            "\n".join([text] + files).strip()

    def _norm(self, m, where):
        a = m["author"]
        name = a.get("global_name") or a["username"]
        self.s["users"][name] = a["id"]
        for u in m.get("mentions", []):
            self.s["users"][u.get("global_name") or u["username"]] = u["id"]
        self.s["where"][m["id"]] = where["id"]
        is_thread = where["type"] in (10, 11, 12)
        parent = self.channels().get(where["parent_id"], where) if is_thread else where
        return {"id": m["id"], "author": name, "channel": parent["name"],
                "thread": where["name"] if is_thread else "", "text": self._text(m),
                "time": ((int(m["id"]) >> 22) + EPOCH_MS) / 1000, "mine": a["id"] == self.uid}

    def _sources(self):
        """Text channels and active threads, each with its newest message id."""
        out = [c for c in self.channels().values() if c["type"] == TEXT]
        return out + self.threads()

    def read(self, cursor):
        after = dict(cursor.get("after", {}))
        msgs, more = [], False
        for src in self._sources():
            last, seen = src.get("last_message_id"), after.get(src["id"])
            if not last or (seen and int(seen) >= int(last)):
                continue
            q = f"?limit=100&after={seen}" if seen else "?limit=50"
            got = self.call("GET", f"/channels/{src['id']}/messages{q}", ok403=True)
            if not got:
                continue
            got.sort(key=lambda m: int(m["id"]))
            more |= len(got) == 100
            after[src["id"]] = got[-1]["id"]
            msgs += [self._norm(m, src) for m in got if m.get("type", 0) in (0, 19)]
        self.save()
        msgs.sort(key=lambda m: int(m["id"]))
        return msgs, {"after": after}, more

    def recent(self, n):
        msgs = []
        for src in self._sources():
            got = self.call("GET", f"/channels/{src['id']}/messages?limit={min(n, 100)}", ok403=True) or []
            msgs += [self._norm(m, src) for m in got if m.get("type", 0) in (0, 19)]
        self.save()
        return sorted(msgs, key=lambda m: int(m["id"]))[-n:]

    def mentions_out(self, text):
        """Turn @**Name** (Zulip habit) into a real Discord mention when the name is known."""
        def sub(mo):
            uid = self.s["users"].get(mo.group(1))
            return f"<@{uid}>" if uid else "@" + mo.group(1)
        return re.sub(r"@_?\*\*([^*]+)\*\*", sub, text)

    def _send(self, channel_id, text, files=()):
        pieces = chunks(self.mentions_out(text))
        first = None
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            m = self.call("POST", f"/channels/{channel_id}/messages", {"content": piece},
                          files=files if last else ())
            first = first or m["id"]
            self.s["where"][m["id"]] = channel_id
        return first

    def post(self, channel, thread, text, files=()):
        parent = self.channel(channel, create=True)
        if parent["type"] == TEXT and not thread:
            mid = self._send(parent["id"], text, files)
        else:
            t = self.thread(parent, thread)
            if t is None and parent["type"] == FORUM:
                pieces = chunks(self.mentions_out(text))
                payload = {"name": thread[:100], "message": {"content": pieces[0]}}
                t = self.call("POST", f"/channels/{parent['id']}/threads", payload,
                              files=files if len(pieces) == 1 else ())
                mid = t["id"]  # a forum post's first message shares the thread's id
                self.s["where"][mid] = t["id"]
                if len(pieces) > 1:
                    self._send(t["id"], "\n\n".join(pieces[1:]), files)
                self.save()
                return mid
            if t is None:
                t = self.call("POST", f"/channels/{parent['id']}/threads",
                              {"name": thread[:100], "type": 11, "auto_archive_duration": 10080})
            mid = self._send(t["id"], text, files)
        self.save()
        return mid

    def _where(self, mid):
        cid = self.s["where"].get(str(mid))
        if not cid:
            raise SystemExit(f"Unknown message [{mid}]; read or recent it first")
        return cid

    def react(self, mid, emoji):
        e = EMOJI.get(emoji, emoji)
        self.call("PUT", f"/channels/{self._where(mid)}/messages/{mid}/reactions/"
                  f"{urllib.parse.quote(e)}/@me")

    def edit(self, mid, text):
        if len(text) > 2000:
            raise SystemExit("Edited text exceeds Discord's 2000 characters; post a follow-up instead")
        self.call("PATCH", f"/channels/{self._where(mid)}/messages/{mid}",
                  {"content": self.mentions_out(text)})

    def resolve(self, channel, thread):
        t = self.thread(self.channel(channel), thread)
        if t is None:
            raise SystemExit(f"No thread {thread!r} in #{channel}")
        if self.call("PATCH", f"/channels/{t['id']}", {"name": ("✔ " + thread)[:100], "archived": True},
                     ok403=True) is None:
            self._send(t["id"], "✔ resolved")

    def members(self):
        got = self.call("GET", f"/guilds/{self.guild}/members?limit=1000", ok403=True)
        if got:
            return [(f"<@{m['user']['id']}> ({m.get('nick') or m['user'].get('global_name') or m['user']['username']})",
                     "bot" if m["user"].get("bot") else "human")
                    for m in got if m["user"]["id"] != self.uid]
        # Without the Server Members intent: everyone seen in messages so far.
        return [(f"<@{uid}> ({name})", "seen") for name, uid in self.s["users"].items() if uid != self.uid]

    def dm(self, author, text):
        uid = author if str(author).isdigit() else self.s["users"].get(author)
        if not uid:
            found = self.call("GET", f"/guilds/{self.guild}/members/search?"
                              + urllib.parse.urlencode({"query": author, "limit": 1}), ok403=True)
            uid = found[0]["user"]["id"] if found else None
        if not uid:
            raise SystemExit(f"Cannot find Discord user {author!r}; ask your author for their user id")
        ch = self.call("POST", "/users/@me/channels", {"recipient_id": str(uid)})
        self._send(ch["id"], text)

    def api(self, method, path, data):
        return self.call(method, path, data or None)
