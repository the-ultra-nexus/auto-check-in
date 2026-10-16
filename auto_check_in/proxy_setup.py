"""起一个本地 mihomo，把浏览器出口切到订阅节点。

为什么需要：Cloudflare 对 GitHub runner 的机房 IP 段风险判定高，直连时
``plugin.php`` 会被质询页拦下。实测经订阅节点（机房或非机房均可）接口可达，
所以 CI 里先把出口换掉，再让浏览器走本地代理端口。

订阅源是公开的 raw 链接，无需凭据；节点定义原样使用，只有 rules 被替换
（订阅自带 9000+ 条含 GEOIP 的规则会触发 MMDB 下载，受限网络下超时即 fatal）。

选节点用 mihomo 的 url-test 组：**并行**测速全部节点，且以签到页返回 200 为健康标准，
所以只有真能过 Cloudflare 的节点会被选中。内置多个源并按顺序回退：免费节点寿命以小时计，
单个源随时可能整体失效，一次 CI 跑失败不该让签到整体停摆。
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

# 内置公开源，按顺序回退：免费节点寿命短，单个源随时可能整体失效。
# 三者均已用真实浏览器实测过目标站点（拿到 formhash、未被质询），
# 且都是今天仍在自动更新的仓库。
DEFAULT_SUBSCRIPTIONS = (
    "https://raw.githubusercontent.com/zhuhaiuk/free-nodes/main/clash_config.yaml",
    "https://raw.githubusercontent.com/shaoyouvip/free/main/mihomo.yaml",
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/clash-meta-2.yaml",
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
# 健康检查盯签到页面，而非 plugin.php：实测存在「plugin.php 能开、签到页在浏览器里
# 挂死」的节点，签到页才是浏览器成败的预测指标。expected-status=200 让 mihomo 只在
# 真过了 Cloudflare 的节点里挑，返回 403 质询页的节点会被直接排除。
HEALTH_CHECK_URL = "https://xsijishe.net/k_misign-sign.html"
HEALTH_TIMEOUT_MS = 5000


class ProxySetupError(RuntimeError):
    """Raised when the local proxy cannot be brought up."""


def _api(api_port: int, path: str, payload: dict | None = None):
    """Talk to mihomo's external controller on localhost."""
    import json

    request = urllib.request.Request(
        f"http://127.0.0.1:{api_port}{path}",
        method="PUT" if payload is not None else "GET",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - localhost
        return json.loads(response.read() or b"{}")


def api_select(api_port: int, name: str) -> None:
    """Point the GLOBAL group at one node via the external controller."""
    _api(api_port, "/proxies/GLOBAL", {"name": name})


def _group_delays(api_port: int) -> dict[str, int]:
    """Ask mihomo to re-test the whole group **in parallel**; return node → ms.

    This is the parallel sweep: one call tests every node at once, instead of
    the serial per-node probing that made picking a node so slow. It is also the
    only trustworthy signal — the group's ``now`` just echoes the first node in
    the list until a test runs, and the group's own ``history`` stays empty.
    """
    import urllib.parse

    path = (
        f"/group/GLOBAL/delay?url={urllib.parse.quote(HEALTH_CHECK_URL, safe='')}"
        f"&timeout={HEALTH_TIMEOUT_MS}"
    )
    try:
        return _api(api_port, path) or {}
    except Exception:
        return {}


def _ranked_nodes(api_port: int, exclude: set[str] | None = None) -> list[tuple[int, str]]:
    """Parallel-test every node; return ``[(ms, name)]`` fastest first.

    Nodes that failed the health check come back as 0 or missing, and are dropped.
    """
    excluded = exclude or set()
    return sorted(
        (ms, name)
        for name, ms in _group_delays(api_port).items()
        if isinstance(ms, int) and ms > 0 and name not in excluded
    )


def pick_fastest(api_port: int, exclude: set[str] | None = None) -> tuple[str, int] | None:
    """Choose and switch to the fastest healthy node, or ``None`` when none is left."""
    ranked = _ranked_nodes(api_port, exclude)
    if not ranked:
        return None
    ms, name = ranked[0]
    api_select(api_port, name)
    return name, ms


def switch_to_next(api_port: int, exclude: set[str]) -> str | None:
    """Pick the fastest node not already tried; ``None`` when none is left.

    Used when Cloudflare blocks the chosen node mid-run: the free pool has plenty
    of nodes, so switching beats waiting.
    """
    picked = pick_fastest(api_port, exclude)
    return picked[0] if picked else None


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
        "proxy-groups": [
            {
                # url-test 并行测速所有节点，只留下真能过 Cloudflare 的：
                # 签到页返回 200 才算健康，403 质询页的节点被自动排除。
                "name": "GLOBAL",
                "type": "url-test",
                "url": HEALTH_CHECK_URL,
                "interval": 300,
                "tolerance": 50,
                "lazy": False,
                "expected-status": 200,
                "proxies": names,
            }
        ],
        "rules": ["MATCH,GLOBAL"],
    }
    out.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return names


def _subscriptions(override: str) -> tuple[str, ...]:
    """用户指定了订阅就只用它；否则走内置源的顺序回退。"""
    return (override,) if override.strip() else DEFAULT_SUBSCRIPTIONS


def setup(subscription_url: str, work_dir: Path, proxy_port: int, api_port: int) -> int:
    work_dir.mkdir(parents=True, exist_ok=True)
    core = _core_binary(work_dir)
    urls = _subscriptions(subscription_url)
    errors: list[str] = []
    for index, url in enumerate(urls):
        work = work_dir if len(urls) == 1 else work_dir / f"sub{index}"
        work.mkdir(parents=True, exist_ok=True)
        try:
            return _setup_one(core, url, work, proxy_port, api_port, index, len(urls))
        except ProxySetupError as exc:
            # 单个源失效不能终止整个流程：免费源随时可能整体不可用，换下一个即可。
            errors.append(f"[{index + 1}/{len(urls)}] {url}\n  {exc}")
    raise ProxySetupError("所有订阅源均不可用：\n" + "\n".join(errors))


def _setup_one(
    core: Path, url: str, work: Path, proxy_port: int, api_port: int, index: int, total: int
) -> int:
    subscription = work / "subscription.yaml"
    _fetch_subscription(url, subscription)
    config = work / "config.yaml"
    names = _write_config(subscription, config, proxy_port, api_port)

    log = (work / "mihomo.log").open("wb")
    process = subprocess.Popen(
        [str(core), "-d", str(work), "-f", str(config)], stdout=log, stderr=log
    )
    time.sleep(4)
    if process.poll() is not None:
        raise ProxySetupError(f"mihomo 启动失败，见 {work / 'mihomo.log'}")
    try:
        # 并行测速全部节点并切到最快的一个（url-test 组自身的 now 在测速前
        # 只是列表首节点，不可信，必须显式触发一次测速）。
        picked = pick_fastest(api_port)
        if picked:
            name, ms = picked
            print(
                f"已选定节点 {name} 延迟 {ms}ms"
                f"（订阅源 {index + 1}/{total}，共 {len(names)} 节点）",
                flush=True,
            )
            return 0
        raise ProxySetupError("所有节点均不可用（无节点能通过签到页健康检查）")
    except BaseException:
        process.terminate()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动本地代理供浏览器使用")
    parser.add_argument(
        "--subscription",
        default="",
        help="指定单个订阅源；留空则按顺序尝试内置公开源",
    )
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
