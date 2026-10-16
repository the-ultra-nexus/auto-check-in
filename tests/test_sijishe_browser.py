"""Sijishe browser adapter tests (scripted driver, no real network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_check_in.adapters.sijishe_browser import (
    MAX_NODE_SWITCHES,
    SijisheBrowserAdapter,
    _domain,
)
from auto_check_in.config import NetworkConfig
from auto_check_in.models import Account, CheckInStatus

from helpers import FakeDriver, make_site_config


class BrowserAdapterTests(unittest.TestCase):
    def _adapter(
        self, driver: FakeDriver, switcher=None, **overrides
    ) -> SijisheBrowserAdapter:
        """switcher 默认返回 None（没有别的节点可换），可传入序列模拟换节点。"""
        return SijisheBrowserAdapter(
            make_site_config(**overrides),
            driver_factory=lambda: driver,
            challenge_timeout_seconds=1,
            node_switcher=switcher or (lambda exclude: None),
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

    def test_challenge_page_switches_node_then_errors(self):
        """被 CF 拦下且没有别的节点可换 → ERROR（而非静默失败）。"""
        driver = FakeDriver()
        driver.title = "Just a moment..."
        adapter = self._adapter(driver, session_cache=False, network=NetworkConfig(retries=1))
        result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.ERROR)
        self.assertIn("Cloudflare", result.message)

    def test_blocked_node_is_switched_and_then_succeeds(self):
        """第一次被拦 → 换节点 → 第二次成功。"""
        blocked = FakeDriver()
        blocked.title = "Just a moment..."
        good = FakeDriver()
        drivers = iter([blocked, good])
        switches: list[set] = []

        def switcher(exclude: set) -> str:
            switches.append(set(exclude))
            return "node-2"

        adapter = SijisheBrowserAdapter(
            make_site_config(session_cache=False),
            driver_factory=lambda: next(drivers),
            challenge_timeout_seconds=1,
            node_switcher=switcher,
        )
        result = adapter.run(Account("alice", "pw"))

        self.assertEqual(result.status, CheckInStatus.SUCCESS)
        self.assertEqual(len(switches), 1, "被拦一次应换一次节点")
        self.assertIn("node-2", adapter._current_node)

    def test_gives_up_after_max_switches(self):
        """一直换节点也过不去 → 停止，不无限重试。"""
        calls: list[int] = []

        def switcher(exclude: set) -> str:
            calls.append(1)
            return f"node-{len(calls)}"

        def factory():
            d = FakeDriver()
            d.title = "Just a moment..."
            return d

        adapter = SijisheBrowserAdapter(
            make_site_config(session_cache=False, network=NetworkConfig(retries=1)),
            driver_factory=factory,
            challenge_timeout_seconds=1,
            node_switcher=switcher,
        )
        result = adapter.run(Account("alice", "pw"))

        self.assertEqual(result.status, CheckInStatus.ERROR)
        self.assertEqual(len(calls), MAX_NODE_SWITCHES, "换节点次数应封顶")

    def test_switcher_receives_tried_nodes(self):
        """换节点时必须把已试过的节点传出去，否则会换回同一个。"""
        seen: list[set] = []

        def switcher(exclude: set) -> str | None:
            seen.append(set(exclude))
            return "next" if len(seen) < 2 else None

        def factory():
            d = FakeDriver()
            d.title = "Just a moment..."
            return d

        adapter = SijisheBrowserAdapter(
            make_site_config(session_cache=False, network=NetworkConfig(retries=1)),
            driver_factory=factory,
            challenge_timeout_seconds=1,
            node_switcher=switcher,
        )
        adapter.run(Account("alice", "pw"))
        # 第二次调用时，第一次选中的节点应已在排除集里
        self.assertIn("next", seen[1])

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
