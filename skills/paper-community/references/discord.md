# Writing on Discord

On Discord a channel is usually a *forum*, and a thread is a *post* in it.
`BOOTH post --thread NAME` opens the post if it does not exist yet.

- Mentions: `<@USER_ID>`, exactly as `BOOTH who` prints it. Writing
  `@**Name**` also works for anyone who has posted before.
- Links: a channel or thread `<#ID>`; a message
  `https://discord.com/channels/SERVER/CHANNEL/MESSAGE` (`BOOTH api GET
  /channels/ID` shows the ids). When moving a conversation, leave
  `moving this to <#NEW_THREAD_ID>`.
- Quote-reply: start lines with `> ` for what you answer.
- Math does not render on Discord. Write short formulas in plain Unicode or
  inline code (`S(R) ≈ log₂(2R+1)`); anything with real equations goes in a
  LaTeX note as a PDF, or as a rendered PNG with `--attach`.
- Markdown: bold, italics, lists, `#` headings, code blocks, and spoilers
  `||hidden||`. No tables: use a code block or an attached file.
- Messages are capped at 2000 characters. `BOOTH post` splits longer text at
  paragraph breaks; prefer a note over a long split message.
- Times in everyone's own time zone: `<t:UNIX_SECONDS:f>`.
- `BOOTH resolve` renames the post with a leading "✔ " and archives it. A
  reply reopens it.
- `BOOTH api METHOD /path key=value ...` reaches anything else
  (https://discord.com/developers/docs/reference).
