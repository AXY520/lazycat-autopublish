#!/usr/bin/env python3
"""通过喵喵商店 MCP 更新已有的 MoviePilot 应用。"""

import itertools
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


PACKAGE_ID = "org.moviepilot.lazycat"
MCP_URL = "https://apps.pushcat.eu.org/mcp"


class NoRedirect(HTTPRedirectHandler):
    """禁止将社区商店的令牌带到重定向地址。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """拒绝当前 HTTP 重定向。"""
        return None


class MCPClient:
    """处理喵喵商店 Streamable HTTP 的初始化和工具调用。"""

    def __init__(self, url, token):
        """使用仅对当前端点有效的 Bearer 令牌初始化会话。"""
        self.url = url
        self.opener = build_opener(NoRedirect())
        self.ids = itertools.count(1)
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "lazycat-autopublish/1.0",
        }
        result = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "lazycat-autopublish", "version": "1.0"},
        })
        self.headers["MCP-Protocol-Version"] = result["protocolVersion"]
        self.request("notifications/initialized", notification=True)

    def request(self, method, params=None, notification=False):
        """发送 MCP 消息并返回对应请求 ID 的结果。"""
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            message["id"] = next(self.ids)
        request = Request(self.url, json.dumps(message).encode(), self.headers, method="POST")
        with self.opener.open(request, timeout=60) as response:
            session = response.headers.get("MCP-Session-Id")
            if method == "initialize" and session:
                self.headers["MCP-Session-Id"] = session
            if notification:
                return None
            if response.headers.get_content_type() == "text/event-stream":
                data = []
                for line in response:
                    line = line.rstrip(b"\r\n")
                    if line.startswith(b"data:"):
                        data.append(line[5:].lstrip(b" "))
                    elif not line and data:
                        reply = json.loads(b"\n".join(data))
                        if reply.get("id") == message["id"]:
                            break
                        data.clear()
                else:
                    raise RuntimeError(f"{method} 未收到 MCP 响应")
            else:
                reply = json.load(response)
            if "error" in reply:
                raise RuntimeError(f"{method}: {reply['error'].get('message', 'MCP 请求失败')}")
            if reply.get("id") != message["id"]:
                raise RuntimeError(f"{method} 的 MCP 响应无法与请求匹配")
            return reply["result"]

    def tool(self, name, arguments):
        """调用商店工具，保留其业务成功或失败结果。"""
        return self.request("tools/call", {"name": name, "arguments": arguments})


def tool_error(result):
    """提取商店工具返回的文本错误。"""
    return " ".join(item["text"] for item in result["content"] if item["type"] == "text")


def publish(client, version, download_url, sha256):
    """提交新版本，返回商店是否已提供该版本。"""
    page = 1
    while True:
        result = client.tool("appstore_list_my_apps", {"query": PACKAGE_ID, "page": page})
        if result.get("isError"):
            raise RuntimeError(tool_error(result))
        listing = result["structuredContent"]
        app = next((item for item in listing["apps"] or [] if item["packageId"] == PACKAGE_ID), None)
        if app is not None:
            break
        next_page = listing.get("nextPage")
        if not isinstance(next_page, int) or next_page <= page:
            raise RuntimeError(f"令牌无法找到已有的商店应用 {PACKAGE_ID}")
        page = next_page

    current = app.get("latestVersion", "")
    if current == version and app["status"] == "APPROVED":
        print(f"喵喵商店已提供 MoviePilot {version}")
        return True
    if not app["canUploadVersion"]:
        raise RuntimeError(f"令牌没有为 {PACKAGE_ID} 上传版本的权限")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", current) and (
        tuple(map(int, current.split("."))) > tuple(map(int, version.split(".")))
    ):
        raise RuntimeError(f"喵喵商店版本 {current} 高于 GitHub Release {version}")

    result = client.tool("appstore_publish_version_from_url", {
        "packageId": PACKAGE_ID,
        "version": version,
        "downloadUrl": download_url,
        "sourceType": "GITHUB",
        "sha256": sha256,
        "changelog": f"上游发布说明：https://github.com/jxxghp/MoviePilot/releases/tag/v{version}",
    })
    if result.get("isError"):
        error = tool_error(result)
        if "UNIQUE constraint failed: app_versions.app_id, app_versions.version" in error or (
            "appversion_app_id_version" in error and "duplicate" in error.lower()
        ):
            print(f"喵喵商店已有 MoviePilot {version} 的记录，等待该版本可用")
            return False
        raise RuntimeError(error)

    published = result["structuredContent"]
    if (published["app"]["packageId"], published["version"]["version"], published["version"]["sha256"]) != (
        PACKAGE_ID, version, sha256,
    ):
        raise RuntimeError("社区商店返回的应用版本或校验值与 GitHub Release 不一致")
    status = published["version"]["status"]
    print(f"喵喵商店已接收 MoviePilot {version}，版本状态 {status}")
    return status == "APPROVED" and published["app"]["status"] == "APPROVED"


def main():
    """将商店可用状态写入 GitHub Actions 输出。"""
    version, url, sha256 = sys.argv[1:]
    token = os.environ["MOVIEPILOT_COMMUNITY_MCP_TOKEN"]
    try:
        ready = publish(MCPClient(MCP_URL, token), version, url, sha256)
    except HTTPError as exc:
        sys.exit(f"喵喵商店 MCP 请求失败，HTTP {exc.code}")
    except (URLError, TimeoutError, RuntimeError, KeyError, ValueError) as exc:
        sys.exit(f"喵喵商店同步失败：{str(exc).replace(token, '[redacted]')}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        print(f"ready={str(ready).lower()}", file=output)


if __name__ == "__main__":
    main()
