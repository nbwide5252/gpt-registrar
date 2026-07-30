FROM python:3.11-slim-bookworm
LABEL description="GPT Registrator - VPS Docker"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget ca-certificates gnupg lsb-release \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium 2>/dev/null || true
RUN python -m playwright install-deps chromium 2>/dev/null || true

RUN curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg 2>/dev/null; \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main" > /etc/apt/sources.list.d/cloudflare-client.list; \
    apt-get update -qq 2>/dev/null; \
    apt-get install -y -qq cloudflare-warp 2>/dev/null || true

COPY . .
RUN mkdir -p outputs/tokens logs
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]