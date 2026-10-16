"""proxy_setup 测试：订阅源回退链 + 按延迟选节点。不起真实 mihomo，不打网络。"""

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
    "  - {name: slow, type: socks5, server: 127.0.0.1, port: 1080}\n"
    "  - {name: fast, type: socks5, server: 127.0.0.1, port: 1081}\n"
)


def _run(subscription: str, work: Path, fetch, probe, yaml_text=TWO_NODE_YAML) -> int:
    def fetch_writing(url: str, dest: Path) -> None:
        dest.write_text(yaml_text, encoding="utf-8")

    with mock.patch.object(proxy_setup, "_core_binary", return_value=Path("/bin/true")), \
         mock.patch.object(proxy_setup, "_fetch_subscription", side_effect=fetch or fetch_writing), \
         mock.patch.object(proxy_setup, "_probe_node", side_effect=probe), \
         mock.patch.object(proxy_setup, "api_select") as select, \
         mock.patch.object(proxy_setup.subprocess, "Popen") as popen, \
         mock.patch.object(proxy_setup.time, "sleep"):
        popen.return_value.poll.return_value = None  # None = 进程还活着
        code = setup(subscription, work, 7890, 9090)
    return code, (select.call_args[0][1] if select.called else None)


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

            code, _ = _run("", Path(directory) / "work", fetch, lambda *_: 0.5)
            self.assertEqual(code, 0)
            # 只走到第二个源就成功，第三个不应再被请求
            self.assertEqual(seen, list(proxy_setup.DEFAULT_SUBSCRIPTIONS[:2]))

    def test_all_sources_failing_reports_every_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProxySetupError) as caught:
                _run("", Path(directory) / "work", None, lambda *_: None)
            message = str(caught.exception)
            for url in proxy_setup.DEFAULT_SUBSCRIPTIONS:
                self.assertIn(url, message)
            self.assertIn("所有节点均不可用", message)  # 每个源的失败原因都被带出

    def test_each_source_gets_its_own_work_dir(self):
        """源之间不能共用 config.yaml，否则上一个源的节点定义会污染下一个。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "work"
            with self.assertRaises(ProxySetupError):
                _run("", root, None, lambda *_: None)
            self.assertEqual(
                sorted(p.name for p in root.iterdir() if p.is_dir()),
                [f"sub{i}" for i in range(len(proxy_setup.DEFAULT_SUBSCRIPTIONS))],
            )

    def test_single_source_reuses_work_dir(self):
        """用户指定单个源时不建子目录，保持原有路径约定。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "work"
            code, _ = _run(GOOD, root, None, lambda *_: 0.5)
            self.assertEqual(code, 0)
            self.assertTrue((root / "config.yaml").exists())
            self.assertEqual([p.name for p in root.iterdir() if p.is_dir()], [])


class NodeSelectionTests(unittest.TestCase):
    """关键行为：选最快节点，不是第一个可达的。"""

    def test_picks_fastest_not_first_reachable(self):
        """首节点能连但慢，会让浏览器 renderer 超时——必须选快的那个。"""
        with tempfile.TemporaryDirectory() as directory:
            latencies = {"slow": 9.0, "fast": 0.8}
            code, picked = _run(
                GOOD, Path(directory) / "work", None,
                lambda _api, name, *a: latencies[name],
            )
            self.assertEqual(code, 0)
            self.assertEqual(picked, "fast")

    def test_stops_early_when_a_node_is_fast_enough(self):
        with tempfile.TemporaryDirectory() as directory:
            latencies = {"slow": 0.3, "fast": 0.4}
            calls: list[str] = []
            code, picked = _run(
                GOOD, Path(directory) / "work", None,
                lambda _api, name, *a: (calls.append(name), latencies[name])[1],
            )
            self.assertEqual(code, 0)
            self.assertEqual(picked, "slow")
            self.assertEqual(calls, ["slow"], "够快就该收手，不必探完")

    def test_unreachable_nodes_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            latencies = {"slow": None, "fast": 1.2}
            code, picked = _run(
                GOOD, Path(directory) / "work", None,
                lambda _api, name, *a: latencies[name],
            )
            self.assertEqual(code, 0)
            self.assertEqual(picked, "fast")

    def test_all_nodes_unreachable_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProxySetupError) as caught:
                _run(GOOD, Path(directory) / "work", None, lambda *_: None)
            self.assertIn("所有节点均不可用", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
