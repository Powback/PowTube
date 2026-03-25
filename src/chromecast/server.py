#!/usr/bin/env python3
"""Chromecast HTTP control server — exposes casting commands via a REST API.

Wraps pychromecast to maintain a persistent connection to a Chromecast device.
chromecast-cli (and agents) send HTTP requests here rather than connecting directly.

Default port: 7655 (override with CHROMECAST_CONTROL_PORT env var)
Default device: 192.168.50.143 (override with CHROMECAST_HOST or CHROMECAST_NAME env var)

Endpoints:
    GET  /devices         → discover Chromecast devices on the network (mDNS)
    GET  /status          → current playback state as JSON
    POST /connect         → {"host": "192.168.50.143"} or {"name": "Living Room TV"}
    POST /cast            → {"url": "...", "content_type": "video/mp4", "title": "..."}
    POST /play            → resume playback
    POST /pause           → pause playback
    POST /stop            → stop and return to idle
    POST /volume          → {"level": 50}  (0–100)
    POST /seek            → {"seconds": 30.0}
"""

import asyncio
import logging
import mimetypes
import os
import threading
from urllib.parse import urlparse

import pychromecast
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("chromecast.server")

DEFAULT_PORT = int(os.environ.get("CHROMECAST_CONTROL_PORT", "7655"))
DEFAULT_HOST = os.environ.get("CHROMECAST_HOST", "192.168.50.143")
DEFAULT_NAME = os.environ.get("CHROMECAST_NAME", "")

# Global state — protected by a lock since pychromecast is synchronous
_lock = threading.Lock()
_cast = None       # pychromecast.Chromecast instance
_browser = None    # discovery browser (kept alive to maintain mDNS)


def _guess_content_type(url: str) -> str:
    """Guess MIME type from URL extension, default to video/mp4."""
    path = urlparse(url).path
    mime, _ = mimetypes.guess_type(path)
    if mime:
        return mime
    # YouTube-dl / direct stream URLs often have no extension — assume video
    return "video/mp4"


def _connect_by_host(host: str) -> pychromecast.Chromecast:
    global _cast, _browser
    logger.info("Connecting to Chromecast at %s …", host)
    cast, browser = pychromecast.get_chromecast_from_host(
        (host, 8009, None, None, None)
    )
    cast.wait(timeout=15)
    _cast = cast
    _browser = browser
    logger.info("Connected: %s (model: %s)", cast.name, cast.model_name)
    return cast


def _connect_by_name(name: str) -> pychromecast.Chromecast:
    global _cast, _browser
    logger.info("Discovering Chromecast named '%s' …", name)
    chromecasts, browser = pychromecast.get_listed_chromecasts(
        friendly_names=[name], timeout=10
    )
    if not chromecasts:
        raise RuntimeError(f"No Chromecast found with name '{name}'")
    cast = chromecasts[0]
    cast.wait(timeout=15)
    _cast = cast
    _browser = browser
    logger.info("Connected: %s (model: %s)", cast.name, cast.model_name)
    return cast


def _get_cast() -> pychromecast.Chromecast:
    """Return current cast connection, auto-connecting to default if needed."""
    global _cast
    with _lock:
        if _cast is not None:
            return _cast
        if DEFAULT_NAME:
            return _connect_by_name(DEFAULT_NAME)
        if DEFAULT_HOST:
            return _connect_by_host(DEFAULT_HOST)
        raise RuntimeError("No Chromecast configured. Set CHROMECAST_HOST or use POST /connect")


# --- Route handlers ---

async def handle_devices(request):
    """Discover all Chromecast devices visible via mDNS (requires network access)."""
    loop = asyncio.get_event_loop()
    try:
        cast_infos, browser = await loop.run_in_executor(
            None, lambda: pychromecast.discovery.discover_chromecasts(timeout=8)
        )
        pychromecast.discovery.stop_discovery(browser)
        devices = [
            {
                "name": info.friendly_name,
                "host": info.host,
                "port": info.port,
                "model": info.model_name,
                "uuid": str(info.uuid) if info.uuid else None,
            }
            for info in cast_infos
        ]
        return web.json_response({"devices": devices, "count": len(devices)})
    except Exception as e:
        logger.error("Device discovery failed: %s", e)
        return web.json_response({"error": str(e)}, status=503)


async def handle_connect(request):
    data = await request.json()
    host = data.get("host", "")
    name = data.get("name", "")
    loop = asyncio.get_event_loop()
    try:
        if host:
            cast = await loop.run_in_executor(None, lambda: _connect_by_host(host))
        elif name:
            cast = await loop.run_in_executor(None, lambda: _connect_by_name(name))
        else:
            return web.json_response({"error": "host or name required"}, status=400)
        return web.json_response({"ok": True, "device": cast.name, "host": host or name})
    except Exception as e:
        logger.error("Connect failed: %s", e)
        return web.json_response({"error": str(e)}, status=503)


async def handle_status(request):
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)
        # Refresh media status
        await loop.run_in_executor(None, cast.media_controller.update_status)
        ms = cast.media_controller.status
        cs = cast.status
        return web.json_response({
            "device": cast.name,
            "player_state": ms.player_state,
            "content_id": ms.content_id,
            "title": ms.title,
            "current_time": ms.adjusted_current_time,
            "duration": ms.duration,
            "volume": round((cs.volume_level or 0) * 100),
            "muted": cs.volume_muted,
            "app": cs.display_name,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)


async def handle_cast(request):
    data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return web.json_response({"error": "url required"}, status=400)
    content_type = data.get("content_type") or _guess_content_type(url)
    title = data.get("title", "")
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)

        def _do_cast():
            mc = cast.media_controller
            mc.play_media(url, content_type, title=title or None)
            mc.block_until_active(timeout=10)

        await loop.run_in_executor(None, _do_cast)
        return web.json_response({"ok": True, "url": url, "content_type": content_type})
    except Exception as e:
        logger.error("Cast failed: %s", e)
        return web.json_response({"error": str(e)}, status=503)


async def handle_play(request):
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)
        await loop.run_in_executor(None, cast.media_controller.play)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)


async def handle_pause(request):
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)
        await loop.run_in_executor(None, cast.media_controller.pause)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)


async def handle_stop(request):
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)
        await loop.run_in_executor(None, cast.media_controller.stop)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)


async def handle_volume(request):
    data = await request.json()
    level = data.get("level")
    if level is None:
        return web.json_response({"error": "level required (0-100)"}, status=400)
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)
        await loop.run_in_executor(None, lambda: cast.set_volume(int(level) / 100))
        return web.json_response({"ok": True, "volume": int(level)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)


async def handle_seek(request):
    data = await request.json()
    seconds = data.get("seconds")
    if seconds is None:
        return web.json_response({"error": "seconds required"}, status=400)
    loop = asyncio.get_event_loop()
    try:
        cast = await loop.run_in_executor(None, _get_cast)
        await loop.run_in_executor(None, lambda: cast.media_controller.seek(float(seconds)))
        return web.json_response({"ok": True, "seconds": float(seconds)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)


async def handle_health(request):
    return web.json_response({"ok": True, "service": "chromecast-server"})


def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/devices", handle_devices)
    app.router.add_get("/status", handle_status)
    app.router.add_post("/connect", handle_connect)
    app.router.add_post("/cast", handle_cast)
    app.router.add_post("/play", handle_play)
    app.router.add_post("/pause", handle_pause)
    app.router.add_post("/stop", handle_stop)
    app.router.add_post("/volume", handle_volume)
    app.router.add_post("/seek", handle_seek)

    # Attempt to pre-connect on startup (non-fatal if device unreachable)
    if DEFAULT_HOST or DEFAULT_NAME:
        def _try_preconnect():
            try:
                _get_cast()
            except Exception as e:
                logger.warning("Pre-connect skipped: %s", e)
        t = threading.Thread(target=_try_preconnect, daemon=True)
        t.start()

    logger.info("Chromecast control server starting on port %d", DEFAULT_PORT)
    web.run_app(app, host="0.0.0.0", port=DEFAULT_PORT, access_log=None)


if __name__ == "__main__":
    main()
