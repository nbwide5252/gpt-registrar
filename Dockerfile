FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl wget ca-certificates gnupg iproute2 dbus libdbus-1-3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg 2>/dev/null; echo deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main > /etc/apt/sources.list.d/cloudflare-client.list; apt-get update -qq 2>/dev/null; apt-get install -y -qq cloudflare-warp 2>/dev/null || echo WARP optional

COPY . .
RUN mkdir -p outputs/tokens logs
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT [" bash\,\/entrypoint.sh\]
