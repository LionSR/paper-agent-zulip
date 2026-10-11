#!/usr/bin/env python3
"""Organizer tools for a Discord community. Never prints tokens.

Discord has no API for creating bots, so each paper's bot is made by hand once:

  1. https://discord.com/developers/applications > New Application, named
     after the paper (e.g. Lu2026).
  2. Bot > Reset Token, copy it. On the same page switch on Message Content
     Intent and Server Members Intent.
  3. Run `setup_discord.py invite SHORT` and paste the token when asked.
     It checks the bot, writes discord/SHORT.community.json (the file you send
     the author) and prints the link that adds the bot to the server.

    setup_discord.py server GUILD_ID CHANNEL   # once: the server and main channel
    setup_discord.py invite SHORT              # per paper, as above
"""
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

from community import HERE

KEYS = HERE / "discord"
SERVER = KEYS / "server.json"
API = "https://discord.com/api/v10"
PERMISSIONS = sum(1 << b for b in (
    4,   # Manage Channels: open collaboration channels
    6,   # Add Reactions
    10,  # View Channels
    11,  # Send Messages
    14,  # Embed Links
    15,  # Attach Files
    16,  # Read Message History
    34,  # Manage Threads: mark threads resolved
    35,  # Create Public Threads
    38,  # Send Messages in Threads
))
MESSAGE_CONTENT = (1 << 18) | (1 << 19)
SERVER_MEMBERS = (1 << 14) | (1 << 15)


def get(path, token):
    req = urllib.request.Request(API + path, headers={
        "Authorization": f"Bot {token}", "User-Agent": "DiscordBot (paper-agent-community, 1.0)"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Discord {e.code}: {e.read().decode()[:200]}")


def invite(short):
    if not SERVER.exists():
        raise SystemExit("Run `setup_discord.py server GUILD_ID CHANNEL` first.")
    server = json.loads(SERVER.read_text())
    token = getpass.getpass(f"Bot token for {short}: ").strip()
    app = get("/oauth2/applications/@me", token)
    flags = app.get("flags", 0)
    if not flags & MESSAGE_CONTENT:
        print("warning: Message Content Intent is off; the agent will read empty messages")
    if not flags & SERVER_MEMBERS:
        print("note: Server Members Intent is off; `who` will list only people seen in messages")
    out = KEYS / f"{short}.community.json"
    out.write_text(json.dumps({"platform": "discord", "token": token, "guild": server["guild"],
                               "channel": server["channel"]}, indent=1) + "\n")
    os.chmod(out, 0o600)
    print(f"{app['name']}: wrote {out.relative_to(HERE)}")
    print("Add it to the server (open while logged in as a server admin):")
    print(f"https://discord.com/oauth2/authorize?client_id={app['id']}&scope=bot&permissions={PERMISSIONS}")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("server", "invite"):
        raise SystemExit(__doc__)
    KEYS.mkdir(exist_ok=True)
    if sys.argv[1] == "server":
        guild, channel = sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "general"
        SERVER.write_text(json.dumps({"guild": guild, "channel": channel}) + "\n")
        print(f"server {guild}, main channel #{channel}")
    else:
        invite(sys.argv[2])


if __name__ == "__main__":
    main()
