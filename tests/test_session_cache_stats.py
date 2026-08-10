"""Session-cache reuse telemetry tests: counters and redacted logs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auto_check_in.adapters.sijishe import SijisheAdapter
from auto_check_in.models import Account, AccountResult, CheckInStatus, RunSummary
from auto_check_in.session import SessionCacheStats, save_cookies

from helpers import FakeResponse, FakeSession, make_site_config


class SessionCacheStatsTest(unittest.TestCase):
    def test_restore_hit_and_persist_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            save_cookies(Path(directory), "sijishe", "alice", {"SgL6_2132_auth": "abc"})
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            session = FakeSession()
            adapter = SijisheAdapter(config, session_factory=lambda: session)
            with self.assertLogs("auto_check_in", level="INFO") as logs:
                result = adapter.run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertEqual(adapter.session_cache_stats.restored, 1)
            self.assertEqual(adapter.session_cache_stats.rejected, 0)
            self.assertEqual(adapter.session_cache_stats.saved, 1)
            output = "\n".join(logs.output)
            self.assertIn(
                "session-cache site=sijishe account=al***e event=restored cookies=1",
                output,
            )
            self.assertIn("event=saved", output)
            self.assertNotIn("abc", output)

    def test_restore_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            session = FakeSession()
            adapter = SijisheAdapter(config, session_factory=lambda: session)
            with self.assertLogs("auto_check_in", level="INFO") as logs:
                result = adapter.run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertEqual(adapter.session_cache_stats.restored, 0)
            self.assertEqual(adapter.session_cache_stats.saved, 1)
            self.assertIn("event=restore-miss", "\n".join(logs.output))

    def test_restored_session_rejected_triggers_relogin(self):
        with tempfile.TemporaryDirectory() as directory:
            save_cookies(Path(directory), "sijishe", "alice", {"SgL6_2132_auth": "stale"})
            config = make_site_config(session_cache=True, session_dir=Path(directory))
            session = FakeSession()
            session.plugin_response = FakeResponse("<html>Discuz! System Error</html>")
            session.fix_after_login = True
            adapter = SijisheAdapter(config, session_factory=lambda: session)
            with self.assertLogs("auto_check_in", level="INFO") as logs:
                result = adapter.run(Account("alice", "pw"))
            self.assertEqual(result.status, CheckInStatus.SUCCESS)
            self.assertTrue(any(method == "POST" for method, _, _ in session.requests))
            stats = adapter.session_cache_stats
            self.assertEqual(stats.restored, 1)
            self.assertEqual(stats.rejected, 1)
            self.assertEqual(stats.saved, 1)
            self.assertIn("event=rejected", "\n".join(logs.output))

    def test_persist_skips_without_auth_cookie(self):
        adapter = SijisheAdapter(make_site_config(session_cache=True))
        session = FakeSession()
        with self.assertLogs("auto_check_in", level="INFO") as logs:
            adapter._persist_session(session, "alice")
        self.assertEqual(adapter.session_cache_stats.saved, 0)
        self.assertIn(
            "event=persist-skipped reason=no-auth-cookie",
            "\n".join(logs.output),
        )

    def test_persist_skips_when_disabled(self):
        adapter = SijisheAdapter(make_site_config(session_cache=False))
        session = FakeSession()
        with self.assertLogs("auto_check_in", level="INFO") as logs:
            adapter._persist_session(session, "alice")
        self.assertEqual(adapter.session_cache_stats.saved, 0)
        self.assertIn(
            "event=persist-skipped reason=disabled",
            "\n".join(logs.output),
        )

    def test_run_summary_renders_counter_line_when_present(self):
        summary = RunSummary(
            [AccountResult("alice", CheckInStatus.SUCCESS)],
            sessions_restored=1,
            sessions_rejected=1,
            sessions_saved=1,
        )
        self.assertIn("会话缓存: 恢复 1 / 被拒重登 1 / 新保存 1", summary.render())

    def test_run_summary_omits_counter_line_when_all_zero(self):
        self.assertNotIn("会话缓存", RunSummary([]).render())

    def test_stats_bump_and_merge(self):
        stats = SessionCacheStats().bump(restored=1).bump(saved=1)
        merged = SessionCacheStats.merge(stats, SessionCacheStats().bump(rejected=2))
        self.assertEqual(merged.restored, 1)
        self.assertEqual(merged.rejected, 2)
        self.assertEqual(merged.saved, 1)


if __name__ == "__main__":
    unittest.main()
