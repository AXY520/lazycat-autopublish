#!/usr/bin/env bash
# 使用懒猫官方仓库返回的镜像地址构建 MoviePilot x86_64 安装包。
set -euo pipefail

version="${1:?缺少 MoviePilot 版本}"
image="${2:?缺少懒猫官方镜像地址}"
output_dir="$(realpath -m "${3:?缺少输出目录}")"
app_dir="$(cd "$(dirname "$0")" && pwd)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "无效的稳定版本：$version" >&2; exit 1; }
[[ "$image" =~ ^registry\.lazycat\.cloud/[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+$ ]] || {
  echo '需要 copy-image 返回的懒猫官方仓库地址' >&2
  exit 1
}

mkdir -p "$output_dir"
stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT
cp "$app_dir"/packaging/{package.yml,lzc-manifest.yml,lzc-build.yml,icon.png} "$stage/"
cp -R "$app_dir/packaging/content" "$stage/"
sed -i -E "s/^version: .*/version: \"$version\"/" "$stage/package.yml"
sed -i -E "s#^    image: .*#    image: $image#" "$stage/lzc-manifest.yml"

asset="MoviePilot-$version-linux-amd64.lpk"
cd "$stage"
lzc-cli project release -o "$stage/$asset"
lzc-cli lpk lint "$stage/$asset"

entries="$(tar -tf "$asset")"
if grep -Eq '^(\./)?(images(/|$)|images\.lock$)' <<< "$entries"; then
  echo 'MoviePilot LPK 必须走官方镜像仓库引用' >&2
  exit 1
fi
test "$(stat -c %s "$asset")" -lt 200000000
mv -- "$asset" "$output_dir/$asset"
