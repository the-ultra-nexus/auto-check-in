#!/usr/bin/env bash
# 测试代理列表到目标的连通性（本地或 GitHub runner 均可）。
# 用法：
#   scripts/test_proxy_connectivity.sh 'http://a:80,http://b:8080'
#   scripts/test_proxy_connectivity.sh --target https://example.com < proxies.txt
#   cat proxies.txt | scripts/test_proxy_connectivity.sh
#   scripts/test_proxy_connectivity.sh 'https://cdn.jsdelivr.net/gh/.../data.txt'  # URL 列表源
# 代理格式：http://host:port，逗号分隔或每行一个；目标默认 xsijishe.net 签到页。
set -u

TARGET="https://xsijishe.net/k_misign-sign.html"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    -h|--help)
      echo "用法: $0 [--target URL] <proxy1 proxy2 ...>  或  cat proxies.txt | $0 [--target URL]"
      echo "     参数为带路径的 http(s):// URL 时自动当作代理列表源抓取"
      exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

tmp=$(mktemp)
SOURCES=()
PROXIES=()
if [ ${#ARGS[@]} -gt 0 ]; then
  for arg in "${ARGS[@]}"; do
    if printf '%s' "$arg" | grep -qE '^https?://[^/]+/.+'; then
      SOURCES+=("$arg")
    else
      PROXIES+=("$arg")
    fi
  done
fi

{
  if [ ${#PROXIES[@]} -gt 0 ]; then
    printf '%s\n' "${PROXIES[@]}"
  fi
  if [ ${#SOURCES[@]} -gt 0 ]; then
    for url in "${SOURCES[@]}"; do
      echo "-- 列表源: $url" >&2
      curl -sL --max-time 30 "$url"
    done
  fi
  if [ ${#PROXIES[@]} -eq 0 ] && [ ${#SOURCES[@]} -eq 0 ]; then
    cat
  fi
} | tr ',' '\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' > "$tmp"

echo "== 待测代理数: $(wc -l < "$tmp" | tr -d ' ')，目标: $TARGET =="
export TARGET
helper=$(mktemp)
cat > "$helper" <<'HELPER'
p="$1"
code=$(curl -x "$p" -I -s --connect-timeout 5 --max-time 15 -o /dev/null -w "%{http_code}" "$TARGET" 2>/dev/null)
rc=$?
if [ "${code:-000}" != "000" ]; then
  echo "OK   $p -> HTTP $code"
else
  case $rc in
    7)  echo "FAIL $p -> 代理不可达 (exit 7)";;
    28) echo "FAIL $p -> 超时 (exit 28)";;
    35|60) echo "FAIL $p -> TLS/证书 (exit $rc)";;
    *)  echo "FAIL $p -> 无响应 (exit $rc)";;
  esac
fi
HELPER
cat "$tmp" | xargs -P 10 -I{} bash "$helper" {} | sort
rm -f "$helper"
rm -f "$tmp"
