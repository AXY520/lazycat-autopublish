#!/usr/bin/env bash
# 用包内初始化脚本和空缓存验证核心服务可在无外网时启动。
set -euo pipefail

image="${1:?缺少 MoviePilot amd64 镜像}"
lpk="${2:?缺少 MoviePilot LPK}"
docker_cli="${DOCKER:-docker}"
test_dir="$(mktemp -d)"
container=""
cleanup() {
  if [[ -n "$container" ]]; then
    "$docker_cli" rm -f "$container" >/dev/null
  fi
  rm -rf -- "$test_dir"
}
trap cleanup EXIT

tar -xOf "$lpk" content.tar | tar -xOf - setup.sh > "$test_dir/setup.sh"
sh -n "$test_dir/setup.sh"
container="$("$docker_cli" create --platform linux/amd64 --network none \
  --tmpfs /config --tmpfs /moviepilot-cache --tmpfs /lzcapp/run/mnt/home \
  -e LAZYCAT_APP_DEPLOY_UID=smoke -e PUID=918 -e PGID=918 -e UMASK=022 \
  -e PACKAGE_CACHE_ROOT=/moviepilot-cache/packages -e CLOAKBROWSER_CACHE_DIR=/moviepilot-cache/cloakbrowser \
  -e MOVIEPILOT_AUTO_UPDATE=false -e MOVIEPILOT_UPDATE_DEV=false -e TINI_SUBREAPER=1 \
  --entrypoint /bin/sh "$image" -ec \
  'mkdir -p /lzcapp/pkg/content; cp /tmp/moviepilot-lpk-setup.sh /lzcapp/pkg/content/setup.sh
   /bin/sh /lzcapp/pkg/content/setup.sh; exec /usr/bin/tini -g -- /entrypoint.sh')"
"$docker_cli" cp "$test_dir/setup.sh" "$container:/tmp/moviepilot-lpk-setup.sh"
"$docker_cli" start "$container" >/dev/null

for (( attempt = 0; attempt < 45; attempt++ )); do
  if "$docker_cli" exec "$container" /usr/bin/curl -fsS --fail-early --max-time 2 \
      http://127.0.0.1:3001/health/ready http://127.0.0.1:3000/ >/dev/null 2>&1; then
    logs="$("$docker_cli" logs "$container" 2>&1)"
    if grep -Eq '确保 CloakBrowser 浏览器内核可用|Stealth Chromium .*Downloading' <<< "$logs"; then
      printf '%s\n' '启动时仍在尝试下载 CloakBrowser 内核。' >&2
      break
    fi
    printf '%s\n' '空缓存启动通过，后端 readiness 和前端均已响应。'
    exit 0
  fi
  [[ "$("$docker_cli" inspect --format '{{.State.Running}}' "$container")" == true ]] || break
  sleep 2
done

"$docker_cli" logs --tail 100 "$container" >&2
exit 1
