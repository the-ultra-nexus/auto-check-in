"""HTTP helper tests: session creation and proxy rotation."""

from __future__ import annotations

import unittest
from unittest import mock

import requests
from requests.exceptions import ProxyError

from auto_check_in.config import NetworkConfig
from auto_check_in.http import SessionProvider


class SessionProxyTests(unittest.TestCase):
    def test_no_proxy_session_has_empty_proxies(self):
        provider = SessionProvider(NetworkConfig())
        session = provider.new_session()
        try:
            self.assertEqual(session.proxies, {})
        finally:
            session.close()

    def test_proxy_rotates_round_robin(self):
        provider = SessionProvider(
            NetworkConfig(proxy_urls=("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        )
        sessions = [provider.new_session() for _ in range(3)]
        try:
            self.assertEqual(
                [session.proxies for session in sessions],
                [
                    {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                    {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
                    {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                ],
            )
        finally:
            for session in sessions:
                session.close()


class FailoverSessionTests(unittest.TestCase):
    def _provider(self, proxies: tuple[str, ...]) -> SessionProvider:
        return SessionProvider(NetworkConfig(proxy_urls=proxies))

    def test_site_session_ignores_ambient_env_proxies(self):
        session = self._provider(("http://1.2.3.4:8080",)).new_session()
        try:
            self.assertFalse(session.trust_env)
        finally:
            session.close()

    def test_failover_rotates_to_next_proxy(self):
        provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                raise ProxyError("Unable to connect to proxy")
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://xsijishe.net")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                attempts,
                [
                    {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                    {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
                ],
            )
            self.assertEqual(
                session.proxies,
                {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
            )
        finally:
            session.close()

    def test_http_rejection_rotates_to_next_proxy(self):
        provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                return mock.Mock(status_code=403)
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://xsijishe.net")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                attempts,
                [
                    {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                    {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
                ],
            )
            self.assertEqual(
                session.proxies,
                {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
            )
        finally:
            session.close()

    def test_rotate_status_codes_cover_rejections(self):
        for status in (403, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
                session = provider.new_session()
                attempts: list[dict] = []

                def fake_request(self_, method, url, **kwargs):
                    attempts.append(dict(self_.proxies))
                    if len(attempts) == 1:
                        return mock.Mock(status_code=status)
                    return mock.Mock(status_code=200)

                with mock.patch.object(requests.Session, "request", fake_request):
                    response = session.request("GET", "https://xsijishe.net")
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(len(attempts), 2)
                    self.assertEqual(
                        session.proxies,
                        {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
                    )
                finally:
                    session.close()

    def test_other_http_status_does_not_rotate(self):
        for status in (200, 301, 401, 404):
            with self.subTest(status=status):
                provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
                session = provider.new_session()
                attempts: list[dict] = []

                def fake_request(self_, method, url, **kwargs):
                    attempts.append(dict(self_.proxies))
                    return mock.Mock(status_code=status)

                with mock.patch.object(requests.Session, "request", fake_request):
                    response = session.request("GET", "https://xsijishe.net")
                try:
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(len(attempts), 1)
                    self.assertEqual(
                        session.proxies,
                        {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
                    )
                finally:
                    session.close()

    def test_all_proxies_rejected_returns_last_response(self):
        provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            return mock.Mock(status_code=403 if len(attempts) == 1 else 503)

        with mock.patch.object(requests.Session, "request", fake_request):
            response = session.request("GET", "https://xsijishe.net")
        try:
            self.assertEqual(response.status_code, 503)
            self.assertEqual(len(attempts), 2)
        finally:
            session.close()

    def test_session_sticks_to_working_proxy(self):
        provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            if len(attempts) == 1:
                raise ProxyError("Unable to connect to proxy")
            return mock.Mock(status_code=200)

        with mock.patch.object(requests.Session, "request", fake_request):
            session.request("GET", "https://xsijishe.net")
            session.request("GET", "https://xsijishe.net/k_misign-sign.html")
        try:
            self.assertEqual(len(attempts), 3)
            self.assertEqual(
                attempts[2],
                {"http": "http://5.6.7.8:3128", "https": "http://5.6.7.8:3128"},
            )
        finally:
            session.close()

    def test_all_proxies_fail_raises_last_error(self):
        provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            raise ProxyError("Unable to connect to proxy")

        with mock.patch.object(requests.Session, "request", fake_request):
            with self.assertRaises(ProxyError):
                session.request("GET", "https://xsijishe.net")
        try:
            self.assertEqual(len(attempts), 2)
        finally:
            session.close()

    def test_non_proxy_error_does_not_rotate(self):
        provider = self._provider(("http://1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()
        attempts: list[dict] = []

        def fake_request(self_, method, url, **kwargs):
            attempts.append(dict(self_.proxies))
            raise requests.exceptions.ConnectionError("boom")

        with mock.patch.object(requests.Session, "request", fake_request):
            with self.assertRaises(requests.exceptions.ConnectionError):
                session.request("GET", "https://xsijishe.net")
        try:
            self.assertEqual(len(attempts), 1)
            self.assertEqual(
                session.proxies,
                {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
            )
        finally:
            session.close()

    def test_failover_log_redacts_credentials(self):
        provider = self._provider(("http://user:pass@1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()

        def fake_request(self_, method, url, **kwargs):
            raise ProxyError("Unable to connect to proxy")

        with mock.patch.object(requests.Session, "request", fake_request), self.assertLogs(
            "auto_check_in", level="DEBUG"
        ) as logs:
            with self.assertRaises(ProxyError):
                session.request("GET", "https://xsijishe.net")
        text = "\n".join(logs.output)
        try:
            self.assertIn("http://***@1.2.3.4:8080", text)
            self.assertNotIn("user:pass", text)
        finally:
            session.close()

    def test_http_rejection_log_redacts_credentials(self):
        provider = self._provider(("http://user:pass@1.2.3.4:8080", "http://5.6.7.8:3128"))
        session = provider.new_session()

        def fake_request(self_, method, url, **kwargs):
            return mock.Mock(status_code=403)

        with mock.patch.object(requests.Session, "request", fake_request), self.assertLogs(
            "auto_check_in", level="DEBUG"
        ) as logs:
            session.request("GET", "https://xsijishe.net")
        text = "\n".join(logs.output)
        try:
            self.assertIn("http://***@1.2.3.4:8080", text)
            self.assertNotIn("user:pass", text)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
