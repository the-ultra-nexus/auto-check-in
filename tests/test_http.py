"""HTTP helper tests: session creation and proxy rotation."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
