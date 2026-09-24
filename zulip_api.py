"""Minimal Zulip REST client shared by the scripts in this folder. Never prints keys."""
import base64
import configparser
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZULIP = HERE / "zulip"


class Client:
    def __init__(self, rc_path):
        c = configparser.ConfigParser()
        c.read(rc_path)
        api = c["api"]
        self.email = api["email"].strip()
        self.site = api["site"].strip().rstrip("/")
        token = base64.b64encode(f"{self.email}:{api['key'].strip()}".encode()).decode()
        self.auth = f"Basic {token}"

    @classmethod
    def bot(cls, short):
        return cls(ZULIP / f"{short}.zuliprc")

    @classmethod
    def admin(cls):
        return cls(ZULIP / "admin.zuliprc")

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
        """Upload a file and return a Markdown link to it."""
        path = Path(path)
        boundary = f"----zulip{time.time_ns()}"
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


def load_roster(name="roster.json"):
    return json.loads((HERE / name).read_text())
