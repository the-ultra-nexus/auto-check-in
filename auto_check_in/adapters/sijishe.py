"""司机社纯 HTTP 适配器：登录弹框表单 + 签到接口。"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

import requests
from lxml import etree

from ..config import SiteConfig
from ..discuz import (
    DISCUZ_ALREADY_MARKERS,
    classify_discuz_response,
    extract_formhash,
    md5_password,
    parse_login_dialog,
)
from ..errors import CheckInError, LoginBlockedError, LoginError
from ..http import SessionProvider, ua_headers
from ..log import logger
from ..models import Account, AccountResult, CheckInStatus
from ..security import mask_username, redact_text
from ..session import load_cookies, save_cookies


class SijisheAdapter:
    """Login via the Discuz popup dialog and sign in via the k_misign endpoint."""

    def __init__(
        self,
        config: SiteConfig,
        session_factory: Callable[[], Any] | None = None,
        session_provider: SessionProvider | None = None,
    ):
        self.config = config
        self._session_factory = session_factory
        self._session_provider = session_provider or SessionProvider(
            config.network,
            direct_first=config.direct_first,
            probe_url=f"{config.base_url.rstrip('/')}{config.sign_path}",
        )

    @contextmanager
    def _new_session(self) -> Iterator[Any]:
        if self._session_factory is not None:
            session = self._session_factory()
            try:
                yield session
            finally:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
            return
        session = self._session_provider.new_session()
        try:
            yield session
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                close()

    def run(self, account: Account) -> AccountResult:
        try:
            with self._new_session() as session:
                base = self.config.base_url.rstrip("/")
                sign_page = f"{base}{self.config.sign_path}"
                self._restore_session(session, account.username)
                if not self._is_logged_in(session, sign_page):
                    self._login(session, base, account)
                result = self._sign_in(session, base, account.username)
                if result.status is CheckInStatus.LOGIN_FAILED:
                    session.cookies.clear()
                    self._login(session, base, account)
                    result = self._sign_in(session, base, account.username)
                self._persist_session(session, account.username)
                return result
        except LoginBlockedError as exc:
            return AccountResult(account.username, CheckInStatus.LOGIN_BLOCKED, str(exc))
        except LoginError as exc:
            return AccountResult(account.username, CheckInStatus.LOGIN_FAILED, str(exc))
        except CheckInError as exc:
            return AccountResult(account.username, CheckInStatus.CHECK_IN_FAILED, str(exc))
        except requests.RequestException as exc:
            detail = redact_text(str(exc))[:200] or "网络请求失败"
            logger.warning(
                "site=%s account=%s 站点请求失败: %s",
                self.config.name,
                mask_username(account.username),
                detail,
            )
            return AccountResult(
                account.username,
                CheckInStatus.SITE_UNAVAILABLE,
                f"站点请求失败：{detail}",
            )
        except Exception as exc:
            detail = redact_text(str(exc))[:200] or "未知异常"
            logger.warning(
                "site=%s account=%s 运行异常: %s",
                self.config.name,
                mask_username(account.username),
                detail,
            )
            return AccountResult(
                account.username,
                CheckInStatus.ERROR,
                f"运行过程中发生未预期错误：{detail}",
            )

    def _restore_session(self, session: Any, username: str) -> None:
        if not self.config.session_cache:
            return
        for name, value in load_cookies(
            self.config.session_dir,
            self.config.name,
            username,
            self.config.session_max_age_seconds,
        ).items():
            session.cookies.set(name, value)

    def _persist_session(self, session: Any, username: str) -> None:
        if not self.config.session_cache:
            return
        cookies = session.cookies.get_dict()
        if any(name.endswith("_auth") and value for name, value in cookies.items()):
            save_cookies(self.config.session_dir, self.config.name, username, cookies)

    def _login(self, session: Any, base: str, account: Account) -> None:
        sign_page = f"{base}{self.config.sign_path}"
        session.get(
            sign_page,
            headers=ua_headers(),
            timeout=self.config.network.request_timeout_seconds,
        )
        for attempt in range(self.config.network.retries):
            if attempt > 0 and self.config.network.retry_delay_seconds > 0:
                time.sleep(self.config.network.retry_delay_seconds)
            logger.debug("login step=dialog-fetch site=%s", self.config.name)
            dialog = self._fetch_dialog(session, base)
            form = parse_login_dialog(dialog)
            logger.debug("login step=login-submit site=%s", self.config.name)
            self._post_login(session, base, sign_page, form, account)
            if self._is_logged_in(session, sign_page):
                return
        raise LoginError("登录失败：多次尝试后仍未登录")

    def _fetch_dialog(self, session: Any, base: str) -> str:
        url = (
            f"{base}/member.php?mod=logging&action=login&infloat=yes"
            "&handlekey=login&inajax=1&ajaxtarget=fwin_content_login"
        )
        response = session.get(
            url,
            headers=ua_headers({"X-Requested-With": "XMLHttpRequest"}),
            timeout=self.config.network.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.text

    def _post_login(
        self,
        session: Any,
        base: str,
        sign_page: str,
        form: dict[str, str],
        account: Account,
    ) -> None:
        url = (
            f"{base}/member.php?mod=logging&action=login&loginsubmit=yes"
            f"&handlekey=login&loginhash={form['loginhash']}&inajax=1"
        )
        data = {
            "formhash": form["formhash"],
            "referer": form["referer"] or sign_page,
            "username": account.username,
            "password": md5_password(account.password),
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
        }
        logger.debug(
            "login form fields: formhash=%s username=%s password_md5=%s",
            "filled" if form.get("formhash") else "missing",
            "filled" if account.username else "missing",
            "filled" if account.password else "missing",
        )
        response = session.post(
            url,
            data=data,
            headers=ua_headers({"Origin": base, "Referer": sign_page}),
            timeout=self.config.network.request_timeout_seconds,
        )
        status_code = response.status_code
        if status_code >= 400:
            if 400 <= status_code < 500:
                raise LoginBlockedError(
                    f"登录提交被站点拒绝（HTTP {status_code}）：站点可能启用了防机器人校验"
                    "或封禁了当前出口 IP，请核对账号密码并在本地验证"
                )
            response.raise_for_status()

    def _is_logged_in(self, session: Any, sign_page: str) -> bool:
        if any(cookie.name.endswith("_auth") and cookie.value for cookie in session.cookies):
            return True
        response = session.get(
            sign_page,
            headers=ua_headers(),
            timeout=self.config.network.request_timeout_seconds,
        )
        html = response.text
        root = etree.HTML(html)
        if root is not None:
            node = root.xpath('//a[@id="JD_sign"]')
            if node:
                href = node[0].get("href", "") or ""
                return not ("mod=logging" in href and "action=login" in href)
        return any(marker in html for marker in DISCUZ_ALREADY_MARKERS)

    def _sign_in(self, session: Any, base: str, username: str) -> AccountResult:
        logger.debug("sign-in step=sign-in site=%s", self.config.name)
        sign_page = f"{base}{self.config.sign_path}"
        timeout = self.config.network.request_timeout_seconds
        last_message = ""
        for _ in range(2):
            page = session.get(sign_page, headers=ua_headers(), timeout=timeout)
            page.raise_for_status()
            html = page.text
            if any(marker in html for marker in DISCUZ_ALREADY_MARKERS):
                return AccountResult(username, CheckInStatus.ALREADY_CHECKED_IN)
            formhash = extract_formhash(html)
            if not formhash:
                raise CheckInError("签到页缺少 formhash")
            url = (
                f"{base}/plugin.php?id=k_misign:sign&operation=qiandao"
                f"&formhash={formhash}&format=empty&inajax=1&ajaxtarget=JD_sign"
            )
            response = session.get(
                url,
                headers=ua_headers(
                    {
                        "Referer": sign_page,
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "*/*",
                    }
                ),
                timeout=timeout,
            )
            response.raise_for_status()
            status, message = classify_discuz_response(response.text)
            if status in {CheckInStatus.SUCCESS, CheckInStatus.ALREADY_CHECKED_IN}:
                return AccountResult(username, status, message)
            if status is CheckInStatus.LOGIN_FAILED:
                return AccountResult(username, status, message)
            last_message = message or "签到接口未确认成功"
        return AccountResult(username, CheckInStatus.CHECK_IN_FAILED, last_message)
