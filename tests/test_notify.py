"""Notification channel tests."""

from __future__ import annotations

import os
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


if __name__ == "__main__":
    unittest.main()
