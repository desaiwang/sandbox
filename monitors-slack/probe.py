#!/usr/bin/env python3
"""Find what Slack is rejecting in alert-rollup.json.

    python3 probe.py

NB: do not rename this to bisect.py / random.py / json.py etc. A file sharing a
stdlib module name in the working directory shadows the real one on import.

Posts a ladder of increasingly complex payloads and reports ok/error for each,
so you can see exactly which field combination breaks. Also renders the ones
that succeed, so you can eyeball whether `pretext` actually shows up.

Reads .env from the same directory. Stdlib only.
"""

import copy
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
API = "https://slack.com/api/chat.postMessage"


def load_env():
    env_path = HERE / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def post(label, body, token, channel):
    body = dict(body, channel=channel)
    body.setdefault("text", f"bisect: {label}")
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req) as r:
        res = json.load(r)

    if res.get("ok"):
        print(f"  OK      {label}")
    else:
        print(f"  FAIL    {label}  -> {res.get('error')}")
        meta = res.get("response_metadata", {}).get("messages", [])
        for m in meta:
            print(f"            {m}")
        if not meta and res.get("warning"):
            print(f"            warning: {res['warning']}")
    return res.get("ok", False)


def main():
    load_env()
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL")
    if not token or not channel:
        sys.exit("SLACK_BOT_TOKEN / SLACK_CHANNEL missing from .env")

    payload = json.loads((HERE / "alert-rollup.json").read_text())
    atts = payload["attachments"]
    first = atts[0]

    print("\n== does pretext work at all (no blocks) ==")
    post("pretext + legacy text, no blocks", {
        "attachments": [{
            "color": first["color"],
            "pretext": first["pretext"],
            "mrkdwn_in": ["pretext", "text"],
            "text": "legacy attachment body",
        }],
    }, token, channel)

    print("\n== blocks alone, no legacy fields ==")
    post("color + blocks, no pretext", {
        "attachments": [{
            "color": first["color"],
            "blocks": first["blocks"],
        }],
    }, token, channel)

    print("\n== the combination in question ==")
    post("color + pretext + blocks", {
        "attachments": [copy.deepcopy(first)],
    }, token, channel)

    print("\n== each attachment on its own, as written ==")
    for i, att in enumerate(atts):
        name = att.get("pretext", f"attachment {i}").strip("*")
        post(f"[{i}] {name}", {"attachments": [copy.deepcopy(att)]}, token, channel)

    print("\n== blocks hoisted to top level (no attachments, no bars) ==")
    flat = []
    for att in atts:
        flat.extend(copy.deepcopy(att.get("blocks", [])))
    post("all blocks, top level", {"blocks": flat}, token, channel)

    print("\n== the full payload as written ==")
    body = {k: v for k, v in payload.items() if k != "channel"}
    post("full alert-rollup.json", body, token, channel)
    print()


if __name__ == "__main__":
    main()
