#!/usr/bin/env python3
"""Post a Block Kit / attachments payload to Slack, or update the last one in place.

    python3 post.py alert-rollup.json            # post
    python3 post.py alert-rollup.json -u         # edit the last post in place
    python3 post.py alert-rollup.json -t <ts>    # reply in a thread

The payload file is either a single message object, or a JSON array of message
objects -- an array is posted as consecutive messages, which is how you get
un-barred headers interleaved with colour-barred groups (top-level `blocks`
always render above `attachments`, so you get one such pair per message).

Reads .env from this directory. Stores posted ts values in <payload>.ts so -u
knows what to edit. Stdlib only -- no pip install.

NB: don't name files in this directory after stdlib modules (bisect.py,
random.py, json.py...) -- they shadow the real module on import.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API = "https://slack.com/api/"


def load_env():
    """Read .env sitting next to this script, without needing `source .env`."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def call(method, body, token):
    req = urllib.request.Request(
        API + method,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def build(msg, channel):
    body = {"channel": channel}
    # An explicit empty/absent `text` is honoured, not defaulted: when a message
    # has no top-level blocks, Slack RENDERS `text` as a line above the bars.
    # Dropping it is the only way to suppress that line. Cost: weaker push
    # notifications, since `text` is what the notification shows.
    text = msg.get("text", "monitor rollup")
    if text:
        body["text"] = text
    for key in ("blocks", "attachments"):
        if key in msg:
            body[key] = msg[key]
    return body


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)

    payload_path = Path(args[0])
    update = "-u" in args or "--update" in args
    thread_ts = args[args.index("-t") + 1] if "-t" in args else None

    load_env()
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL")
    if not token or not channel:
        sys.exit("Set SLACK_BOT_TOKEN and SLACK_CHANNEL in .env first.")

    payload = json.loads(payload_path.read_text())
    messages = payload if isinstance(payload, list) else [payload]
    ts_file = payload_path.with_suffix(payload_path.suffix + ".ts")

    if update:
        if not ts_file.exists():
            sys.exit(f"No {ts_file.name} yet -- post once before updating.")
        known = ts_file.read_text().split()
        if len(known) != len(messages):
            sys.exit(
                f"{payload_path.name} now has {len(messages)} message(s) but "
                f"{ts_file.name} tracks {len(known)}. Delete {ts_file.name} "
                "and post fresh."
            )

    posted = []
    for i, msg in enumerate(messages):
        body = build(msg, channel)

        if update:
            body["ts"] = known[i]
            # chat.update KEEPS blocks/attachments you omit, so clear whichever
            # this message no longer uses rather than leaving a stale hybrid.
            for key in ("blocks", "attachments"):
                body.setdefault(key, [])
            method = "chat.update"
        else:
            if thread_ts:
                body["thread_ts"] = thread_ts
            method = "chat.postMessage"

        res = call(method, body, token)

        if not res.get("ok"):
            label = f"message {i + 1}/{len(messages)}"
            print(f"FAILED on {label}: {res.get('error')}", file=sys.stderr)
            print(json.dumps(res, indent=2), file=sys.stderr)
            if posted:
                ts_file.write_text("\n".join(posted))
                print(f"(first {len(posted)} saved to {ts_file.name})", file=sys.stderr)
            sys.exit(1)

        posted.append(res["ts"])
        if not update and i < len(messages) - 1:
            time.sleep(0.4)  # keep channel ordering stable

    ts_file.write_text("\n".join(posted))
    verb = "updated" if update else "posted"
    print(f"{verb} {len(posted)} message(s): {', '.join(posted)}")


if __name__ == "__main__":
    main()
