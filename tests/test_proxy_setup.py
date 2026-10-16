"""proxy_setup 测试：订阅源回退链 + 并行选节点。不起真实 mihomo，不打网络。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auto_check_in import proxy_setup
from auto_check_in.proxy_setup import ProxySetupError, _subscriptions, setup

GOOD = proxy_setup.DEFAULT_SUBSCRIPTIONS[0]
TWO_NODE_YAML = (
    "proxies:\n"
    "  - {name: n1, type: socks5, server: 127.0.0.1, port: 1080}\n"
    "  - {name: n2, type: socks5, server: 127.0.0.1, port: 1081}\n"
)


def _run(subscription: str, work: Path, fetch, group_pick, delays=None) -> tuple[int, str]:
    """跑 setup，返回 (退出码, mihomo 最终选中的节点)。"""

    def fetch_writing(url: str, dest: Path) -> None:
        dest.write_text(TWO_NODE_YAML, encoding="utf-8")

    with mock.patch.object(proxy_setup, "_core_binary", return_value=Path("/bin/true")), \
         mock.patch.object(proxy_setup, "_fetch_subscription", side_effect=fetch or fetch_writing), \
         mock.patch.object(proxy_setup, "_wait_for_group", side_effect=group_pick), \
         mock.patch.object(proxy_setup, "_group_delays", return_value=delays or {}), \
         mock.patch.object(proxy_setup.subprocess, "Popen") as popen, \
         mock.patch.object(proxy_setup.time, "sleep"):
        popen.return_value.poll.return_value = None  # None = 进程还活着
        code = setup(subscription, work, 7890, 9090)
    return code, (group_pick.return_value if hasattr(group_pick, "return_value") else "")


class SubscriptionsTests(unittest.TestCase):
    def test_defaults_are_distinct_raw_https(self):
        urls = _subscriptions("")
        self.assertEqual(len(urls), 3)
        self.assertEqual(len(set(urls)), 3, "内置源不应重复")
        for url in urls:
            self.assertTrue(url.startswith("https://raw.githubusercontent.com/"), url)

    def test_override_uses_only_given_url(self):
        self.assertEqual(_subscriptions(" https://x/y.yaml "), (" https://x/y.yaml ",))


class FallbackTests(unittest.TestCase):
    def test_first_source_failure_falls_through_to_next(self):
        with tempfile.TemporaryDirectory() as directory:
            seen: list[str] = []

            def fetch(url: str, dest: Path) -> None:
                seen.append(url)
                if url == GOOD:
                    raise ProxySetupError("订阅内容过小，可能拉取失败")
                dest.write_text(TWO_NODE_YAML, encoding="utf-8")

            code, _ = _run("", Path(directory) / "work", fetch, lambda *_: "n1")
            self.assertEqual(code, 0)
            # 只走到第二个源就成功，第三个不应再被请求
            self.assertEqual(seen, list(proxy_setup.DEFAULT_SUBSCRIPTIONS[:2]))

    def test_all_sources_failing_reports_every_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProxySetupError) as caught:
                _run("", Path(directory) / "work", None, lambda *_: "")
            message = str(caught.exception)
            for url in proxy_setup.DEFAULT_SUBSCRIPTIONS:
                self.assertIn(url, message)
            self.assertIn("所有节点均不可用", message)

    def test_each_source_gets_its_own_work_dir(self):
        """源之间不能共用 config.yaml，否则上一个源的节点定义会污染下一个。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "work"
            with self.assertRaises(ProxySetupError):
                _run("", root, None, lambda *_: "")
            self.assertEqual(
                sorted(p.name for p in root.iterdir() if p.is_dir()),
                [f"sub{i}" for i in range(len(proxy_setup.DEFAULT_SUBSCRIPTIONS))],
            )

    def test_single_source_reuses_work_dir(self):
        """用户指定单个源时不建子目录，保持原有路径约定。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "work"
            code, _ = _run(GOOD, root, None, lambda *_: "n1")
            self.assertEqual(code, 0)
            self.assertTrue((root / "config.yaml").exists())
            self.assertEqual([p.name for p in root.iterdir() if p.is_dir()], [])


class ConfigTests(unittest.TestCase):
    """url-test 组是并行与健康检查的载体，配置写错就全盘失效。"""

    def _config(self) -> dict:
        import yaml

        with tempfile.TemporaryDirectory() as directory:
            sub = Path(directory) / "sub.yaml"
            sub.write_text(TWO_NODE_YAML, encoding="utf-8")
            out = Path(directory) / "config.yaml"
            proxy_setup._write_config(sub, out, 7890, 9090)
            return yaml.safe_load(out.read_text(encoding="utf-8"))

    def test_group_is_url_test_with_health_check(self):
        group = self._config()["proxy-groups"][0]
        self.assertEqual(group["type"], "url-test", "必须是 url-test 才能并行测速")
        self.assertEqual(group["url"], proxy_setup.HEALTH_CHECK_URL)
        self.assertEqual(group["expected-status"], 200, "只认 200，403 质询页的节点被排除")
        self.assertFalse(group["lazy"], "lazy 会跳过测速，选不出可用节点")

    def test_health_check_targets_sign_page_not_plugin(self):
        """实测存在 plugin.php 能开、签到页在浏览器里挂死的节点，必须以签到页为准。"""
        self.assertIn("k_misign-sign.html", proxy_setup.HEALTH_CHECK_URL)

    def test_rules_replaced_with_match_global(self):
        self.assertEqual(self._config()["rules"], ["MATCH,GLOBAL"])


class SwitchNodeTests(unittest.TestCase):
    """被 CF 拦下时的换节点路径。"""

    def _delays(self, payload: dict) -> dict:
        with mock.patch.object(proxy_setup, "_api", return_value=payload), \
             mock.patch.object(proxy_setup, "api_select") as select:
            chosen = proxy_setup.switch_to_next(9090, set())
        return {"chosen": chosen, "select": select}

    def test_picks_fastest_available(self):
        result = self._delays({"slow": 9000, "fast": 800})
        self.assertEqual(result["chosen"], "fast")

    def test_skips_already_tried_nodes(self):
        with mock.patch.object(proxy_setup, "_api", return_value={"a": 100, "b": 200}), \
             mock.patch.object(proxy_setup, "api_select") as select:
            chosen = proxy_setup.switch_to_next(9090, {"a"})
        self.assertEqual(chosen, "b")
        select.assert_called_once_with(9090, "b")

    def test_returns_none_when_all_tried(self):
        with mock.patch.object(proxy_setup, "_api", return_value={"a": 100}), \
             mock.patch.object(proxy_setup, "api_select"):
            self.assertIsNone(proxy_setup.switch_to_next(9090, {"a"}))

    def test_ignores_failed_probes(self):
        """延迟为 0 或非整数表示节点不可用，不能选。"""
        with mock.patch.object(proxy_setup, "_api", return_value={"dead": 0, "alive": 500}), \
             mock.patch.object(proxy_setup, "api_select"):
            self.assertEqual(proxy_setup.switch_to_next(9090, set()), "alive")


if __name__ == "__main__":
    unittest.main()
