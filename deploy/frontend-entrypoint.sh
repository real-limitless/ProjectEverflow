#!/bin/sh
# Configure nginx DNS resolver from the container's resolv.conf so /api proxy
# works on both Docker (127.0.0.11) and Podman (network gateway, e.g. 10.89.x.1).
set -eu

CONF=/etc/nginx/conf.d/default.conf
TEMPLATE=/etc/nginx/templates/default.conf.template

# Prefer explicit resolvers; always include Docker embedded DNS when present.
NS_LIST=""
if [ -r /etc/resolv.conf ]; then
  # shellcheck disable=SC2013
  for ns in $(awk '/^nameserver/ { print $2 }' /etc/resolv.conf); do
    case "$ns" in
      ''|*[!0-9.]*) continue ;;
    esac
    NS_LIST="${NS_LIST} ${ns}"
  done
fi
# Fallbacks if resolv.conf was empty / unusual
NS_LIST="${NS_LIST} 127.0.0.11 10.89.0.1 10.88.0.1"
# Dedupe while preserving order
RESOLVERS=""
for ns in $NS_LIST; do
  case " ${RESOLVERS} " in
    *" ${ns} "*) ;;
    *) RESOLVERS="${RESOLVERS} ${ns}" ;;
  esac
done
RESOLVERS=$(echo "$RESOLVERS" | sed 's/^ *//')

if [ -f "$TEMPLATE" ]; then
  sed "s/__EVERFLOW_RESOLVERS__/${RESOLVERS}/g" "$TEMPLATE" > "$CONF"
else
  # In-place patch of baked config (upgrade path)
  if grep -q 'resolver ' "$CONF" 2>/dev/null; then
    sed -i "s/resolver [^;]*;/resolver ${RESOLVERS} valid=10s ipv6=off;/" "$CONF"
  fi
fi

echo "everflow-frontend: nginx resolver → ${RESOLVERS}"

exec nginx -g 'daemon off;'
