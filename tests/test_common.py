"""Shared tests: configuration, Discuz helpers, runner, redaction, session cache."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_check_in.config import (
    CheckInConfig,
    ConfigError,
    NetworkConfig,
    SiteConfig,
    load_config,
    parse_accounts,
)
from auto_check_in.discuz import (
    classify_discuz_response,
    extract_formhash,
    parse_login_dialog,
)
from auto_check_in.http import USER_AGENTS, SessionProvider, ua_headers
from auto_check_in.models import AccountResult, CheckInStatus, RunSummary
from auto_check_in.runner import run
from auto_check_in.security import redact_text
from auto_check_in.session import load_cookies, save_cookies, session_path

from helpers import ANON_SIGN_PAGE, DIALOG, write_config


class ConfigTests(unittest.TestCase):
    def test_parse_accounts_supports_at_and_newline(self):
        accounts = parse_accounts("alice&one@bob&two\ncarol&three&with-ampersand")
        self.assertEqual([a.username for a in accounts], ["alice", "bob", "carol"])
        self.assertEqual(accounts[-1].password, "three&with-ampersand")

    def test_parse_accounts_rejects_malformed_secret(self):
        with self.assertRaises(ConfigError):
            parse_accounts("alice-without-password")

    def test_per_site_environment_isolation(self):
        path = write_config("[runtime]\nenabled_sites = []\nmax_workers = 2\n")
        config = load_config(
            path,
            {
                "CHECK_IN_SITES": "sijishe,site2",
                "SITE_SIJISHE_BASE_URL": "https://a.example",
                "SITE_SIJISHE_ACCOUNTS": "u1&p1",
                "SITE_SITE2_BASE_URL": "https://b.example/",
                "SITE_SITE2_ACCOUNTS": "u2&p2",
            },
        )
        self.assertEqual([site.name for site in config.sites], ["sijishe", "site2"])
        self.assertEqual(config.sites[0].base_url, "https://a.example")
        self.assertEqual(config.sites[1].base_url, "https://b.example")
        self.assertEqual(config.sites[1].accounts, "u2&p2")
        self.assertEqual(config.max_workers, 2)

    def test_missing_base_url_rejected(self):
        path = write_config("")
        with self.assertRaises(ConfigError):
            load_config(path, {"CHECK_IN_SITES": "sijishe", "SITE_SIJISHE_ACCOUNTS": "u&p"})

    def test_missing_credentials_rejected(self):
        path = write_config("")
        with self.assertRaises(ConfigError):
            load_config(path, {"CHECK_IN_SITES": "sijishe", "SITE_SIJISHE_BASE_URL": "https://a.example"})

    def test_max_workers_env_override(self):
        path = write_config("[runtime]\nmax_workers = 2\n")
        config = load_config(
            path,
            {
                "CHECK_IN_MAX_WORKERS": "6",
                "CHECK_IN_SITES": "sijishe",
                "SITE_SIJISHE_BASE_URL": "https://a.example",
                "SITE_SIJISHE_ACCOUNTS": "u&p",
            },
        )
        self.assertEqual(config.max_workers, 6)

    def test_session_cache_env(self):
        path = write_config("")
        config = load_config(
            path,
            {
                "CHECK_IN_SITES": "sijishe",
                "SITE_SIJISHE_BASE_URL": "https://a.example",
                "SITE_SIJISHE_ACCOUNTS": "u&p",
                "CHECK_IN_SESSION_CACHE": "false",
                "CHECK_IN_SESSION_DIR": "/tmp/sessions",
            },
        )
        self.assertFalse(config.sites[0].session_cache)
        self.assertEqual(config.sites[0].session_dir, Path("/tmp/sessions"))

    def test_site_configs_json(self):
        path = write_config("[runtime]\nenabled_sites = ['sijishe']\n")
        config = load_config(
            path,
            {
                "SITE_CONFIGS": json.dumps(
                    {
                        "sijishe": {"base_url": "https://a.example", "accounts": "u1&p1"},
                        "site2": {"base_url": "https://b.example", "accounts": "u2&p2", "adapter": "custom"},
                    }
                )
            },
        )
        self.assertEqual([site.name for site in config.sites], ["sijishe", "site2"])
        self.assertEqual(config.sites[0].base_url, "https://a.example")
        self.assertEqual(config.sites[1].adapter, "custom")

    def test_site_configs_invalid_json(self):
        path = write_config("")
        with self.assertRaises(ConfigError):
            load_config(path, {"SITE_CONFIGS": "{bad json"})

    def test_per_site_env_overrides_site_configs(self):
        path = write_config("")
        config = load_config(
            path,
            {
                "CHECK_IN_SITES": "sijishe",
                "SITE_CONFIGS": json.dumps(
                    {"sijishe": {"base_url": "https://json.example", "accounts": "u&p"}}
                ),
                "SITE_SIJISHE_BASE_URL": "https://env.example",
            },
        )
        self.assertEqual(config.sites[0].base_url, "https://env.example")

    def test_request_delay_default_and_env(self):
        path = write_config("[network]\nrequest_delay_seconds = 3.0\n")
        base = {
            "CHECK_IN_SITES": "sijishe",
            "SITE_SIJISHE_BASE_URL": "https://a.example",
            "SITE_SIJISHE_ACCOUNTS": "u&p",
        }
        self.assertEqual(load_config(path, base).sites[0].network.request_delay_seconds, 3.0)
        self.assertEqual(
            load_config(path, {**base, "CHECK_IN_REQUEST_DELAY": "5"}).sites[0].network.request_delay_seconds,
            5.0,
        )

    def test_request_delay_negative_rejected(self):
        path = write_config("")
        with self.assertRaises(ConfigError):
            load_config(
                path,
                {
                    "CHECK_IN_SITES": "sijishe",
                    "SITE_SIJISHE_BASE_URL": "https://a.example",
                    "SITE_SIJISHE_ACCOUNTS": "u&p",
                    "CHECK_IN_REQUEST_DELAY": "-1",
                },
            )

    def test_multiple_site_errors_aggregated(self):
        path = write_config("")
        with self.assertRaises(ConfigError) as ctx:
            load_config(
                path,
                {
                    "CHECK_IN_SITES": "sijishe,site2",
                    "SITE_SIJISHE_ACCOUNTS": "u&p",
                    "SITE_SITE2_ACCOUNTS": "u&p",
                },
            )
        message = str(ctx.exception)
        self.assertIn("sijishe", message)
        self.assertIn("site2", message)

    def test_unknown_key_warns(self):
        path = write_config("[runtime]\nbogus_key = 1\n")
        with mock.patch("auto_check_in.config.logger.warning") as warning:
            load_config(
                path,
                {
                    "CHECK_IN_SITES": "sijishe",
                    "SITE_SIJISHE_BASE_URL": "https://a.example",
                    "SITE_SIJISHE_ACCOUNTS": "u&p",
                },
            )
        self.assertTrue(any("bogus_key" in str(call) for call in warning.call_args_list))

    def test_session_max_age_env(self):
        path = write_config("")
        config = load_config(
            path,
            {
                "CHECK_IN_SITES": "sijishe",
                "SITE_SIJISHE_BASE_URL": "https://a.example",
                "SITE_SIJISHE_ACCOUNTS": "u&p",
                "CHECK_IN_SESSION_MAX_AGE": "3600",
            },
        )
        self.assertEqual(config.sites[0].session_max_age_seconds, 3600.0)


class DiscuzParsingTests(unittest.TestCase):
    def test_parse_login_dialog(self):
        form = parse_login_dialog(DIALOG)
        self.assertEqual(form["formhash"], "abc123")
        self.assertEqual(form["loginhash"], "Ab12")
        self.assertTrue(form["referer"].startswith("https://xsijishe.net"))

    def test_parse_login_dialog_rejects_without_form(self):
        with self.assertRaises(Exception):
            parse_login_dialog("<root><![CDATA[<html></html>]]></root>")

    def test_extract_formhash(self):
        self.assertEqual(extract_formhash(ANON_SIGN_PAGE), "pagehash1")

    def test_classify_already_signed(self):
        status, _ = classify_discuz_response("<root><![CDATA[今日已签]]></root>")
        self.assertIs(status, CheckInStatus.ALREADY_CHECKED_IN)

    def test_classify_success_empty_cdata(self):
        status, _ = classify_discuz_response("<root><![CDATA[]]></root>")
        self.assertIs(status, CheckInStatus.SUCCESS)

    def test_classify_system_error(self):
        status, _ = classify_discuz_response(
            "<html><title>xsijishe.net - System Error</title>Discuz! System Error</html>"
        )
        self.assertIs(status, CheckInStatus.LOGIN_FAILED)

    def test_classify_unknown(self):
        status, message = classify_discuz_response("<root><![CDATA[签到失败]]></root>")
        self.assertIs(status, CheckInStatus.CHECK_IN_FAILED)
        self.assertTrue(message)

    def test_classify_malformed(self):
        status, _ = classify_discuz_response("not-xml")
        self.assertIs(status, CheckInStatus.CHECK_IN_FAILED)


class SessionProviderTests(unittest.TestCase):
    def test_provider_session_has_ua_and_network_defaults(self):
        provider = SessionProvider(NetworkConfig())
        session = provider.new_session()
        try:
            self.assertIn("User-Agent", session.headers)
            self.assertIn(session.headers["User-Agent"], USER_AGENTS)
            self.assertEqual(provider.network.request_timeout_seconds, 15)
            self.assertEqual(provider.network.request_delay_seconds, 3.0)
        finally:
            session.close()

    def test_ua_headers_uses_pool(self):
        headers = ua_headers({"Referer": "https://example.test"})
        self.assertIn(headers["User-Agent"], USER_AGENTS)
        self.assertEqual(headers["Referer"], "https://example.test")


class RunnerTests(unittest.TestCase):
    def test_parallel_sites_with_failure_isolation(self):
        class GoodAdapter:
            def __init__(self, config):
                self.config = config

            def run(self, account):
                return AccountResult(account.username, CheckInStatus.SUCCESS)

        class BadAdapter:
            def __init__(self, config):
                self.config = config

            def run(self, account):
                return AccountResult(account.username, CheckInStatus.LOGIN_FAILED, "失败")

        config = CheckInConfig(
            sites=(
                SiteConfig("good", "good", "https://a.example", "u&p"),
                SiteConfig("bad", "bad", "https://b.example", "u&p"),
            ),
            max_workers=2,
        )
        summary = run(config, adapter_types={"good": GoodAdapter, "bad": BadAdapter})
        self.assertEqual(len(summary.results), 2)
        self.assertEqual(summary.exit_code, 1)
        self.assertEqual([r.status for r in summary.results].count(CheckInStatus.SUCCESS), 1)

    def test_unknown_adapter_is_config_error(self):
        config = CheckInConfig(
            sites=(SiteConfig("x", "missing", "https://a.example", "u&p"),),
            max_workers=1,
        )
        with self.assertRaises(ConfigError):
            run(config, adapter_types={})

    def test_request_delay_applied_between_accounts(self):
        class StubAdapter:
            def __init__(self, config):
                self.config = config

            def run(self, account):
                return AccountResult(account.username, CheckInStatus.SUCCESS)

        config = CheckInConfig(
            sites=(
                SiteConfig(
                    "s",
                    "stub",
                    "https://a.example",
                    "u1&p1@u2&p2",
                    network=NetworkConfig(request_delay_seconds=2),
                ),
            ),
            max_workers=1,
        )
        with mock.patch("auto_check_in.runner.time.sleep") as sleep, mock.patch(
            "auto_check_in.runner.random.uniform", return_value=0.0
        ):
            summary = run(config, adapter_types={"stub": StubAdapter})
        self.assertEqual(len(summary.results), 2)
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args[0][0], 2.0)

    def test_request_delay_zero_skips_wait(self):
        class StubAdapter:
            def __init__(self, config):
                self.config = config

            def run(self, account):
                return AccountResult(account.username, CheckInStatus.SUCCESS)

        config = CheckInConfig(
            sites=(
                SiteConfig(
                    "s",
                    "stub",
                    "https://a.example",
                    "u1&p1@u2&p2",
                    network=NetworkConfig(request_delay_seconds=0),
                ),
            ),
            max_workers=1,
        )
        with mock.patch("auto_check_in.runner.time.sleep") as sleep:
            run(config, adapter_types={"stub": StubAdapter})
        sleep.assert_not_called()


class RedactionTests(unittest.TestCase):
    def test_redact_cookie_and_hex(self):
        text = "SgL6_2132_auth=secret123; cf_clearance=token abc123456789012345678901234567890"
        redacted = redact_text(text)
        self.assertNotIn("secret123", redacted)
        self.assertNotIn("token", redacted)
        self.assertIn("***", redacted)

    def test_summary_excludes_credentials(self):
        summary = RunSummary([AccountResult("alice", CheckInStatus.LOGIN_FAILED, "SgL6_2132_auth=secret 失败")])
        self.assertNotIn("secret", summary.render())

    def test_status_labels_are_readable(self):
        self.assertEqual(CheckInStatus.SUCCESS.label, "签到成功")
        self.assertEqual(CheckInStatus.LOGIN_FAILED.label, "登录失败")
        summary = RunSummary([AccountResult("alice", CheckInStatus.SUCCESS)])
        self.assertIn("签到成功", summary.render())

    def test_title_head_all_success(self):
        summary = RunSummary(
            [
                AccountResult("alice", CheckInStatus.SUCCESS),
                AccountResult("bob", CheckInStatus.ALREADY_CHECKED_IN),
            ]
        )
        self.assertEqual(summary.title_head(), "2/2 成功")

    def test_title_head_partial_failure(self):
        summary = RunSummary(
            [
                AccountResult("alice", CheckInStatus.SUCCESS),
                AccountResult("bob", CheckInStatus.LOGIN_FAILED),
            ]
        )
        self.assertEqual(summary.title_head(), "1/2 失败")

    def test_title_head_empty(self):
        self.assertEqual(RunSummary().title_head(), "无账号")

    def test_render_groups_by_site(self):
        summary = RunSummary(
            [
                AccountResult("a", CheckInStatus.SUCCESS, site="sijishe"),
                AccountResult("b", CheckInStatus.LOGIN_FAILED, site="sijishe"),
                AccountResult("c", CheckInStatus.SUCCESS, site="site2"),
            ]
        )
        text = summary.render()
        self.assertIn("【sijishe】", text)
        self.assertIn("【site2】", text)


class SessionCacheTests(unittest.TestCase):
    def test_roundtrip_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            session_dir = Path(directory)
            save_cookies(session_dir, "sijishe", "alice", {"SgL6_2132_auth": "abc"})
            self.assertEqual(load_cookies(session_dir, "sijishe", "alice"), {"SgL6_2132_auth": "abc"})
            self.assertEqual(load_cookies(session_dir, "sijishe", "bob"), {})

    def test_expired_cache_returns_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            session_dir = Path(directory)
            path = session_path(session_dir, "sijishe", "alice")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"saved_at": 1.0, "cookies": {"SgL6_2132_auth": "abc"}}),
                encoding="utf-8",
            )
            self.assertEqual(load_cookies(session_dir, "sijishe", "alice", max_age_seconds=60), {})
            self.assertEqual(load_cookies(session_dir, "sijishe", "alice"), {"SgL6_2132_auth": "abc"})


class DependencyTests(unittest.TestCase):
    def test_no_obsolete_dependencies(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        for name in ("selenium", "ddddocr", "opencv", "onnxruntime"):
            self.assertNotIn(name, text)


if __name__ == "__main__":
    unittest.main()
