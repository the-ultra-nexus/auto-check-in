"""Sijishe adapter tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from auto_check_in.adapters.sijishe import SijisheAdapter
from auto_check_in.config import NetworkConfig
from auto_check_in.discuz import md5_password
from auto_check_in.http import USER_AGENTS, random_user_agent
from auto_check_in.models import Account, CheckInStatus

from helpers import ANON_SIGN_PAGE, LOGGED_SIGN_PAGE, FakeResponse, FakeSession, make_site_config


class CustomPathSession(FakeSession):
    """FakeSession that serves pages at a custom sign path."""

    def __init__(self, sign_path: str):
        super().__init__()
        self.sign_path = sign_path

    def _respond(self, url: str) -> FakeResponse:
        if self.sign_path in url:
            self.sign_visits += 1
            return FakeResponse(ANON_SIGN_PAGE if self.sign_visits == 1 else LOGGED_SIGN_PAGE)
        return super()._respond(url)


class AlwaysAnonSession(FakeSession):
    """FakeSession whose login never takes effect (keeps serving the anon page)."""

    def _respond(self, url: str) -> FakeResponse:
        if "member.php?mod=logging&action=login&infloat=yes" in url:
            return FakeResponse(self.dialog)
        if "member.php?mod=logging&action=login&loginsubmit=yes" in url:
            return FakeResponse("")
        if "k_misign-sign.html" in url:
            return FakeResponse(ANON_SIGN_PAGE)
        return FakeResponse("")


class AdapterTests(unittest.TestCase):
    def test_full_login_and_sign_in(self):
        session = FakeSession()
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.SUCCESS)
        login_post = next(item for item in session.requests if item[0] == "POST")
        data = login_post[2]["data"]
        self.assertEqual(data["password"], md5_password("pw"))
        self.assertNotIn("pw", str(data))
        for _, _, kwargs in session.requests:
            self.assertIn("User-Agent", kwargs.get("headers", {}))

    def test_already_signed_in(self):
        session = FakeSession()
        session.plugin_response = FakeResponse("<root><![CDATA[今日已签]]></root>")
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.ALREADY_CHECKED_IN)

    def test_custom_sign_path_used(self):
        session = CustomPathSession("/custom-sign.html")
        adapter = SijisheAdapter(
            make_site_config(session_cache=False, sign_path="/custom-sign.html"),
            session_factory=lambda: session,
        )
        result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.SUCCESS)
        self.assertTrue(any("/custom-sign.html" in url for _, url, _ in session.requests))
        self.assertFalse(any("/k_misign-sign.html" in url for _, url, _ in session.requests))

    def test_retry_delay_applied_between_login_attempts(self):
        session = AlwaysAnonSession()
        adapter = SijisheAdapter(
            make_site_config(
                session_cache=False,
                network=NetworkConfig(retries=3, retry_delay_seconds=2.0),
            ),
            session_factory=lambda: session,
        )
        with mock.patch("auto_check_in.adapters.sijishe.time.sleep") as sleep:
            result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.LOGIN_FAILED)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_any_call(2.0)

    def test_session_invalid(self):
        session = FakeSession()
        session.plugin_response = FakeResponse("<html>Discuz! System Error</html>")
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.LOGIN_FAILED)

    def test_session_cache_skips_login_on_second_run(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            first = FakeSession()
            result = SijisheAdapter(config, session_factory=lambda: first).run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertTrue(any(method == "POST" for method, _, _ in first.requests))

            second = FakeSession()
            result = SijisheAdapter(config, session_factory=lambda: second).run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertFalse(any(method == "POST" for method, _, _ in second.requests))

    def test_invalid_session_triggers_relogin(self):
        with tempfile.TemporaryDirectory() as directory:
            from auto_check_in.session import save_cookies

            save_cookies(Path(directory), "sijishe", "alice", {"SgL6_2132_auth": "stale"})
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            session = FakeSession()
            session.plugin_response = FakeResponse("<html>Discuz! System Error</html>")
            session.fix_after_login = True
            result = SijisheAdapter(config, session_factory=lambda: session).run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertTrue(any(method == "POST" for method, _, _ in session.requests))

    def test_user_agent_pool(self):
        self.assertGreaterEqual(len(set(USER_AGENTS)), 3)
        for _ in range(20):
            self.assertIn(random_user_agent(), USER_AGENTS)

    def test_unexpected_error_is_logged_and_surfaced(self):
        session = FakeSession()

        def boom(*args, **kwargs):
            raise RuntimeError("boom detail")

        session.get = boom
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        with mock.patch("auto_check_in.adapters.sijishe.logger") as logger:
            result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.ERROR)
        self.assertIn("运行过程中发生未预期错误", result.message)
        self.assertIn("boom detail", result.message)
        logger.warning.assert_called_once()
        self.assertIn("boom detail", str(logger.warning.call_args))

    def test_http_error_classified_as_site_unavailable(self):
        session = FakeSession()

        def boom(*args, **kwargs):
            raise requests.HTTPError("403 Client Error: Forbidden for url")

        session.get = boom
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        with mock.patch("auto_check_in.adapters.sijishe.logger") as logger:
            result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.SITE_UNAVAILABLE)
        self.assertIn("站点请求失败", result.message)
        self.assertIn("403", result.message)
        logger.warning.assert_called_once()


    def test_login_post_403_maps_to_login_blocked(self):
        session = FakeSession()
        session.login_post_response = FakeResponse("", status=403)
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        with self.assertLogs("auto_check_in", level="DEBUG") as logs:
            result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.LOGIN_BLOCKED)
        self.assertIn("登录提交被站点拒绝（HTTP 403）", result.message)
        self.assertIn("防机器人", result.message)
        self.assertNotIn("alice", result.message)
        output = "\n".join(logs.output)
        self.assertIn("login step=dialog-fetch", output)
        self.assertIn("login step=login-submit", output)
        self.assertIn(
            "login form fields: formhash=filled username=filled password_md5=filled",
            output,
        )
        self.assertNotIn("pw", output)

    def test_sign_in_http_error_503_stays_site_unavailable(self):
        session = FakeSession()

        def boom(*args, **kwargs):
            raise requests.HTTPError("503 Server Error: Service Unavailable for url")

        session.get = boom
        adapter = SijisheAdapter(
            make_site_config(session_cache=False),
            session_factory=lambda: session,
        )
        with mock.patch("auto_check_in.adapters.sijishe.logger") as logger:
            result = adapter.run(Account("alice", "pw"))
        self.assertEqual(result.status, CheckInStatus.SITE_UNAVAILABLE)
        self.assertIn("站点请求失败", result.message)
        self.assertIn("503", result.message)
        self.assertNotIn("登录提交", result.message)
        logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
