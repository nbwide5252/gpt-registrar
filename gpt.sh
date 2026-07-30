#!/bin/bash
CMD=""
case "" in
    batch)  COUNT=""; docker exec -it gpt-registrar python3 deploy/menu.py 2>/dev/null || { cd /opt/gpt-registrar && docker compose up -d && docker exec -it gpt-registrar python3 deploy/menu.py; } ;;
    help|--help|-h) echo "GPT自动注册机"; echo "  gpt          打开菜单"; echo "  gpt batch 10 批量注册10个"; echo "  gpt config   配置管理"; echo "  gpt balance  SMS余额" ;;
    *) docker exec -it gpt-registrar python3 deploy/menu.py 2>/dev/null || { cd /opt/gpt-registrar && docker compose up -d && docker exec -it gpt-registrar python3 deploy/menu.py; } ;;
esac