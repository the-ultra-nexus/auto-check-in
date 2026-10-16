"""Sijishe browser adapter tests (scripted driver, no real network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_check_in.adapters.sijishe_browser import SijisheBrowserAdapter, _domain
from auto_check_in.config import NetworkConfig
from auto_check_in.models import Account, CheckInStatus

from helpers import FakeDriver, make_site_config


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

    def test_stale_cached_session_triggers_relogin(self):
        """缓存里的 *_auth 仍在，但服务端会话已失效 → 应清 cookie 重登。"""
        with tempfile.TemporaryDirectory() as directory:
            from auto_check_in.session import save_cookies

            save_cookies(Path(directory), "sijishe", "alice", {"SgL6_2132_auth": "stale"})
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            driver = FakeDriver()
            # 恢复的会话看起来有效，但签到接口返回未登录响应
            driver.cookies.append({"name": "SgL6_2132_auth", "value": "stale"})
            driver.plugin_body = (
                "<root><![CDATA[您所在用户组不允许使用]]></root>"
            )
            driver.fix_after_login = True

            adapter = SijisheBrowserAdapter(
                config, driver_factory=lambda: driver, challenge_timeout_seconds=1
            )
            result = adapter.run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertTrue(driver.clicks, "应重新提交登录表单")
            stats = adapter.session_cache_stats
            self.assertEqual(stats.rejected, 1)

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
