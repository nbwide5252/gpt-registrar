FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl wget ca-certificates iproute2 dbus libdbus-1-3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p outputs/tokens logs
ENTRYPOINT [" python3\,\deploy/menu.py\]