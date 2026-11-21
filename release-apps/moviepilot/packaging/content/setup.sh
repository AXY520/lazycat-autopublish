#!/bin/sh
set -eu

netdisk=/lzcapp/run/mnt/home
if [ -z "${LAZYCAT_APP_DEPLOY_UID:-}" ] || ! mountpoint -q "$netdisk"; then
    printf '%s\n' 'MoviePilot 需要当前用户实例的懒猫网盘文稿挂载。' >&2
    exit 1
fi

project_dir="$netdisk/MoviePilot"
for path in "$project_dir" "$project_dir/downloads" "$project_dir/library"; do
    if [ -L "$path" ]; then
        printf 'MoviePilot 存储目录不能是符号链接：%s\n' "$path" >&2
        exit 1
    fi
done
if [ ! -d "$project_dir" ]; then
    # 网盘根目录由系统管理；项目目录由业务组共享，子目录继承该组。
    gosu "0:$PGID" mkdir -m 2775 -- "$project_dir"
fi
gosu "$PUID:$PGID" mkdir -p -- "$project_dir/downloads" "$project_dir/library"
if ! gosu "$PUID:$PGID" sh -c '[ -w "$1" ] && [ -w "$2" ]' sh "$project_dir/downloads" "$project_dir/library"; then
    printf '%s\n' 'MoviePilot 进程无法写入网盘的下载或媒体库目录。' >&2
    exit 1
fi

# 镜像会从这两个位置之一读取启动脚本。CloakBrowser 首次使用时自行下载内核。
for entrypoint in /app/docker/entrypoint.sh /usr/local/lib/moviepilot/control/entrypoint.sh; do
    if [ -f "$entrypoint" ] && grep -qx 'ensure_browser_kernel' "$entrypoint"; then
        sed -i '/^ensure_browser_kernel$/d' "$entrypoint"
        bash -n "$entrypoint"
    fi
done
