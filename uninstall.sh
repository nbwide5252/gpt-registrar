#!/bin/bash
echo === Uninstall GPT Registrator ===
docker compose -f /opt/gpt-registrar/docker-compose.yml down -v 2>/dev/null || true
docker rm -f gpt-registrar 2>/dev/null || true
docker rmi gpt-registrar-gpt 2>/dev/null || true
docker image prune -f 2>/dev/null || true
rm -rf /opt/gpt-registrar 2>/dev/null
rm -f /usr/local/bin/gpt 2>/dev/null
if command -v warp-cli >/dev/null 2>&1; then warp-cli disconnect 2>/dev/null; warp-cli delete 2>/dev/null; apt-get purge -y cloudflare-warp 2>/dev/null; rm -f /etc/apt/sources.list.d/cloudflare-client.list 2>/dev/null; fi
apt-get autoremove -y 2>/dev/null; apt-get clean 2>/dev/null
rm -rf /root/.cache/pip 2>/dev/null
echo Done.
