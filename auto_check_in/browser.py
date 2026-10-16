"""Selenium Chrome factory for adapters that must clear Cloudflare's JS challenge.

A plain HTTP client cannot pass the challenge — it has no JS engine — so the whole
login/sign-in flow runs inside a real Chrome. The optional ``proxy_url`` points at a
local mihomo instance so the egress IP is a proxy node rather than the runner's.
"""

from __future__ import annotations

import shutil

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)

_CHROME_FLAGS = (
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-popup-blocking",
    "--window-size=1440,900",
    # 去掉 navigator.webdriver 之外最明显的自动化标记
    "--disable-blink-features=AutomationControlled",
)


# 页面加载上限。被 Cloudflare 拦住的出口会一直转圈，等太久不如让适配器
# 换节点：可用节点实测 4–6s 就能加载完，30s 已经足够宽松。
PAGE_LOAD_TIMEOUT_SECONDS = 30


class BrowserError(RuntimeError):
    """Raised when no usable browser can be started."""


def _chromedriver_path() -> str | None:
    """Prefer a system ChromeDriver (runner images ship one) over a download."""
    return shutil.which("chromedriver")


def build_driver(proxy_url: str | None = None, headless: bool = True):
    """Create a Chrome WebDriver configured to look like an ordinary browser.

    ``headless`` defaults to True; the runner has no display, and headless Chrome
    passes the page-level challenge (verified on both a dev machine and a runner).
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError as exc:  # pragma: no cover - depends on the install extra
        raise BrowserError(
            "未安装 selenium，无法使用浏览器适配器；请执行 uv sync（selenium 已是主依赖）"
        ) from exc

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    for flag in _CHROME_FLAGS:
        options.add_argument(flag)
    if proxy_url:
        options.add_argument(f"--proxy-server={proxy_url}")
    options.add_argument(f"--user-agent={DEFAULT_USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver_path = _chromedriver_path()
    service = Service(executable_path=driver_path) if driver_path else Service()
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as exc:
        raise BrowserError(f"Chrome 启动失败：{type(exc).__name__}") from exc

    # 隐藏 CDP 暴露的自动化标记
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
        )
    except Exception:
        pass
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
    driver.set_script_timeout(60)
    return driver
