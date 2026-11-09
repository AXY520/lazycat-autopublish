#!/usr/bin/env python3
"""修补 lzc-cli 的 docker-save 解包器（embed 打包用）。

问题：lzc-cli 用 tar 模块流式读取 docker save 归档，并允许消费者在条目
中途 await。GitHub runner 上会随机截断/错位某些层的 tar 数据，产出的 lpk
在 `scripts/verify_lpk.py` 里报 diff_id 不符（同一 commit 多次构建坏层不同）。

做法：把 walkDockerArchive 换成「先 tar.x 解包到临时目录、再逐文件串行回调」，
不共享解析流，结果稳定。上游修好后可删除本脚本。

用法: patch_lzc_cli.py <lpk_build_images_pack_local.js>
"""

import sys
from pathlib import Path

MARKER = "async function walkDockerArchive(archivePath, onEntry) {"

REPLACEMENT = """async function walkDockerArchive(archivePath, onEntry) {
\tconst extractDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lzc-docker-archive-'));
\ttry {
\t\tawait tar.x({ file: archivePath, cwd: extractDir, strict: true });
\t\tconst files = [];
\t\tconst walk = (dir, rel) => {
\t\t\tfor (const name of fs.readdirSync(dir).sort()) {
\t\t\t\tconst abs = path.join(dir, name);
\t\t\t\tconst relPath = rel ? rel + '/' + name : name;
\t\t\t\tconst st = fs.statSync(abs);
\t\t\t\tif (st.isDirectory()) walk(abs, relPath);
\t\t\t\telse if (st.isFile()) files.push({ abs, relPath, size: st.size });
\t\t\t}
\t\t};
\t\twalk(extractDir, '');
\t\tfor (const file of files) {
\t\t\tawait onEntry({
\t\t\t\tpath: file.relPath,
\t\t\t\tsize: file.size,
\t\t\t\tresume() {},
\t\t\t\tdestroy() {},
\t\t\t\ton() {},
\t\t\t\t[Symbol.asyncIterator]: () => fs.createReadStream(file.abs)[Symbol.asyncIterator](),
\t\t\t});
\t\t}
\t} finally {
\t\tfs.rmSync(extractDir, { recursive: true, force: true });
\t}
}
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: patch_lzc_cli.py <lpk_build_images_pack_local.js>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    text = path.read_text()
    if "lzc-docker-archive-" in text:
        print(f"{path.name}: 已修补，跳过")
        return 0
    start = text.find(MARKER)
    if start < 0:
        print(f"{path}: 找不到 walkDockerArchive", file=sys.stderr)
        return 1
    end = text.find("\n}\n", start)
    if end < 0:
        print(f"{path}: walkDockerArchive 没有结束括号", file=sys.stderr)
        return 1
    patched = text[:start] + REPLACEMENT + text[end + len("\n}\n") :]
    path.write_text(patched)
    print(f"{path.name}: 已替换 walkDockerArchive（tar.x 解包后逐文件回调）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
