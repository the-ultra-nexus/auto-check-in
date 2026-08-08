"""Shared fixtures and helpers for site adapter tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from auto_check_in.config import SiteConfig

DIALOG = """<?xml version="1.0" encoding="utf-8"?><root><![CDATA[
<form id="loginform_X" action="member.php?mod=logging&amp;action=login&amp;loginsubmit=yes&amp;handlekey=login&amp;loginhash=Ab12" onsubmit="return false;">
<input type="hidden" name="formhash" value="abc123" />
<input type="hidden" name="referer" value="https://xsijishe.net/k_misign-sign.html" />
<input type="text" name="username" />
<input type="password" name="password" />
<select name="questionid"><option value="0">无</option></select>
<input type="checkbox" name="cookietime" value="2592000" />
</form>
]]></root>"""

ANON_SIGN_PAGE = """<html><body>
<input type="hidden" name="formhash" value="pagehash1" />
<a id="JD_sign" href="member.php?mod=logging&amp;action=login" class="btn"></a>
</body></html>"""

LOGGED_SIGN_PAGE = """<html><body>
<input type="hidden" name="formhash" value="pagehash2" />
<a id="JD_sign" href="javascript:;" onclick="k_misign()" class="btn"></a>
</body></html>"""


class FakeCookie:
    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value


class FakeCookieJar:
    def __init__(self):
        self._cookies: list[FakeCookie] = []

    def append(self, cookie: FakeCookie) -> None:
        self._cookies.append(cookie)

    def __iter__(self):
        return iter(self._cookies)

    def set(self, name: str, value: str) -> None:
        self._cookies.append(FakeCookie(name, value))

    def get_dict(self) -> dict[str, str]:
        return {cookie.name: cookie.value for cookie in self._cookies}

    def clear(self) -> None:
        self._cookies.clear()


class FakeResponse:
    def __init__(self, text: str = "", status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Scripted HTTP session for adapter tests."""

    def __init__(self):
        self.headers: dict[str, str] = {}
        self.cookies = FakeCookieJar()
        self.requests: list[tuple[str, str, object]] = []
        self.sign_visits = 0
        self.plugin_response = FakeResponse("<root><![CDATA[]]></root>")
        self.dialog = DIALOG
        self.fix_after_login = False
        self.login_post_response: FakeResponse | None = None

    def _respond(self, url: str) -> FakeResponse:
        if "member.php?mod=logging&action=login&infloat=yes" in url:
            return FakeResponse(self.dialog)
        if "member.php?mod=logging&action=login&loginsubmit=yes" in url:
            if self.login_post_response is not None:
                return self.login_post_response
            self.cookies.append(FakeCookie("SgL6_2132_auth", "abc"))
            if self.fix_after_login:
                self.plugin_response = FakeResponse("<root><![CDATA[]]></root>")
            return FakeResponse("")
        if "plugin.php?id=k_misign:sign&operation=qiandao" in url:
            return self.plugin_response
        if "k_misign-sign.html" in url:
            self.sign_visits += 1
            return FakeResponse(ANON_SIGN_PAGE if self.sign_visits == 1 else LOGGED_SIGN_PAGE)
        return FakeResponse("")

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.requests.append(("GET", url, kwargs))
        return self._respond(url)

    def post(self, url: str, data=None, **kwargs) -> FakeResponse:
        self.requests.append(("POST", url, {"data": data, **kwargs}))
        return self._respond(url)

    def close(self) -> None:
        pass


def write_config(text: str) -> Path:
    directory = tempfile.mkdtemp()
    path = Path(directory) / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def make_site_config(
    name: str = "sijishe",
    adapter: str = "sijishe",
    base_url: str = "https://xsijishe.net",
    accounts: str = "alice&pw",
    **overrides,
) -> SiteConfig:
    values = dict(name=name, adapter=adapter, base_url=base_url, accounts=accounts)
    values.update(overrides)
    return SiteConfig(**values)
