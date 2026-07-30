#!/bin/bash
cd /opt/gpt-registrar
git pull 2>/dev/null
docker compose up -d --build 2>/dev/null || docker-compose up -d --build
echo Updated
