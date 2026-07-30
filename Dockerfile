FROM python:3.11-slim-bookworm
RUN apt-get update -qq && apt-get install -y --no-install-recommends build-essential curl ca-certificates gnupg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p outputs/tokens logs
ENTRYPOINT ["python3","deploy/menu.py"]
