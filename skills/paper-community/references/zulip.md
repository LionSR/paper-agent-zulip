# Writing on Zulip

On Zulip a thread is a *topic* inside a channel.

- Mentions: `@**Exact Name**` (from `BOOTH who`); silent mention
  `@_**Name**`; notify a whole topic with `@**topic**`.
- Links: a topic `#**MAIN>topic name**`, a message `#**MAIN>topic name@ID**`.
  When moving a conversation, leave `moving this to #**MAIN>new topic**`.
- Quote-reply: a ` ```quote ` block with what you answer, plus the message
  link.
- Math: inline `$$S(R) \approx \log_2(2R+1)$$`, display equations in a
  ` ```math ` block. Both render.
- Markdown, tables, code, and collapsible ` ```spoiler Title ` blocks.
- `/poll Question` or `/todo Title` followed by one item per line.
- Times in everyone's own time zone: `<time:2026-10-01T15:00:00Z>`.
- `BOOTH resolve` renames the topic with a leading "✔ ", which is how Zulip
  marks topics resolved.
- `BOOTH api METHOD /path key=value ...` reaches anything else
  (https://zulip.com/api/), e.g. moving messages to another topic:
  `BOOTH api PATCH /messages/ID topic="new name" propagate_mode=change_all`.
