#!/usr/bin/env bash
# Firewall: SSH from anywhere, HTTP only from Cloudflare's published ranges.
# Cloudflare terminates TLS, so the origin only serves port 80. Re-run to
# refresh the Cloudflare ranges (they change rarely).
set -euo pipefail
v4=$(curl -fsS --max-time 15 https://www.cloudflare.com/ips-v4)
v6=$(curl -fsS --max-time 15 https://www.cloudflare.com/ips-v6)
n4=$(echo "$v4" | grep -c '/'); n6=$(echo "$v6" | grep -c '/')
if [ "$n4" -lt 10 ] || [ "$n6" -lt 5 ]; then
  echo "Cloudflare range list looks wrong (v4=$n4 v6=$n6); aborting" >&2; exit 1
fi
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'ssh'
# drop any old port-80 rules so refreshed ranges replace them
(ufw status numbered | grep -E "80/tcp.*Cloudflare" || true) | awk -F'[][]' '{print $2}' | sort -rn | while read n; do ufw --force delete "$n"; done
for r in $v4 $v6; do ufw allow proto tcp from "$r" to any port 80 comment 'Cloudflare'; done
ufw --force enable
ufw status | head -5
echo "rules: $(ufw status | grep -c Cloudflare) Cloudflare ranges allowed on 80"
