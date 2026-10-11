"""Zulip backend: a channel is a Zulip channel, a thread is a topic."""
import base64
import configparser
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from backends import EMOJI

RESOLVED = "✔ "


def invitation(path):
    """A zuliprc file, or a community.json with platform, email, key and site."""
    path = Path(path).expanduser()
    if path.suffix == ".json":
        d = json.loads(path.read_text())
        return {k: d[k] for k in ("email", "key", "site")}
    c = configparser.ConfigParser()
    c.read(path)
    return {k: c["api"][k].strip() for k in ("email", "key", "site")}


class Zulip:
    """Thin REST client. Also used by the organizer scripts."""

    def __init__(self, rc_path=None, *, email=None, key=None, site=None):
        if rc_path is not None:
            email, key, site = invitation(rc_path).values()
        self.email = email.strip()
        self.site = site.strip().rstrip("/")
        token = base64.b64encode(f"{self.email}:{key.strip()}".encode()).decode()
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


class Backend:
    def __init__(self, cred, state_dir):
        self.z = Zulip(**cred)
        self.me = self.z.call("GET", "/users/me")["full_name"]

    def _norm(self, m):
        return {"id": str(m["id"]), "author": m["sender_full_name"], "channel": m["display_recipient"],
                "thread": m["subject"], "time": m["timestamp"], "text": m["content"],
                "mine": m["sender_email"] == self.z.email}

    def _fetch(self, **window):
        subs = {s["name"] for s in self.z.call("GET", "/users/me/subscriptions")["subscriptions"]}
        msgs = self.z.call("GET", "/messages", {
            **window, "apply_markdown": "false",
            "narrow": json.dumps([{"operator": "channels", "operand": "public"}]),
        })["messages"]
        return msgs, [self._norm(m) for m in msgs if m["display_recipient"] in subs]

    def read(self, cursor):
        last = cursor.get("last")
        msgs, mine = self._fetch(anchor=last or "oldest", include_anchor="false" if last else "true",
                                 num_before=0, num_after=200)
        if msgs:
            cursor = {"last": msgs[-1]["id"]}
        return mine, cursor, len(msgs) == 200

    def recent(self, n):
        return self._fetch(anchor="newest", num_before=n, num_after=0)[1][-n:]

    def ensure(self, channel):
        self.z.subscribe(channel)  # also creates the channel if it does not exist

    def post(self, channel, thread, text, files=()):
        self.ensure(channel)
        content = "\n\n".join([text] + [self.z.upload(f) for f in files]).strip()
        return str(self.z.call("POST", "/messages", {"type": "stream", "to": channel,
                                                     "topic": thread, "content": content})["id"])

    def react(self, mid, emoji):
        self.z.call("POST", f"/messages/{mid}/reactions",
                    {"emoji_name": emoji if emoji in EMOJI else emoji.strip(":")})

    def edit(self, mid, text):
        self.z.call("PATCH", f"/messages/{mid}", {"content": text})

    def resolve(self, channel, thread):
        narrow = [{"operator": "channel", "operand": channel}, {"operator": "topic", "operand": thread}]
        msgs = self.z.call("GET", "/messages", {"anchor": "newest", "num_before": 1, "num_after": 0,
                                                "narrow": json.dumps(narrow)})["messages"]
        if not msgs:
            raise SystemExit(f"No thread {thread!r} in #{channel}")
        # Keep the resolved topic within the server's limit, leaving room for the prefix.
        keep = self._max_topic_length() - len(RESOLVED)
        self.z.call("PATCH", f"/messages/{msgs[0]['id']}",
                    {"topic": RESOLVED + thread[:keep], "propagate_mode": "change_all"})

    def _max_topic_length(self):
        """The server's topic length limit, which Zulip reports only when registering an event queue."""
        reg = self.z.call("POST", "/register", {"fetch_event_types": json.dumps(["realm"])})
        self.z.call("DELETE", "/events", {"queue_id": reg["queue_id"]})
        return reg.get("max_topic_length", 60)

    def members(self):
        return [(f"@**{u['full_name']}**", "bot" if u["is_bot"] else "human")
                for u in self.z.call("GET", "/users")["members"]
                if u["is_active"] and u["email"] != self.z.email and u.get("bot_type") not in (2, 3)]

    def dm(self, author, text):
        self.z.call("POST", "/messages", {"type": "direct", "to": json.dumps([author]), "content": text})

    def api(self, method, path, data):
        return self.z.call(method, path, data)
