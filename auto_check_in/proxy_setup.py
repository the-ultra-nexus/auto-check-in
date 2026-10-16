"""起一个本地 mihomo，把浏览器出口切到订阅节点。

为什么需要：Cloudflare 对 GitHub runner 的机房 IP 段风险判定高，直连时
``plugin.php`` 会被质询页拦下。实测经订阅节点（机房或非机房均可）接口可达，
所以 CI 里先把出口换掉，再让浏览器走本地代理端口。

订阅源是公开的 raw 链接，无需凭据；节点定义原样使用，只有 rules 被替换
（订阅自带 9000+ 条含 GEOIP 的规则会触发 MMDB 下载，受限网络下超时即 fatal）。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

DEFAULT_SUBSCRIPTION = (
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/clash-meta-2.yaml"
)
CORE_RELEASE = (
    "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/"
    "mihomo-{platform}-compatible-v1.19.32.gz"
)


def _platform_tag() -> str:
    """Release asset platform tag for the host, so local runs work too."""
    import platform

    machine = platform.machine().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(
        machine, "amd64"
    )
    system = platform.system().lower()
    os_tag = {"linux": "linux", "darwin": "darwin"}.get(system, "linux")
    return f"{os_tag}-{arch}"
PROXY_PORT = 7890
API_PORT = 9090


class ProxySetupError(RuntimeError):
    """Raised when the local proxy cannot be brought up."""


def _download(url: str, dest: Path, timeout: int = 120) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed hosts
        dest.write_bytes(response.read())


def _core_binary(work: Path) -> Path:
    """Fetch the mihomo core unless one is already on PATH."""
    found = shutil.which("mihomo")
    if found:
        return Path(found)
    target = work / "mihomo"
    if target.exists():
        return target
    archive = work / "mihomo.gz"
    _download(CORE_RELEASE.format(platform=_platform_tag()), archive)
    import gzip

    target.write_bytes(gzip.decompress(archive.read_bytes()))
    target.chmod(0o755)
    return target


def _fetch_subscription(url: str, dest: Path) -> None:
    _download(url, dest, timeout=60)
    if dest.stat().st_size < 1024:
        raise ProxySetupError("订阅内容过小，可能拉取失败")


def _write_config(subscription: Path, out: Path, proxy_port: int, api_port: int) -> list[str]:
    """Rewrite the subscription into a local-only config; return node names."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ProxySetupError("缺少 pyyaml，无法解析订阅") from exc

    data = yaml.safe_load(subscription.read_text(encoding="utf-8", errors="replace")) or {}
    proxies = [p for p in (data.get("proxies") or []) if isinstance(p, dict) and p.get("name")]
    if not proxies:
        raise ProxySetupError("订阅里没有可用节点")
    names = [p["name"] for p in proxies]

    config = {
        "mixed-port": proxy_port,
        "allow-lan": False,
        "mode": "global",
        "log-level": "warning",
        "ipv6": False,
        "external-controller": f"127.0.0.1:{api_port}",
        "proxies": proxies,
        "proxy-groups": [{"name": "GLOBAL", "type": "select", "proxies": names}],
        "rules": ["MATCH,GLOBAL"],
    }
    out.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return names


def _probe_node(api_port: int, name: str, proxy_port: int, timeout: float = 20.0) -> bool:
    """Switch to a node and check the target is reachable through it."""
    import json
    import urllib.error

    def api(method: str, path: str, payload: dict | None = None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{api_port}{path}",
            method=method,
            data=json.dumps(payload).encode() if payload else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - localhost
            return json.loads(response.read() or b"{}")

    try:
        api("PUT", "/proxies/GLOBAL", {"name": name})
    except Exception:
        return False
    time.sleep(0.5)
    # 用目标站点做探针：质询页也会返回 403，但 TCP 能通即说明节点可用
    try:
        request = urllib.request.Request(
            "https://xsijishe.net/k_misign-sign.html",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(
                {"http": f"http://127.0.0.1:{proxy_port}", "https": f"http://127.0.0.1:{proxy_port}"}
            )
        )
        opener.open(request, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        # 有 HTTP 响应（含 403 质询）说明链路通，浏览器可以自己去过质询
        return True
    except Exception:
        return False


def setup(subscription_url: str, work_dir: Path, proxy_port: int, api_port: int) -> int:
    work_dir.mkdir(parents=True, exist_ok=True)
    core = _core_binary(work_dir)
    subscription = work_dir / "subscription.yaml"
    _fetch_subscription(subscription_url, subscription)
    config = work_dir / "config.yaml"
    names = _write_config(subscription, config, proxy_port, api_port)

    log = (work_dir / "mihomo.log").open("wb")
    process = subprocess.Popen(
        [str(core), "-d", str(work_dir), "-f", str(config)], stdout=log, stderr=log
    )
    time.sleep(4)
    if process.poll() is not None:
        raise ProxySetupError(f"mihomo 启动失败，见 {work_dir / 'mihomo.log'}")

    for name in names:
        if _probe_node(api_port, name, proxy_port):
            print(f"已选定节点 #{names.index(name) + 1}/{len(names)}", flush=True)
            return 0
    raise ProxySetupError("所有节点均不可用")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动本地代理供浏览器使用")
    parser.add_argument("--subscription", default=DEFAULT_SUBSCRIPTION)
    parser.add_argument("--work-dir", default="/tmp/auto-check-in-proxy")
    parser.add_argument("--proxy-port", type=int, default=PROXY_PORT)
    parser.add_argument("--api-port", type=int, default=API_PORT)
    args = parser.parse_args(argv)
    try:
        return setup(args.subscription, Path(args.work_dir), args.proxy_port, args.api_port)
    except ProxySetupError as exc:
        print(f"代理启动失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
