"""通知通道注册表：按环境变量启用渠道，每渠道独立超时，无全局可变状态。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import smtplib
import threading
import time
import urllib.parse
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import requests

from .http import random_user_agent

TIMEOUT = 15


def _env(name: str) -> str:
    return os.environ.get(name, "") or ""


def _headers() -> dict[str, str]:
    return {"User-Agent": random_user_agent()}


def console(title: str, content: str) -> None:
    if _env("CONSOLE").lower() not in {"1", "true", "yes", "on"}:
        return
    print(f"{title}\n{content}")


def bark(title: str, content: str) -> None:
    url = _env("BARK_PUSH")
    if not url:
        return
    params = {}
    for key, env in (
        ("group", "BARK_GROUP"),
        ("sound", "BARK_SOUND"),
        ("icon", "BARK_ICON"),
        ("level", "BARK_LEVEL"),
        ("url", "BARK_URL"),
    ):
        if _env(env):
            params[key] = _env(env)
    requests.post(url, data={"title": title, "body": content}, params=params, headers=_headers(), timeout=TIMEOUT)


def serverJ(title: str, content: str) -> None:
    key = _env("PUSH_KEY")
    if not key:
        return
    requests.post(
        f"https://sctapi.ftqq.com/{key}.send",
        data={"title": title, "desp": content},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def telegram(title: str, content: str) -> None:
    token = _env("TG_BOT_TOKEN")
    chat_id = _env("TG_USER_ID")
    if not token or not chat_id:
        return
    base = _env("TG_API_HOST") or "https://api.telegram.org"
    requests.post(
        f"{base}/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": f"{title}\n{content}"},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def dingtalk(title: str, content: str) -> None:
    token = _env("DD_BOT_TOKEN")
    secret = _env("DD_BOT_SECRET")
    if not token or not secret:
        return
    timestamp = str(round(time.time() * 1000))
    digest = hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
    signed = urllib.parse.quote_plus(base64.b64encode(digest))
    url = f"https://oapi.dingtalk.com/robot/send?access_token={token}&timestamp={timestamp}&sign={signed}"
    requests.post(
        url,
        json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def feishu(title: str, content: str) -> None:
    key = _env("FSKEY")
    if not key:
        return
    requests.post(
        f"https://open.feishu.cn/open-apis/bot/v2/hook/{key}",
        json={"msg_type": "text", "content": {"text": f"{title}\n{content}"}},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def qywx_bot(title: str, content: str) -> None:
    key = _env("QYWX_KEY")
    if not key:
        return
    requests.post(
        f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}",
        json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def pushplus(title: str, content: str) -> None:
    token = _env("PUSH_PLUS_TOKEN")
    if not token:
        return
    requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def pushdeer(title: str, content: str) -> None:
    key = _env("DEER_KEY")
    if not key:
        return
    base = _env("DEER_URL") or "https://api2.pushdeer.com"
    requests.get(
        f"{base}/message/push",
        params={"pushkey": key, "text": f"{title}\n{content}"},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def webhook(title: str, content: str) -> None:
    url = _env("WEBHOOK_URL")
    method = _env("WEBHOOK_METHOD")
    if not url or not method:
        return
    requests.request(
        method.upper(),
        url,
        json={"title": title, "content": content},
        headers=_headers(),
        timeout=TIMEOUT,
    )


def ntfy(title: str, content: str) -> None:
    topic = _env("NTFY_TOPIC")
    if not topic:
        return
    base = _env("NTFY_URL") or "https://ntfy.sh"
    requests.post(
        f"{base}/{topic}",
        data=content.encode("utf-8"),
        headers={"Title": title, **_headers()},
        timeout=TIMEOUT,
    )


def smtp(title: str, content: str) -> None:
    server = _env("SMTP_SERVER")
    use_ssl = _env("SMTP_SSL").lower() == "true"
    email = _env("SMTP_EMAIL")
    password = _env("SMTP_PASSWORD")
    name = _env("SMTP_NAME")
    if not server or not email or not password or not name:
        return
    message = MIMEText(content, "plain", "utf-8")
    message["Subject"] = Header(title, "utf-8")
    message["From"] = formataddr((Header(name, "utf-8").encode(), email))
    message["To"] = formataddr((Header(name, "utf-8").encode(), email))
    client = smtplib.SMTP_SSL(server, timeout=TIMEOUT) if use_ssl else smtplib.SMTP(server, timeout=TIMEOUT)
    try:
        client.login(email, password)
        client.sendmail(email, email, message.as_bytes())
    finally:
        client.close()


CHANNELS = (bark, serverJ, telegram, dingtalk, feishu, qywx_bot, pushplus, pushdeer, webhook, ntfy, smtp, console)


def _safe(channel, title: str, content: str) -> None:
    try:
        channel(title, content)
    except Exception as exc:
        print(f"通知渠道 {channel.__name__} 发送失败: {exc}")


def send(title: str, content: str, **_kwargs) -> None:
    """按环境变量启用的渠道并发发送通知，渠道异常不影响调用方。"""
    if not content:
        return
    skip = _env("SKIP_PUSH_TITLE")
    if skip and title in re.split(r"\n", skip):
        return
    threads = [
        threading.Thread(target=_safe, args=(channel, title, content), daemon=True)
        for channel in CHANNELS
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
