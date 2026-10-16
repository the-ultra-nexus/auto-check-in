"""Shared fixtures and helpers for site adapter tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from auto_check_in.config import SiteConfig

DIALOG = """<?xml version="1.0" encoding="utf-8"?><root><![CDATA[
<form id="loginform_X" action="member.php?mod=logging&amp;action=login&amp;loginsubmit=yes&amp;handlekey=login&amp;loginhash=Ab12" onsubmit="return false;">
<input type="hidden" name="formhash" value="abc123" />
<input type="hidden" name="referer" value="https://site.example/k_misign-sign.html" />
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


def write_config(text: str) -> Path:
    directory = tempfile.mkdtemp()
    path = Path(directory) / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


class FakeElement:
    def __init__(self, driver, kind: str):
        self._driver = driver
        self._kind = kind

    def send_keys(self, text: str) -> None:
        self._driver.typed.append((self._kind, text))

    def clear(self) -> None:
        pass

    def click(self) -> None:
        self._driver.clicks.append(self._kind)
        if self._kind == "submit":
            self._driver.login_lands = True
            if self._driver.fix_after_login:
                self._driver.plugin_body = "<root><![CDATA[]]></root>"


class FakeForm:
    def __init__(self, driver):
        self._driver = driver

    def find_element(self, by, selector):
        if "username" in selector:
            return FakeElement(self._driver, "username")
        if "password" in selector:
            return FakeElement(self._driver, "password")
        if self._driver.has_submit:
            return FakeElement(self._driver, "submit")
        raise RuntimeError("no such element")


class FakeDriver:
    """Scripted browser: enough surface for the browser adapter's flow."""

    def __init__(self):
        self.typed: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.visited: list[str] = []
        self.cookies: list[dict] = []
        self.login_lands = False
        self.fix_after_login = False
        self.has_submit = True
        self.title = "登录 - 站点"
        self.sign_page = LOGGED_SIGN_PAGE
        self.plugin_body = "<root><![CDATA[]]></root>"
        self.scripts: list[str] = []

    @property
    def page_source(self) -> str:
        if "k_misign-sign.html" in (self.visited[-1] if self.visited else ""):
            return self.sign_page
        return "<html><form><input name='username'><input name='password'></form></html>"

    def get(self, url: str) -> None:
        self.visited.append(url)
        if "k_misign-sign.html" in url:
            self.title = "每日签到 - 站点"

    def find_element(self, by, selector):
        if selector == '//form[.//input[@name="username"]]':
            return FakeForm(self)
        raise RuntimeError("not found")

    def execute_async_script(self, script: str, *args):
        self.scripts.append(script)
        return self.plugin_body

    def get_cookies(self):
        if self.login_lands and not any(c["name"].endswith("_auth") for c in self.cookies):
            self.cookies.append({"name": "SgL6_2132_auth", "value": "abc"})
        return list(self.cookies)

    def add_cookie(self, cookie: dict) -> None:
        self.cookies.append(cookie)

    def delete_all_cookies(self) -> None:
        self.cookies.clear()

    def quit(self) -> None:
        pass


def make_site_config(
    name: str = "sijishe",
    adapter: str = "sijishe",
    base_url: str = "https://site.example",
    accounts: str = "alice&pw",
    **overrides,
) -> SiteConfig:
    values = dict(name=name, adapter=adapter, base_url=base_url, accounts=accounts)
    values.update(overrides)
    return SiteConfig(**values)
