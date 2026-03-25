#!/usr/bin/env python3
"""chromecast-cli: Cast media and control Chromecast devices via the chromecast control server.

Usage:
    chromecast-cli devices                           Discover Chromecast devices on the network
    chromecast-cli status                            Show current playback status
    chromecast-cli connect <host-or-ip>              Connect to a device by IP address
    chromecast-cli connect --name "Living Room"      Connect to a device by name
    chromecast-cli cast <url>                        Cast a media URL to the connected device
    chromecast-cli cast <url> --type video/mp4       Cast with explicit content type
    chromecast-cli cast <url> --title "My Video"     Cast with a display title
    chromecast-cli play                              Resume playback
    chromecast-cli pause                             Pause playback
    chromecast-cli stop                              Stop playback
    chromecast-cli volume <0-100>                    Set volume level
    chromecast-cli seek <seconds>                    Seek to time in seconds

Environment:
    CHROMECAST_API_URL   Base URL of the control server (default: http://localhost:7655)
"""

import argparse
import asyncio
import json
import os
import sys

import aiohttp

DEFAULT_API_URL = os.environ.get("CHROMECAST_API_URL", "http://localhost:7655")


async def api_post(api_url: str, path: str, body: dict = None):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{api_url}{path}", json=body or {}) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    print(f"ERROR: {data.get('error', resp.reason)}", file=sys.stderr)
                    sys.exit(1)
                return data
        except aiohttp.ClientConnectorError:
            print(
                f"ERROR: Cannot connect to chromecast control server at {api_url}\n"
                "Is the server running? Start with: docker compose up -d chromecast",
                file=sys.stderr,
            )
            sys.exit(1)


async def api_get(api_url: str, path: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{api_url}{path}") as resp:
                data = await resp.json()
                if resp.status >= 400:
                    print(f"ERROR: {data.get('error', resp.reason)}", file=sys.stderr)
                    sys.exit(1)
                return data
        except aiohttp.ClientConnectorError:
            print(
                f"ERROR: Cannot connect to chromecast control server at {api_url}\n"
                "Is the server running? Start with: docker compose up -d chromecast",
                file=sys.stderr,
            )
            sys.exit(1)


async def cmd_devices(args):
    print("Scanning for Chromecast devices (up to 8 seconds)…")
    r = await api_get(args.api_url, "/devices")
    devices = r.get("devices", [])
    if not devices:
        print("No Chromecast devices found.")
        return
    print(f"Found {len(devices)} device(s):")
    for d in devices:
        print(f"  {d['name']:30s}  {d['host']}:{d.get('port', 8009)}  [{d.get('model', '?')}]")


async def cmd_status(args):
    r = await api_get(args.api_url, "/status")
    print(f"device:        {r.get('device', 'none')}")
    print(f"app:           {r.get('app') or 'idle'}")
    print(f"player_state:  {r.get('player_state', 'UNKNOWN')}")
    print(f"title:         {r.get('title') or '—'}")
    content = r.get('content_id') or ''
    if len(content) > 80:
        content = content[:77] + '…'
    print(f"content:       {content or '—'}")
    t = r.get('current_time') or 0
    d = r.get('duration') or 0
    print(f"time:          {t:.1f}s / {d:.1f}s")
    print(f"volume:        {r.get('volume', 0)}%{' (muted)' if r.get('muted') else ''}")


async def cmd_connect(args):
    body = {}
    if args.name:
        body["name"] = args.name
    elif args.host:
        body["host"] = args.host
    else:
        print("ERROR: provide host (positional) or --name <name>", file=sys.stderr)
        sys.exit(1)
    r = await api_post(args.api_url, "/connect", body)
    print(f"connect: {'OK' if r.get('ok') else 'FAILED'} — {r.get('device', '')}")


async def cmd_cast(args):
    body = {"url": args.url}
    if args.type:
        body["content_type"] = args.type
    if args.title:
        body["title"] = args.title
    r = await api_post(args.api_url, "/cast", body)
    if r.get("ok"):
        print(f"cast: OK  [{r.get('content_type', '?')}]  {args.url}")
    else:
        print("cast: FAILED")


async def cmd_play(args):
    r = await api_post(args.api_url, "/play")
    print(f"play: {'OK' if r.get('ok') else 'FAILED'}")


async def cmd_pause(args):
    r = await api_post(args.api_url, "/pause")
    print(f"pause: {'OK' if r.get('ok') else 'FAILED'}")


async def cmd_stop(args):
    r = await api_post(args.api_url, "/stop")
    print(f"stop: {'OK' if r.get('ok') else 'FAILED'}")


async def cmd_volume(args):
    r = await api_post(args.api_url, "/volume", {"level": args.level})
    print(f"volume {args.level}: {'OK' if r.get('ok') else 'FAILED'}")


async def cmd_seek(args):
    r = await api_post(args.api_url, "/seek", {"seconds": args.seconds})
    print(f"seek {args.seconds}s: {'OK' if r.get('ok') else 'FAILED'}")


async def run_command(args):
    await args.func(args)


def main():
    parser = argparse.ArgumentParser(
        prog="chromecast-cli",
        description="Cast media and control Chromecast devices",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        dest="api_url",
        help=f"Control server base URL (default: {DEFAULT_API_URL}, env: CHROMECAST_API_URL)",
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("devices", help="Discover Chromecast devices on the network")
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("status", help="Show current playback status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("connect", help="Connect to a Chromecast device")
    p.add_argument("host", nargs="?", default="", help="Device IP address or hostname")
    p.add_argument("--name", "-n", default="", help="Device friendly name (alternative to host)")
    p.set_defaults(func=cmd_connect)

    p = sub.add_parser("cast", help="Cast a media URL to the connected device")
    p.add_argument("url", help="URL of media to cast (video, audio, or image)")
    p.add_argument("--type", "-t", metavar="MIME", help="Content MIME type (auto-detected if omitted)")
    p.add_argument("--title", metavar="TITLE", help="Display title on TV")
    p.set_defaults(func=cmd_cast)

    p = sub.add_parser("play", help="Resume playback")
    p.set_defaults(func=cmd_play)

    p = sub.add_parser("pause", help="Pause playback")
    p.set_defaults(func=cmd_pause)

    p = sub.add_parser("stop", help="Stop playback")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("volume", help="Set volume level (0-100)")
    p.add_argument("level", type=int, metavar="LEVEL", help="Volume 0-100")
    p.set_defaults(func=cmd_volume)

    p = sub.add_parser("seek", help="Seek to a time position")
    p.add_argument("seconds", type=float, help="Time in seconds")
    p.set_defaults(func=cmd_seek)

    args = parser.parse_args()
    asyncio.run(run_command(args))


if __name__ == "__main__":
    main()
