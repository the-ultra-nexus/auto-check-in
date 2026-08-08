"""Sijishe adapter tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auto_check_in.adapters.sijishe import SijisheAdapter
from auto_check_in.discuz import md5_password
from auto_check_in.http import USER_AGENTS, random_user_agent
from auto_check_in.models import Account, CheckInStatus

from helpers import FakeResponse, FakeSession, make_site_config


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


if __name__ == "__main__":
    unittest.main()
