#!/bin/bash
CMD="${1:-menu}"
case "$CMD" in
    batch)  COUNT="${2:-5}"; docker exec -it gpt-registrar python3 deploy/menu.py 2>/dev/null || { cd /opt/gpt-registrar && docker compose up -d && docker exec -it gpt-registrar python3 deploy/menu.py; } ;;
    help|--help|-h) echo "GPT自动注册机"; echo "  gpt          打开菜单"; echo "  gpt batch 10 批量注册10个" ;;
    *) docker exec -it gpt-registrar python3 deploy/menu.py 2>/dev/null || { cd /opt/gpt-registrar && docker compose up -d && docker exec -it gpt-registrar python3 deploy/menu.py; } ;;
esac