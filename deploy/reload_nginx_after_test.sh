#!/usr/bin/env bash
# After editing nginx to include nginx-option-b-*.conf, run:
#   sudo bash deploy/reload_nginx_after_test.sh

set -euo pipefail
nginx -t
systemctl reload nginx
echo "nginx reloaded OK"
