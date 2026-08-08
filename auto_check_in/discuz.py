"""Discuz-generic parsing and response helpers reused by Discuz-based sites."""

from __future__ import annotations

import hashlib
import re

from lxml import etree

from .errors import LoginError
from .models import CheckInStatus
from .security import redact_text

DISCUZ_ALREADY_MARKERS = ("今日已签", "您今天已经签到过了", "今日已签到")


def md5_password(value: str) -> str:
    """Discuz login form password digest."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def extract_formhash(html: str) -> str:
    """Extract the first ``input[name=formhash]`` value from HTML."""
    root = etree.HTML(html)
    if root is None:
        return ""
    values = root.xpath('//input[@name="formhash"]/@value')
    return str(values[0]).strip() if values else ""


def parse_login_dialog(dialog: str) -> dict[str, str]:
    """Parse formhash/referer/loginhash from the Discuz login dialog CDATA."""
    html = dialog
    try:
        xml_root = etree.fromstring(dialog.encode("utf-8"))
        if xml_root.text:
            html = xml_root.text
    except Exception:
        pass
    root = etree.HTML(html)
    if root is None:
        raise LoginError("登录弹框解析失败")
    form = None
    for candidate in root.xpath("//form"):
        action = candidate.get("action", "")
        if "member.php" in action and "loginsubmit" in action:
            form = candidate
            break
    if form is None:
        raise LoginError("登录弹框解析失败：未找到登录表单")
    action = form.get("action", "")
    match = re.search(r"[?&]loginhash=([A-Za-z0-9]+)", action)
    loginhash = match.group(1) if match else ""
    formhash = form.xpath('.//input[@name="formhash"]/@value')
    referer = form.xpath('.//input[@name="referer"]/@value')
    if not loginhash or not formhash:
        raise LoginError("登录弹框解析失败：缺少 formhash/loginhash")
    return {
        "loginhash": loginhash,
        "formhash": str(formhash[0]).strip(),
        "referer": str(referer[0]).strip() if referer else "",
    }


def classify_discuz_response(text: str) -> tuple[CheckInStatus, str]:
    """Map a Discuz AJAX/error response to a stable status."""
    if "Discuz! System Error" in text:
        return CheckInStatus.LOGIN_FAILED, "会话失效"
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except Exception:
        return CheckInStatus.CHECK_IN_FAILED, "签到响应格式异常"
    if root.tag != "root":
        return CheckInStatus.CHECK_IN_FAILED, "签到响应格式异常"
    cdata = (root.text or "").strip()
    if any(marker in cdata for marker in DISCUZ_ALREADY_MARKERS):
        return CheckInStatus.ALREADY_CHECKED_IN, ""
    if not cdata:
        return CheckInStatus.SUCCESS, ""
    return CheckInStatus.CHECK_IN_FAILED, redact_text(cdata[:80])
