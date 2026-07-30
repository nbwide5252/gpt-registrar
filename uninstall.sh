#!/bin/bash
echo === Uninstall GPT Registrator ===
docker compose -f /opt/gpt-registrar/docker-compose.yml down -v 2>/dev/null
docker rm -f gpt-registrar 2>/dev/null
docker rmi gpt-registrar-gpt 2>/dev/null
rm -rf /opt/gpt-registrar 2>/dev/null
rm -f /usr/local/bin/gpt 2>/dev/null
echo Done.