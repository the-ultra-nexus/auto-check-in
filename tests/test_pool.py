"""Pool batch provider tests: entry parsing and probe classification."""

from __future__ import annotations

import unittest
from unittest import mock

import requests

from auto_check_in.pool import BATCH_SIZE, fetch_pool_batch, parse_pool_entry


class ParsePoolEntryTests(unittest.TestCase):
    def test_host_port(self):
        self.assertEqual(parse_pool_entry("1.2.3.4:8080"), "http://1.2.3.4:8080")

    def test_scheme_url_kept(self):
        self.assertEqual(parse_pool_entry("http://1.2.3.4:8080"), "http://1.2.3.4:8080")
        self.assertEqual(parse_pool_entry("https://1.2.3.4:443"), "https://1.2.3.4:443")

    def test_table_row_takes_first_two_columns(self):
        self.assertEqual(
            parse_pool_entry("1.2.3.4\t8080\tHTTP(S)\t国家\t1~10分钟"),
            "http://1.2.3.4:8080",
        )

    def test_invalid_entries(self):
        for line in ("", "   ", "1.2.3.4", "abc", "1.2.3.4:port", "socks5://1.2.3.4:1080"):
            self.assertIsNone(parse_pool_entry(line))


class FetchPoolBatchTests(unittest.TestCase):
    def _fake_get(self, pool_texts: dict[str, bytes], probe_status: int = 200):
        def fake_get(url: str, **kwargs):
            if "proxies" in kwargs:
                if probe_status == "raise":
                    raise requests.exceptions.ConnectionError("probe failed")
                return mock.Mock(status_code=probe_status)
            content = pool_texts.get(url)
            if content is None:
                raise requests.exceptions.ConnectionError(f"pool unreachable: {url}")
            response = mock.Mock()
            response.content = content
            return response

        return fake_get

    def test_parses_dedupes_and_returns_usable(self):
        pool_texts = {
            "https://pool-a": b"1.2.3.4:8080\n5.6.7.8:3128\nhttp://9.9.9.9:80\n",
            "https://pool-b": b"1.2.3.4:8080\n7.7.7.7:3128\n",
        }
        with mock.patch(
            "auto_check_in.pool.requests.get", side_effect=self._fake_get(pool_texts)
        ):
            batch = fetch_pool_batch(
                ("https://pool-a", "https://pool-b"),
                "https://site.example/k_misign-sign.html",
            )
        self.assertEqual(
            set(batch),
            {
                "http://1.2.3.4:8080",
                "http://5.6.7.8:3128",
                "http://9.9.9.9:80",
                "http://7.7.7.7:3128",
            },
        )

    def test_rejects_non_2xx_3xx(self):
        pool_texts = {"https://pool-a": b"1.2.3.4:8080\n5.6.7.8:3128\n"}
        with mock.patch(
            "auto_check_in.pool.requests.get",
            side_effect=self._fake_get(pool_texts, probe_status=403),
        ):
            batch = fetch_pool_batch(("https://pool-a",), "https://site.example/k_misign-sign.html")
        self.assertEqual(batch, ())

    def test_probe_errors_rejected(self):
        pool_texts = {"https://pool-a": b"1.2.3.4:8080\n"}
        with mock.patch(
            "auto_check_in.pool.requests.get",
            side_effect=self._fake_get(pool_texts, probe_status="raise"),
        ):
            batch = fetch_pool_batch(("https://pool-a",), "https://site.example/k_misign-sign.html")
        self.assertEqual(batch, ())

    def test_unreachable_pool_skipped(self):
        pool_texts = {"https://pool-b": b"1.2.3.4:8080\n"}
        with mock.patch(
            "auto_check_in.pool.requests.get", side_effect=self._fake_get(pool_texts)
        ):
            batch = fetch_pool_batch(
                ("https://pool-a", "https://pool-b"),
                "https://site.example/k_misign-sign.html",
            )
        self.assertEqual(batch, ("http://1.2.3.4:8080",))

    def test_stops_when_batch_full(self):
        lines = "".join(f"{i}.0.0.1:8080\n" for i in range(1, 10))
        pool_texts = {"https://pool-a": lines.encode()}
        with mock.patch(
            "auto_check_in.pool.requests.get", side_effect=self._fake_get(pool_texts)
        ):
            batch = fetch_pool_batch(("https://pool-a",), "https://site.example/k_misign-sign.html")
        self.assertEqual(len(batch), BATCH_SIZE)

    def test_no_pool_urls_returns_empty(self):
        self.assertEqual(fetch_pool_batch((), "https://site.example/k_misign-sign.html"), ())


if __name__ == "__main__":
    unittest.main()
