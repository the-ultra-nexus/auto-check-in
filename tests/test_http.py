"""HTTP helper tests: direct-first probing and on-demand proxy batches."""

from __future__ import annotations

import unittest
from unittest import mock

import requests
from requests.exceptions import ProxyError

from auto_check_in.config import NetworkConfig
from auto_check_in.http import FailoverSession, SessionProvider


def _pool_fetcher(*batches: tuple[str, ...]) -> mock.Mock:
    iterator = iter(batches)

    def fetch() -> tuple[str, ...]:
        try:
            return next(iterator)
        except StopIteration:
            return ()

    return mock.Mock(side_effect=fetch)


class SessionProviderTests(unittest.TestCase):
    def test_no_pool_session_has_empty_proxies(self):
        provider = SessionProvider(NetworkConfig())
        session = provider.new_session()
        try:
            self.assertEqual(session.proxies, {})
            self.assertTrue(session._direct_first)
            self.assertIsNone(session._pool_fetcher)
        finally:
            session.close()

    def test_provider_passes_direct_first(self):
        provider = SessionProvider(NetworkConfig(), direct_first=False)
        session = provider.new_session()
        try:
            self.assertFalse(session._direct_first)
        finally:
            session.close()

    def test_provider_wires_pool_fetcher(self):
        provider = SessionProvider(
            NetworkConfig(proxy_pool_urls=("https://pool.example/data.txt",)),
            probe_url="https://site.example/k_misign-sign.html",
        )
        session = provider.new_session()
        try:
            self.assertIsNotNone(session._pool_fetcher)
        finally:
            session.close()

    def test_site_session_ignores_ambient_env_proxies(self):
        session = SessionProvider(NetworkConfig()).new_session()
        try:
            self.assertFalse(session.trust_env)
        finally:
            session.close()


class FailoverDirectFirstTests(unittest.TestCase):
    def _session(self, fetcher, direct_first: bool = True) -> FailoverSession:
        return FailoverSession(direct_first=direct_first, pool_fetcher=fetcher)

    def test_direct_success_returns_without_batch(self):
        session = self._session(_pool_fetcher(("http://1.2.3.4:8080",)))
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(attempts, [{}])
            session._pool_fetcher.assert_not_called()
        finally:
            session.close()

    def test_direct_failure_acquires_batch_and_retries(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080",))
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            return mock.Mock(status_code=403 if len(attempts) == 1 else 200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                attempts,
                [
                    {},
                    {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                ],
            )
            fetcher.assert_called_once_with()
        finally:
            session.close()

    def test_direct_connection_error_acquires_batch(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080",))
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                raise requests.exceptions.ConnectionError("direct blocked")
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(attempts), 2)
        finally:
            session.close()

    def test_direct_first_disabled_acquires_batch_upfront(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080",))
        session = self._session(fetcher, direct_first=False)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            session.request("GET", "https://site.example")
        try:
            self.assertEqual(
                attempts,
                [{"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"}],
            )
            fetcher.assert_called_once_with()
        finally:
            session.close()

    def test_sticky_direct_later_failure_acquires_batch(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080",))
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 2:
                return mock.Mock(status_code=403)
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            session.request("GET", "https://site.example")
            session.request("GET", "https://site.example/k_misign-sign.html")
            response = session.request("GET", "https://site.example/plugin.php")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(attempts[0], {})
            self.assertEqual(attempts[1], {})
            self.assertEqual(
                attempts[2],
                {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
            )
        finally:
            session.close()

    def test_pool_unavailable_returns_direct_rejection(self):
        fetcher = _pool_fetcher()
        session = self._session(fetcher)

        def fake_request(self_, method, url, **kwargs):
            return mock.Mock(status_code=403)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 403)
        finally:
            session.close()


class FailoverBatchTests(unittest.TestCase):
    def _session(self, fetcher) -> FailoverSession:
        return FailoverSession(direct_first=False, pool_fetcher=fetcher)

    def test_batch_rotates_on_proxy_failure(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                raise ProxyError("Unable to connect to proxy")
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                attempts,
                [
                    {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                    {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
                ],
            )
        finally:
            session.close()

    def test_http_rejection_rotates_to_next_proxy(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                return mock.Mock(status_code=403)
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(attempts), 2)
        finally:
            session.close()

    def test_batch_exhausted_acquires_next_batch(self):
        fetcher = _pool_fetcher(
            ("http://1.2.3.4:8080",),
            ("http://5.6.7.8:3128",),
        )
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            return mock.Mock(status_code=200 if len(attempts) >= 2 else 403)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(fetcher.call_count, 2)
            self.assertEqual(
                attempts[1],
                {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
            )
        finally:
            session.close()

    def test_max_batches_exhausted_returns_last_response(self):
        fetcher = _pool_fetcher(
            ("http://p1:80",),
            ("http://p2:80",),
            ("http://p3:80",),
            ("http://p4:80",),
            ("http://p5:80",),
        )
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            return mock.Mock(status_code=403)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://site.example")
        try:
            self.assertEqual(response.status_code, 403)
            self.assertEqual(fetcher.call_count, 5)
            self.assertEqual(len(attempts), 5)
        finally:
            session.close()

    def test_session_sticks_to_working_proxy(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = self._session(fetcher)
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                raise ProxyError("Unable to connect to proxy")
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            session.request("GET", "https://site.example")
            session.request("GET", "https://site.example/k_misign-sign.html")
        try:
            self.assertEqual(
                attempts[2],
                {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
            )
        finally:
            session.close()

    def test_batches_isolated_per_session(self):
        fetcher_a = _pool_fetcher(("http://1.1.1.1:80",))
        fetcher_b = _pool_fetcher(("http://2.2.2.2:80",))
        session_a = FailoverSession(direct_first=False, pool_fetcher=fetcher_a)
        session_b = FailoverSession(direct_first=False, pool_fetcher=fetcher_b)
        proxies_seen: dict[str, list[dict]] = {"a": [], "b": []}

        def fake_request(self_, method, url, **kwargs):
            tag = "a" if self_ is session_a else "b"
            proxies_seen[tag].append(dict(self_.proxies))
            return mock.Mock(status_code=200)

        try:
            with mock.patch.object(requests.Session, "request", fake_request):
                session_a.request("GET", "https://site-a.example")
                session_b.request("GET", "https://site-b.example")
            self.assertEqual(
                proxies_seen["a"],
                [{"http": "http://1.1.1.1:80", "https": "http://1.1.1.1:80"}],
            )
            self.assertEqual(
                proxies_seen["b"],
                [{"http": "http://2.2.2.2:80", "https": "http://2.2.2.2:80"}],
            )
            fetcher_a.assert_called_once_with()
            fetcher_b.assert_called_once_with()
        finally:
            session_a.close()
            session_b.close()

    def test_all_proxies_fail_raises_last_error(self):
        fetcher = _pool_fetcher(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = self._session(fetcher)

        def fake_request(self_, method, url, **kwargs):
            raise ProxyError("Unable to connect to proxy")

        try:
            with mock.patch.object(requests.Session, "request", fake_request):
                with self.assertRaises(ProxyError):
                    session.request("GET", "https://site.example")
        finally:
            session.close()

    def test_failover_log_redacts_credentials(self):
        fetcher = _pool_fetcher(("http://user:pass@1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = self._session(fetcher)

        def fake_request(self_, method, url, **kwargs):
            raise ProxyError("Unable to connect to proxy")

        with mock.patch.object(requests.Session, "request", fake_request), self.assertLogs(
            "auto_check_in", level="DEBUG"
        ) as logs:
            with self.assertRaises(ProxyError):
                session.request("GET", "https://site.example")
        text = "\n".join(logs.output)
        try:
            self.assertIn("http://***@1.2.3.4:8080", text)
            self.assertNotIn("user:pass", text)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
