"""Notification channel tests."""

from __future__ import annotations

import os
import smtplib
import unittest
from unittest import mock

import requests

from auto_check_in.notify import send

NO_CHANNELS = {
    "BARK_PUSH": "",
    "PUSH_KEY": "",
    "TG_BOT_TOKEN": "",
    "TG_USER_ID": "",
    "DD_BOT_TOKEN": "",
    "DD_BOT_SECRET": "",
    "FSKEY": "",
    "QYWX_KEY": "",
    "PUSH_PLUS_TOKEN": "",
    "DEER_KEY": "",
    "WEBHOOK_URL": "",
    "WEBHOOK_METHOD": "",
    "NTFY_TOPIC": "",
    "SMTP_SERVER": "",
    "SMTP_EMAIL": "",
    "SMTP_PASSWORD": "",
    "SMTP_NAME": "",
    "CONSOLE": "",
    "SKIP_PUSH_TITLE": "",
}


class NotifyTests(unittest.TestCase):
    def test_no_channels_no_requests(self):
        with mock.patch.dict(os.environ, NO_CHANNELS, clear=False), mock.patch(
            "auto_check_in.notify.requests.post", side_effect=AssertionError("不应发送请求")
        ) as post, mock.patch(
            "auto_check_in.notify.requests.get", side_effect=AssertionError("不应发送请求")
        ):
            send("签到 1/1 成功", "账户[alice] 签到成功")
        post.assert_not_called()

    def test_channel_timeout_is_contained(self):
        env = {**NO_CHANNELS, "BARK_PUSH": "https://bark.example/push"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.notify.requests.post", side_effect=requests.Timeout("timeout")
        ):
            send("t", "c")

    def test_multiple_channels_selected(self):
        env = {**NO_CHANNELS, "BARK_PUSH": "https://bark.example/push", "PUSH_KEY": "key123"}
        seen: list[str] = []

        def fake_post(url, **kwargs):
            seen.append(url)
            return mock.Mock(status_code=200)

        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.notify.requests.post", side_effect=fake_post
        ):
            send("t", "c")
        self.assertEqual(len(seen), 2)

    def test_skip_push_title(self):
        env = {**NO_CHANNELS, "PUSH_KEY": "key123", "SKIP_PUSH_TITLE": "签到 1/1 成功"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.notify.requests.post", side_effect=AssertionError("不应发送请求")
        ) as post:
            send("签到 1/1 成功", "c")
        post.assert_not_called()

    def test_user_agent_from_shared_pool(self):
        from auto_check_in.http import USER_AGENTS

        env = {**NO_CHANNELS, "BARK_PUSH": "https://bark.example/push"}
        seen: list[str] = []

        def fake_post(url, **kwargs):
            seen.append(kwargs["headers"]["User-Agent"])
            return mock.Mock(status_code=200)

        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.notify.requests.post", side_effect=fake_post
        ):
            send("t", "c")
        self.assertTrue(seen)
        self.assertIn(seen[0], USER_AGENTS)

    def test_cli_notify_failure_keeps_exit_code(self):
        from auto_check_in.cli import main
        from auto_check_in.models import AccountResult, CheckInStatus, RunSummary

        env = {
            "CHECK_IN_SITES": "sijishe",
            "SITE_SIJISHE_BASE_URL": "https://a.example",
            "SITE_SIJISHE_ACCOUNTS": "u&p",
        }
        summary = RunSummary([AccountResult("u", CheckInStatus.LOGIN_FAILED)])
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.cli.run", return_value=summary
        ), mock.patch(
            "auto_check_in.notify.send", side_effect=RuntimeError("boom")
        ):
            code = main([])
        self.assertEqual(code, 1)



class FakeSMTP:
    """Scriptable smtplib client used by SMTP channel tests."""

    def __init__(self, host, port=0, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = ["connect"]
        self.capabilities = {"starttls"}
        self.fail_auth = False
        self.disconnect_on_login = False

    def ehlo(self):
        self.calls.append("ehlo")
        return (250, b"ok")

    def has_extn(self, name):
        return name.lower() in {item.lower() for item in self.capabilities}

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, email, password):
        self.calls.append(("login", email))
        if self.disconnect_on_login:
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        if self.fail_auth:
            raise smtplib.SMTPAuthenticationError(535, b"auth failed")

    def sendmail(self, from_addr, to_addrs, msg):
        self.calls.append(("sendmail", from_addr, to_addrs))

    def quit(self):
        self.calls.append("quit")

    def close(self):
        self.calls.append("close")


SMTP_ENV = {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_EMAIL": "me@example.com",
    "SMTP_PASSWORD": "secret",
    "SMTP_NAME": "Auto Check In",
}


class SmtpTests(unittest.TestCase):
    def _patch_smtp(self, configure=None):
        created: list[tuple[str, FakeSMTP]] = []

        def factory(which):
            def make(host, port=0, timeout=None):
                instance = FakeSMTP(host, port, timeout)
                if configure is not None:
                    configure(which, instance)
                created.append((which, instance))
                return instance

            return make

        patchers = [
            mock.patch("auto_check_in.notify.smtplib.SMTP", factory("SMTP")),
            mock.patch("auto_check_in.notify.smtplib.SMTP_SSL", factory("SMTP_SSL")),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        return created

    def _run(self, **env):
        from auto_check_in.notify import smtp

        with mock.patch.dict(os.environ, {**NO_CHANNELS, **SMTP_ENV, **env}, clear=False):
            smtp("签到 1/1 成功", "账户[alice] 签到成功")

    def _sent(self, client) -> bool:
        return any(call[0] == "sendmail" for call in client.calls if isinstance(call, tuple))

    def test_ssl_mode_uses_implicit_tls_on_465(self):
        created = self._patch_smtp()
        self._run(SMTP_SSL="true")
        self.assertEqual(len(created), 1)
        which, client = created[0]
        self.assertEqual(which, "SMTP_SSL")
        self.assertEqual(client.port, 465)
        self.assertTrue(self._sent(client))

    def test_ssl_flag_accepts_truthy_variants(self):
        for value in ("1", "yes", "on", "TRUE"):
            with self.subTest(value=value):
                created = self._patch_smtp()
                self._run(SMTP_SSL=value)
                self.assertEqual(created[0][0], "SMTP_SSL", value)

    def test_ssl_mode_respects_smtp_port(self):
        created = self._patch_smtp()
        self._run(SMTP_SSL="true", SMTP_PORT="587")
        which, client = created[0]
        self.assertEqual(which, "SMTP_SSL")
        self.assertEqual(client.port, 587)

    def test_starttls_mode_uses_smtp_with_starttls_on_587(self):
        created = self._patch_smtp()
        self._run(SMTP_STARTTLS="true")
        self.assertEqual(len(created), 1)
        which, client = created[0]
        self.assertEqual(which, "SMTP")
        self.assertEqual(client.port, 587)
        self.assertIn("starttls", client.calls)
        self.assertTrue(self._sent(client))

    def test_auto_mode_with_465_server_falls_back_from_ssl_to_starttls(self):
        created = self._patch_smtp(
            configure=lambda which, client: setattr(client, "disconnect_on_login", which == "SMTP_SSL")
        )
        self._run(SMTP_SERVER="smtp.example.com:465")
        self.assertGreaterEqual(len(created), 2)
        self.assertEqual(created[0][0], "SMTP_SSL")
        self.assertEqual(created[0][1].port, 465)
        self.assertEqual(created[1][0], "SMTP")
        self.assertIn("starttls", created[1][1].calls)
        self.assertTrue(self._sent(created[1][1]))

    def test_auto_mode_without_port_tries_starttls_587_first(self):
        created = self._patch_smtp()
        self._run()
        self.assertGreaterEqual(len(created), 1)
        which, client = created[0]
        self.assertEqual(which, "SMTP")
        self.assertEqual(client.port, 587)
        self.assertIn("starttls", client.calls)

    def test_auth_error_does_not_fall_back(self):
        created = self._patch_smtp(
            configure=lambda which, client: setattr(client, "fail_auth", True)
        )
        from auto_check_in.notify import smtp

        with mock.patch.dict(os.environ, {**NO_CHANNELS, **SMTP_ENV}, clear=False):
            with self.assertRaises(smtplib.SMTPAuthenticationError):
                smtp("t", "c")
        self.assertEqual(len(created), 1)

    def test_invalid_smtp_port_raises_value_error(self):
        from auto_check_in.notify import smtp

        with mock.patch.dict(os.environ, {**NO_CHANNELS, **SMTP_ENV, "SMTP_PORT": "abc"}, clear=False):
            with self.assertRaises(ValueError):
                smtp("t", "c")

    def test_parse_smtp_server(self):
        from auto_check_in.notify import _parse_smtp_server

        self.assertEqual(_parse_smtp_server("smtp.qq.com"), ("smtp.qq.com", None))
        self.assertEqual(_parse_smtp_server("smtp.qq.com:465"), ("smtp.qq.com", 465))
        self.assertEqual(_parse_smtp_server("[::1]:587"), ("::1", 587))
        with self.assertRaises(ValueError):
            _parse_smtp_server("smtp.qq.com:notaport")


class NotifyOnlyCliTests(unittest.TestCase):
    def test_notify_only_without_site_credentials(self):
        from auto_check_in.cli import main

        env = {**NO_CHANNELS, "CONSOLE": "1"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.notify.send"
        ) as send:
            code = main(["--notify-only"])
        self.assertEqual(code, 0)
        send.assert_called_once()
        title, content = send.call_args.args
        self.assertIn("测试", title)
        self.assertIn("console", content)

    def test_notify_only_no_channels_exits_2(self):
        from auto_check_in.cli import main

        with mock.patch.dict(os.environ, NO_CHANNELS, clear=False), mock.patch(
            "auto_check_in.notify.send"
        ) as send:
            code = main(["--notify-only"])
        self.assertEqual(code, 2)
        send.assert_not_called()

    def test_notify_only_notify_disabled_exits_2(self):
        from auto_check_in.cli import main

        env = {**NO_CHANNELS, "CONSOLE": "1", "CHECK_IN_NOTIFY": "false"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "auto_check_in.notify.send"
        ) as send:
            code = main(["--notify-only"])
        self.assertEqual(code, 2)
        send.assert_not_called()

    def test_notify_only_mutually_exclusive(self):
        from auto_check_in.cli import build_parser

        for extra in ("--dry-run", "--no-notify"):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["--notify-only", extra])

    def test_active_channels_reports_enabled(self):
        from auto_check_in.notify import active_channels

        env = {**NO_CHANNELS, "BARK_PUSH": "https://bark.example/push", "CONSOLE": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            active = active_channels()
        self.assertIn("bark", active)
        self.assertIn("console", active)
        self.assertNotIn("telegram", active)

    def test_load_notify_settings_uses_toml_title(self):
        from auto_check_in.config import load_notify_settings
        from helpers import write_config

        path = write_config("[notification]\ntitle = \"本地通知\"\nenabled = true\n")
        title, enabled = load_notify_settings(path, {})
        self.assertEqual(title, "本地通知")
        self.assertTrue(enabled)


if __name__ == "__main__":
    unittest.main()
