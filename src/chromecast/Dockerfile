FROM python:3.12-slim

WORKDIR /app

# Install system deps for zeroconf/mDNS (pychromecast discovery)
RUN apt-get update && apt-get install -y --no-install-recommends \
    avahi-daemon \
    libavahi-compat-libdnssd1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY chromecast_cli.py .

EXPOSE 7655

CMD ["python", "server.py"]
