# PowTube

YouTube and video tooling for PowStation home server.

## Services

### iSponsorBlockTV

Auto-skips YouTube sponsor segments on smart TVs using the [SponsorBlock](https://sponsor.ajay.app/) database.

- **Image:** `ghcr.io/dmunozv04/isponsorblocktv:latest`
- **Repo:** https://github.com/dmunozv04/iSponsorBlockTV
- **Data:** `./data/isponsorblock/` (mounted at `/app/data` in container)

#### How it works

iSponsorBlockTV acts as a man-in-the-middle between your TV remote and YouTube TV, intercepting playback events via the YouTube Lounge API and automatically seeking past sponsor segments.

#### First-time setup

1. Start the container:
   ```bash
   docker compose up -d
   ```

2. Pair with your TV using the pairing code displayed on screen (YouTube TV → Settings → Link with TV code):
   ```bash
   docker exec -it isponsorblock python main.py --setup
   ```
   Enter the 12-digit code shown on your TV.

3. The pairing is saved in `./data/isponsorblock/config.json` and persists across restarts.

#### Notes

- `network_mode: host` would be needed for SSDP/mDNS auto-discovery of TVs on the LAN.
  Under Colima (macOS VM), this doesn't work — use manual pairing via TV pairing code instead.
- Multiple TVs can be paired; re-run setup for each.

## Adding More YouTube/Video Tools

This project is the home for any YouTube or video-related self-hosted tools. Add new services to `docker-compose.yml`.

If a service needs Traefik routing (web UI), add the traefik network:

```yaml
services:
  my-tool:
    image: ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.my-tool.rule=Host(`my-tool.pow`)"
      - "traefik.http.routers.my-tool.entrypoints=web"
      - "traefik.http.services.my-tool.loadbalancer.server.port=8080"
    networks:
      - default
      - traefik

networks:
  traefik:
    external: true
```

## Operations

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f isponsorblock

# Restart
docker compose restart isponsorblock
```
