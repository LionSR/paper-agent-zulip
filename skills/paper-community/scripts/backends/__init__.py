"""Chat platforms behind booth.py. Standard library only.

Every backend turns its platform into the same few ideas: a channel holds
threads (a Zulip topic, a Discord forum post), a message has an id, an author,
a channel, a thread, a time and plain text. booth.py only speaks these ideas;
each backend module only speaks its platform.

A backend module defines `Backend(credentials, state_dir)` with:

    me                                  this agent's display name
    read(cursor) -> (msgs, cursor, more)  messages after the cursor, all channels
    recent(n) -> msgs                   the last n messages, cursor untouched
    ensure(channel)                     join the channel, creating it if new
    post(channel, thread, text, files) -> id   creates the channel or thread if new
    react(id, emoji)                    emoji is a short name such as thumbs_up
    edit(id, text)
    resolve(channel, thread)            mark a settled thread resolved
    members() -> [(mention, kind)]      exact mention strings, kind is human or bot
    dm(author, text)                    direct message to the human author
    api(method, path, data)             raw platform call, for the platform notes

and a module-level `invitation(path) -> credentials` that reads whatever file
the organizer sends for this platform.
"""
import importlib

PLATFORMS = ("zulip", "discord")

# Short reaction names shared by every platform.
EMOJI = {"thumbs_up": "👍", "tada": "🎉", "light_bulb": "💡", "thinking": "🤔",
         "eyes": "👀", "heart": "❤️", "check": "✅"}


def load(platform):
    if platform not in PLATFORMS:
        raise SystemExit(f"Unknown platform {platform!r}; expected one of {', '.join(PLATFORMS)}")
    return importlib.import_module(f"backends.{platform}")
