#!/usr/bin/env python3
"""Answer button clicks from rollup-modal.json by opening a modal.

    pip3 install slack_sdk
    python3 listen.py          # leave running, then click the button in Slack

Needs Socket Mode, so no public URL: Slack pushes interactions down a websocket.
Requires SLACK_APP_TOKEN (xapp-..., scope connections:write) alongside
SLACK_BOT_TOKEN in .env, and Interactivity + Socket Mode enabled in app settings.

The modal body is read from rollup-modal.view.json on every click, so you can
edit that file and re-click without restarting this process.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent

try:
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
except ImportError:
    sys.exit("Needs the Slack SDK:  pip3 install slack_sdk")


def load_env():
    env_path = HERE / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def handle(client: SocketModeClient, req: SocketModeRequest):
    # ack first -- the trigger_id is only valid for ~3 seconds
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

    if req.type != "interactive":
        return
    payload = req.payload
    if payload.get("type") != "block_actions":
        return

    for action in payload.get("actions", []):
        if action.get("action_id") != "view_all_events":
            continue  # link buttons (view_current_state) need no response

        view = json.loads((HERE / "rollup-modal.view.json").read_text())
        try:
            client.web_client.views_open(trigger_id=payload["trigger_id"], view=view)
            print("opened modal for", payload.get("user", {}).get("username", "?"))
        except Exception as e:
            print("views.open failed:", e, file=sys.stderr)


def main():
    load_env()
    bot, app = os.environ.get("SLACK_BOT_TOKEN"), os.environ.get("SLACK_APP_TOKEN")
    if not bot or not app:
        sys.exit("Need SLACK_BOT_TOKEN and SLACK_APP_TOKEN (xapp-...) in .env")
    if not app.startswith("xapp-"):
        sys.exit("SLACK_APP_TOKEN must be an app-level token (xapp-...), not a bot token")

    client = SocketModeClient(app_token=app, web_client=WebClient(token=bot))
    client.socket_mode_request_listeners.append(handle)
    client.connect()
    print("listening for button clicks -- ctrl+c to stop")
    try:
        from threading import Event
        Event().wait()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
