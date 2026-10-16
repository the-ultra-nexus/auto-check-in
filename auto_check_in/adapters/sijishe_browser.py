"""司机社浏览器适配器：用真实 Chrome 完成登录与签到。

纯 HTTP 客户端（``sijishe.py``）无法通过 Cloudflare 的 JS 质询——``requests`` 没有
JS 引擎，无论出口 IP 好坏都会被质询页拦下。本适配器把整条链路放进浏览器：

- 出口代理由 ``--proxy-server`` 指向本地 mihomo（见 ``browser.py``）
- ``cf_clearance`` 绑定 TLS 指纹与会话，**不能**交给 HTTP 客户端复用，所以登录与
  签到都在同一个浏览器会话内完成
- 解析与状态机复用 ``discuz.py`` / ``models.py`` / ``session.py``，不重复实现

Chrome 通过 Selenium 驱动；runner 与开发机都需可用的 Chrome 与匹配的 ChromeDriver。
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from lxml import etree

from ..browser import BrowserError, build_driver
from ..config import SiteConfig
from ..discuz import (
    DISCUZ_ALREADY_MARKERS,
    classify_discuz_response,
    extract_formhash,
)
from ..errors import CheckInError, LoginBlockedError, LoginError
from ..log import logger
from ..models import Account, AccountResult, CheckInStatus
from ..proxy_setup import API_PORT as PROXY_API_PORT, switch_to_next
from ..security import mask_username, redact_text
from ..session import SessionCacheStats, load_cookies, save_cookies

CHALLENGE_MARKERS = ("Just a moment", "cf-challenge", "Checking your browser")
# 质询等待上限。免费节点波动大，等太久不如换节点：实测可用节点 4–6s 就能
# 加载完，卡过 15s 基本就是被这个出口拦住了，换一个比继续等划算。
CHALLENGE_TIMEOUT_SECONDS = 15
LOGIN_TIMEOUT_SECONDS = 90
# 免费源里可用节点很多，被 CF 拦下就换一个，比原地重试划算。
MAX_NODE_SWITCHES = 4


class CloudflareBlocked(RuntimeError):
    """当前节点被 Cloudflare 拦下（质询页或 renderer 挂死）→ 换节点重试。"""


def _get_with_retry(driver: Any, url: str, retries: int = 1) -> None:
    """打开页面，超时后刷新重试一次。

    免费节点波动大，sign/登录页在 CF 质询下 headless Chrome 易挂死。
    只重试一次：再挂就抛给 run() 换节点，比在这个出口上反复等划算。
    """
    from selenium.common.exceptions import TimeoutException

    for attempt in range(retries + 1):
        try:
            driver.get(url)
            return
        except TimeoutException:
            if attempt < retries:
                try:
                    driver.refresh()
                except Exception:
                    pass
            else:
                raise


class SijisheBrowserAdapter:
    """Drive a real browser through the Discuz login dialog and sign-in endpoint."""

    def __init__(
        self,
        config: SiteConfig,
        driver_factory: Callable[[], Any] | None = None,
        challenge_timeout_seconds: int = CHALLENGE_TIMEOUT_SECONDS,
        node_switcher: Callable[[set[str]], str | None] | None = None,
        api_port: int = PROXY_API_PORT,
    ):
        self.config = config
        self._driver_factory = driver_factory or (
            lambda: build_driver(config.network.proxy_url)
        )
        self._stats = SessionCacheStats()
        self._challenge_timeout = challenge_timeout_seconds
        self._api_port = api_port
        self._node_switcher = node_switcher or (
            lambda exclude: switch_to_next(self._api_port, exclude)
        )

    @property
    def session_cache_stats(self) -> SessionCacheStats:
        return self._stats

    @contextmanager
    def _new_driver(self) -> Iterator[Any]:
        driver = self._driver_factory()
        try:
            yield driver
        finally:
            quit_driver = getattr(driver, "quit", None)
            if callable(quit_driver):
                try:
                    quit_driver()
                except Exception:
                    pass

    # --- 页面状态判定 -------------------------------------------------------

    @staticmethod
    def _title(driver: Any) -> str:
        try:
            return driver.title or ""
        except Exception:
            return ""

    @staticmethod
    def _source(driver: Any) -> str:
        try:
            return driver.page_source or ""
        except Exception:
            return ""

    def _wait_clear(self, driver: Any, timeout: int | None = None) -> bool:
        """Wait out the Cloudflare interstitial.

        Judge by ``driver.title`` only: Cloudflare injects ``challenge-platform``
        and ``__CF$cv$params`` into **successful** pages too, so matching those
        strings reports a false challenge on a page that actually loaded.
        """
        deadline = time.time() + (self._challenge_timeout if timeout is None else timeout)
        while time.time() < deadline:
            title = self._title(driver)
            if title and not any(marker in title for marker in CHALLENGE_MARKERS):
                return True
            time.sleep(1)
        return False

    def _is_logged_in(self, driver: Any) -> bool:
        """Auth cookie first (cheap); fall back to the JD_sign link on the page."""
        try:
            cookies = driver.get_cookies()
        except Exception:
            cookies = []
        if any(c.get("name", "").endswith("_auth") and c.get("value") for c in cookies):
            return True
        root = etree.HTML(self._source(driver))
        if root is not None:
            node = root.xpath('//a[@id="JD_sign"]')
            if node:
                href = node[0].get("href", "") or ""
                return not ("mod=logging" in href and "action=login" in href)
        return False

    # --- 会话缓存 -----------------------------------------------------------

    def _restore_session(self, driver: Any, username: str) -> bool:
        if not self.config.session_cache:
            return False
        cookies = load_cookies(
            self.config.session_dir,
            self.config.name,
            username,
            self.config.session_max_age_seconds,
        )
        if not cookies:
            logger.info(
                "session-cache site=%s account=%s event=restore-miss",
                self.config.name,
                mask_username(username),
            )
            return False
        # 必须先在目标域下加载页面，add_cookie 才被允许
        driver.get(self.config.base_url)
        self._wait_clear(driver, timeout=30)
        added = 0
        for name, value in cookies.items():
            try:
                driver.add_cookie({"name": name, "value": value, "domain": _domain(self.config.base_url)})
                added += 1
            except Exception:
                continue
        if added:
            self._stats = self._stats.bump(restored=1)
            logger.info(
                "session-cache site=%s account=%s event=restored cookies=%d",
                self.config.name,
                mask_username(username),
                added,
            )
        return bool(added)

    @staticmethod
    def _clear_cookies(driver: Any) -> None:
        """Drop every cookie so a stale *_auth cannot fake a live session."""
        try:
            driver.delete_all_cookies()
        except Exception:
            pass

    def _persist_session(self, driver: Any, username: str) -> None:
        if not self.config.session_cache:
            logger.info(
                "session-cache site=%s account=%s event=persist-skipped reason=disabled",
                self.config.name,
                mask_username(username),
            )
            return
        try:
            jar = {c["name"]: c["value"] for c in driver.get_cookies() if c.get("value")}
        except Exception:
            return
        if not any(name.endswith("_auth") for name in jar):
            logger.info(
                "session-cache site=%s account=%s event=persist-skipped reason=no-auth-cookie",
                self.config.name,
                mask_username(username),
            )
            return
        save_cookies(self.config.session_dir, self.config.name, username, jar)
        self._stats = self._stats.bump(saved=1)
        logger.info(
            "session-cache site=%s account=%s event=saved cookies=%d",
            self.config.name,
            mask_username(username),
            len(jar),
        )

    # --- 主流程 -------------------------------------------------------------

    def run(self, account: Account) -> AccountResult:
        """跑一次签到；被 Cloudflare 拦下就换节点重试。

        免费源里可用节点很多，被拦时换节点远比原地等待划算——换一个干净出口
        往往一次就过。
        """
        tried: set[str] = set()
        last_error = "未知错误"
        for attempt in range(MAX_NODE_SWITCHES + 1):
            try:
                return self._run_once(account)
            except CloudflareBlocked as exc:
                last_error = str(exc)
                if attempt >= MAX_NODE_SWITCHES:
                    break
                logger.info(
                    "site=%s account=%s 被 Cloudflare 拦下，换节点重试（第 %d 次）：%s",
                    self.config.name,
                    mask_username(account.username),
                    attempt + 1,
                    last_error,
                )
                # 排除当前节点，避免换到同一个
                current = getattr(self, "_current_node", None)
                if current:
                    tried.add(current)
                nxt = self._node_switcher(tried)
                if not nxt:
                    break
                self._current_node = nxt
        return AccountResult(
            account.username,
            CheckInStatus.ERROR,
            f"多次换节点后仍被 Cloudflare 拦下：{redact_text(last_error)[:150]}",
        )

    def _run_once(self, account: Account) -> AccountResult:
        try:
            with self._new_driver() as driver:
                base = self.config.base_url.rstrip("/")
                sign_page = f"{base}{self.config.sign_path}"
                restored = self._restore_session(driver, account.username)
                if not self._is_logged_in(driver):
                    self._login(driver, base, sign_page, account)
                result = self._sign_in(driver, base, sign_page, account.username)
                if result.status is CheckInStatus.LOGIN_FAILED and restored:
                    self._stats = self._stats.bump(rejected=1)
                    logger.info(
                        "session-cache site=%s account=%s event=rejected",
                        self.config.name,
                        mask_username(account.username),
                    )
                    # 缓存里的 *_auth 让 _is_logged_in 误判为已登录，但服务端会话已失效；
                    # 不清掉它，重登会被同一个陈旧 cookie 再次骗过。
                    self._clear_cookies(driver)
                    self._login(driver, base, sign_page, account)
                    result = self._sign_in(driver, base, sign_page, account.username)
                self._persist_session(driver, account.username)
                return result
        except CloudflareBlocked:
            raise  # 交给 run() 换节点
        except LoginBlockedError as exc:
            return AccountResult(account.username, CheckInStatus.LOGIN_BLOCKED, str(exc))
        except LoginError as exc:
            return AccountResult(account.username, CheckInStatus.LOGIN_FAILED, str(exc))
        except CheckInError as exc:
            return AccountResult(account.username, CheckInStatus.CHECK_IN_FAILED, str(exc))
        except BrowserError as exc:
            return AccountResult(
                account.username, CheckInStatus.SITE_UNAVAILABLE, redact_text(str(exc))[:200]
            )
        except Exception as exc:
            # renderer 挂死是当前节点被 CF 拦住的最典型表现，换节点即可。
            from selenium.common.exceptions import WebDriverException

            if isinstance(exc, WebDriverException):
                raise CloudflareBlocked(f"浏览器被拦：{type(exc).__name__}") from exc
            detail = redact_text(str(exc))[:200] or "未知异常"
            logger.warning(
                "site=%s account=%s 浏览器运行异常: %s",
                self.config.name,
                mask_username(account.username),
                detail,
            )
            return AccountResult(
                account.username,
                CheckInStatus.ERROR,
                f"运行过程中发生未预期错误：{detail}",
            )

    def _login(self, driver: Any, base: str, sign_page: str, account: Account) -> None:
        from selenium.webdriver.common.by import By

        for attempt in range(self.config.network.retries):
            if attempt > 0 and self.config.network.retry_delay_seconds > 0:
                time.sleep(self.config.network.retry_delay_seconds)
            logger.debug("login step=page site=%s attempt=%d", self.config.name, attempt + 1)
            _get_with_retry(driver, f"{base}/member.php?mod=logging&action=login")
            if not self._wait_clear(driver):
                # 质询迟迟不过，换节点比继续等这个出口划算
                raise CloudflareBlocked("登录页 Cloudflare 质询未通过")
            try:
                form = driver.find_element(By.XPATH, '//form[.//input[@name="username"]]')
                username_input = form.find_element(By.CSS_SELECTOR, 'input[name="username"]')
                password_input = form.find_element(By.CSS_SELECTOR, 'input[name="password"]')
            except Exception:
                logger.debug("login step=form site=%s event=not-found", self.config.name)
                continue
            username_input.clear()
            username_input.send_keys(account.username)
            password_input.clear()
            password_input.send_keys(account.password)
            logger.debug("login step=submit site=%s", self.config.name)
            submit = None
            for selector in ('button[type="submit"]', 'input[type="submit"]', "button.pn", "#loginsubmit"):
                try:
                    submit = form.find_element(By.CSS_SELECTOR, selector)
                    break
                except Exception:
                    continue
            if submit is None:
                continue
            try:
                submit.click()
            except Exception as exc:
                raise LoginBlockedError(f"登录提交失败：{type(exc).__name__}") from exc
            deadline = time.time() + 30
            while time.time() < deadline and not self._is_logged_in(driver):
                time.sleep(1)
            if self._is_logged_in(driver):
                return
        raise LoginError("登录失败：多次尝试后仍未登录")

    def _sign_in(
        self, driver: Any, base: str, sign_page: str, username: str
    ) -> AccountResult:
        from selenium.webdriver.common.by import By

        for _ in range(2):
            _get_with_retry(driver, sign_page)
            if not self._wait_clear(driver):
                raise CloudflareBlocked("签到页 Cloudflare 质询未通过")
            html = self._source(driver)
            if any(marker in html for marker in DISCUZ_ALREADY_MARKERS):
                return AccountResult(username, CheckInStatus.ALREADY_CHECKED_IN)
            formhash = extract_formhash(html)
            if not formhash:
                raise CheckInError("签到页缺少 formhash")
            url = (
                f"{base}/plugin.php?id=k_misign:sign&operation=qiandao"
                f"&formhash={formhash}&format=empty&inajax=1&ajaxtarget=JD_sign"
            )
            # 在页面内用站点自身的 AJAX 方式提交，携带浏览器真实会话
            try:
                body = driver.execute_async_script(_QIANDAO_JS, url)
            except Exception as exc:
                raise CheckInError(f"签到请求执行失败：{type(exc).__name__}") from exc
            if not isinstance(body, str):
                raise CheckInError("签到响应格式异常")
            status, message = classify_discuz_response(body)
            if status in {CheckInStatus.SUCCESS, CheckInStatus.ALREADY_CHECKED_IN}:
                return AccountResult(username, status, message)
            if status is CheckInStatus.LOGIN_FAILED:
                return AccountResult(username, status, message)
            last_message = message or "签到接口未确认成功"
        return AccountResult(username, CheckInStatus.CHECK_IN_FAILED, last_message)

def _domain(url: str) -> str:
    """Bare host for add_cookie (no scheme, no leading dot)."""
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return host.split(":", 1)[0]


_QIANDAO_JS = r"""
var cb = arguments[arguments.length - 1], url = arguments[0];
fetch(url, {credentials: 'include',
            headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': '*/*'}})
  .then(function (r) { return r.text().then(function (t) { cb(t); }); })
  .catch(function (e) { cb(''); });
"""
