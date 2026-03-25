#!/usr/bin/env python3
"""lgtv_control.py: Direct LG webOS TV control via SSAP WebSocket API

PREREQUISITE: Developer Mode must be enabled on the TV.
Steps to enable:
  1. Register at developer.lge.com
  2. Install "Developer Mode" app on TV from LG Content Store
  3. Enable dev mode with your LG account credentials
  4. Set Developer Mode app → DEV MODE ON
  5. TV exposes port 3000 (SSAP WebSocket)

Usage:
    python3 lgtv_control.py status          # Get TV state
    python3 lgtv_control.py volume 50       # Set volume 0-100
    python3 lgtv_control.py mute            # Toggle mute
    python3 lgtv_control.py power off       # Turn off
    python3 lgtv_control.py input hdmi1     # Switch input
    python3 lgtv_control.py app netflix     # Launch Netflix
    python3 lgtv_control.py app youtube     # Launch YouTube
    python3 lgtv_control.py apps            # List installed apps

TV: 192.168.50.143 (webOS 05.50.70)
"""

import asyncio
import json
import os
import sys

TV_IP = os.environ.get("LG_TV_IP", "192.168.50.143")
CLIENT_KEY_FILE = os.path.expanduser("~/.config/lgtv_client_key.json")

# App IDs for common apps on webOS
APP_IDS = {
    "netflix": "netflix",
    "youtube": "youtube.leanback.v4",
    "disney": "com.disney.disneyplus-prod",
    "spotify": "spotify-beehive",
    "plex": "cdp-30",
    "appletv": "com.apple.atve.lg.appletv",
    "hbo": "com.hbo.hbomax.lge",
    "amazon": "amazon",
    "twitch": "twitch",
    "browser": "com.webos.app.browser",
    "hdmi1": "com.webos.app.hdmi1",
    "hdmi2": "com.webos.app.hdmi2",
    "hdmi3": "com.webos.app.hdmi3",
    "hdmi4": "com.webos.app.hdmi4",
}


def load_client_key():
    try:
        with open(CLIENT_KEY_FILE) as f:
            return json.load(f).get("client_key")
    except FileNotFoundError:
        return None


def save_client_key(key):
    os.makedirs(os.path.dirname(CLIENT_KEY_FILE), exist_ok=True)
    with open(CLIENT_KEY_FILE, "w") as f:
        json.dump({"client_key": key}, f)
    print(f"Client key saved to {CLIENT_KEY_FILE}")


async def run_command(args):
    try:
        from aiowebostv import WebOsClient
    except ImportError:
        print("ERROR: aiowebostv not installed. Run: pip3 install aiowebostv")
        sys.exit(1)

    client_key = load_client_key()
    client = WebOsClient(TV_IP, client_key=client_key)

    try:
        print(f"Connecting to LG TV at {TV_IP}...")
        await asyncio.wait_for(client.connect(), timeout=10)

        # Save client key after pairing
        if client.client_key and client.client_key != client_key:
            save_client_key(client.client_key)
            print("Paired with TV - accept prompt on screen if shown")

        cmd = args[0] if args else "status"

        if cmd == "status":
            info = await client.get_software_info()
            power = await client.get_power_state()
            inputs = await client.get_inputs()
            current = await client.get_current_app()
            print(json.dumps({
                "software": info,
                "power": power,
                "current_app": current,
                "inputs": inputs,
            }, indent=2, default=str))

        elif cmd == "volume":
            if len(args) < 2:
                vol = await client.get_volume()
                print(f"Volume: {vol}")
            else:
                level = int(args[1])
                await client.set_volume(level)
                print(f"Volume set to {level}")

        elif cmd == "mute":
            state = await client.get_muted()
            await client.set_mute(not state)
            print(f"Mute: {'ON' if not state else 'OFF'}")

        elif cmd == "power":
            if len(args) > 1 and args[1] == "off":
                await client.power_off()
                print("TV powered off")
            else:
                print("Usage: power off")

        elif cmd == "input":
            if len(args) < 2:
                inputs = await client.get_inputs()
                print(json.dumps(inputs, indent=2, default=str))
            else:
                input_name = args[1].lower()
                app_id = APP_IDS.get(input_name, input_name)
                await client.launch_app(app_id)
                print(f"Launched: {app_id}")

        elif cmd == "app":
            if len(args) < 2:
                apps = await client.get_apps()
                for app in apps:
                    print(f"{app.get('id'):50s} {app.get('title','')}")
            else:
                app_name = args[1].lower()
                app_id = APP_IDS.get(app_name, args[1])
                await client.launch_app(app_id)
                print(f"Launched: {app_id}")

        elif cmd == "apps":
            apps = await client.get_apps()
            for app in sorted(apps, key=lambda a: a.get("title", "")):
                print(f"{app.get('id'):60s} {app.get('title','')}")

        elif cmd == "notify":
            msg = " ".join(args[1:]) if len(args) > 1 else "Hello from PowTube"
            await client.send_message(msg)
            print(f"Notification sent: {msg}")

        elif cmd == "key":
            if len(args) < 2:
                print("Keys: HOME BACK ENTER UP DOWN LEFT RIGHT RED GREEN YELLOW BLUE VOLUMEUP VOLUMEDOWN MUTE CHANNELUP CHANNELDOWN PLAY PAUSE STOP FASTFORWARD REWIND")
            else:
                key = args[1].upper()
                await client.send_button(key)
                print(f"Key sent: {key}")

        else:
            print(f"Unknown command: {cmd}")
            print("Commands: status, volume [N], mute, power off, input [name], app [name], apps, notify [msg], key [KEY]")
            sys.exit(1)

    except asyncio.TimeoutError:
        print(f"ERROR: Connection timeout to {TV_IP}")
        print("TV may be off or unreachable")
        sys.exit(1)
    except Exception as e:
        err_str = str(e)
        if "Connect call failed" in err_str or isinstance(e, ConnectionRefusedError):
            print(f"\nERROR: Connection refused to {TV_IP}:3000")
            print("\nTV requires Developer Mode to be enabled:")
            print("  1. Register at https://developer.lge.com")
            print("  2. Install 'Developer Mode' app from LG Content Store on TV")
            print("  3. Sign in with LG developer account on TV")
            print("  4. Set Developer Mode → ON")
            print("  5. TV will then accept connections on port 3000")
            print("\nAlternatively, enable IP Control in:")
            print("  TV Settings → All Settings → Connection → IP Control → Secured (password required)")
        else:
            print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


def main():
    args = sys.argv[1:]
    asyncio.run(run_command(args))


if __name__ == "__main__":
    main()
