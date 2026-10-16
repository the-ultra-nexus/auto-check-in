"""Sijishe browser adapter tests (scripted driver, no real network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_check_in.adapters.sijishe_browser import SijisheBrowserAdapter, _domain
from auto_check_in.config import NetworkConfig
from auto_check_in.models import Account, CheckInStatus

from helpers import LOGGED_SIGN_PAGE, make_site_config


class FakeElement:
    def __init__(self, driver, kind: str):
        self._driver = driver
        self._kind = kind

    def send_keys(self, text: str) -> None:
        self._driver.typed.append((self._kind, text))

    def clear(self) -> None:
        pass

    def click(self) -> None:
        self._driver.clicks.append(self._kind)
        if self._kind == "submit":
            self._driver.login_lands = True


class FakeForm:
    def __init__(self, driver):
        self._driver = driver

    def find_element(self, by, selector):
        if "username" in selector:
            return FakeElement(self._driver, "username")
        if "password" in selector:
            return FakeElement(self._driver, "password")
        if self._driver.has_submit:
            return FakeElement(self._driver, "submit")
        raise RuntimeError("no such element")


class FakeDriver:
    """Scripted browser: enough surface for the adapter's flow."""

    def __init__(self):
        self.typed: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.visited: list[str] = []
        self.cookies: list[dict] = []
        self.login_lands = False
        self.has_submit = True
        self.title = "登录 - 站点"
        self.sign_page = LOGGED_SIGN_PAGE
        self.plugin_body = "<root><![CDATA[]]></root>"
        self.scripts: list[str] = []

    @property
    def page_source(self) -> str:
        if "k_misign-sign.html" in (self.visited[-1] if self.visited else ""):
            return self.sign_page
        return "<html><form><input name='username'><input name='password'></form></html>"

    def get(self, url: str) -> None:
        self.visited.append(url)
        if "k_misign-sign.html" in url:
            self.title = "每日签到 - 站点"

    def find_element(self, by, selector):
        if selector == '//form[.//input[@name="username"]]':
            return FakeForm(self)
        raise RuntimeError("not found")

    def execute_async_script(self, script: str, *args):
        self.scripts.append(script)
        return self.plugin_body

    def get_cookies(self):
        if self.login_lands and not any(c["name"].endswith("_auth") for c in self.cookies):
            self.cookies.append({"name": "SgL6_2132_auth", "value": "abc"})
        return list(self.cookies)

    def add_cookie(self, cookie: dict) -> None:
        self.cookies.append(cookie)

    def quit(self) -> None:
        pass


class BrowserAdapterTests(unittest.TestCase):
    def _adapter(self, driver: FakeDriver, **overrides) -> SijisheBrowserAdapter:
        return SijisheBrowserAdapter(
            make_site_config(**overrides),
            driver_factory=lambda: driver,
            challenge_timeout_seconds=1,
        )

    def test_full_login_and_sign_in(self):
        driver = FakeDriver()
        result = self._adapter(driver, session_cache=False).run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.SUCCESS)
        self.assertIn(("username", "alice"), driver.typed)
        self.assertIn("submit", driver.clicks)

    def test_already_signed_in(self):
        driver = FakeDriver()
        driver.sign_page = "<html>今日已签</html>"
        result = self._adapter(driver, session_cache=False).run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.ALREADY_CHECKED_IN)

    def test_challenge_page_raises_check_in_error(self):
        driver = FakeDriver()
        driver.title = "Just a moment..."
        adapter = self._adapter(driver, session_cache=False, network=NetworkConfig(retries=1))
        result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.LOGIN_FAILED)

    def test_plugin_response_parsed_for_already_checked_in(self):
        driver = FakeDriver()
        driver.plugin_body = "<root><![CDATA[今日已签]]></root>"
        result = self._adapter(driver, session_cache=False).run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.ALREADY_CHECKED_IN)

    def test_login_failed_response_surfaces(self):
        driver = FakeDriver()
        driver.plugin_body = "<html>Discuz! System Error</html>"
        result = self._adapter(driver, session_cache=False).run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.LOGIN_FAILED)

    def test_session_cache_saves_and_restores(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            first = FakeDriver()
            SijisheBrowserAdapter(
                config, driver_factory=lambda: first, challenge_timeout_seconds=1
            ).run(Account("alice", "pw"))
            self.assertTrue(any(c["name"].endswith("_auth") for c in first.cookies))

            second = FakeDriver()
            second.cookies.append({"name": "SgL6_2132_auth", "value": "saved"})
            second.login_lands = True
            SijisheBrowserAdapter(
                config, driver_factory=lambda: second, challenge_timeout_seconds=1
            ).run(Account("alice", "pw"))
            # 恢复的会话不应再走登录表单
            self.assertEqual(second.typed, [])

    def test_unexpected_error_is_surfaced(self):
        driver = FakeDriver()

        def boom(*args, **kwargs):
            raise RuntimeError("boom detail")

        driver.get = boom
        with mock.patch("auto_check_in.adapters.sijishe_browser.logger"):
            result = self._adapter(driver, session_cache=False).run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.ERROR)
        self.assertIn("boom detail", result.message)

    def test_domain_helper(self):
        self.assertEqual(_domain("https://xsijishe.net/k_misign-sign.html"), "xsijishe.net")
        self.assertEqual(_domain("https://host.example:8443/x"), "host.example")


if __name__ == "__main__":
    unittest.main()
