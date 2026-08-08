"""通知通道注册表：按环境变量启用渠道，每渠道独立超时，无全局可变状态。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import smtplib
import ssl
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


_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(value: str) -> bool:
    """Lenient boolean parse for env flags (1/true/yes/on, case-insensitive)."""
    return value.strip().lower() in _TRUTHY


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


_SMTP_DEFINITIVE_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
)


def _parse_smtp_server(server: str) -> tuple[str, int | None]:
    """Split ``SMTP_SERVER`` into ``(host, port)``, supporting ``host`` / ``host:port``."""
    host = server.strip()
    if host.startswith("[") and "]" in host:
        end = host.index("]")
        hostname = host[1:end]
        remainder = host[end + 1 :]
        if remainder.startswith(":"):
            return hostname, int(remainder[1:])
        return hostname, None
    if host.count(":") == 1:
        hostname, port_text = host.rsplit(":", 1)
        if not port_text.isdigit():
            raise ValueError(f"SMTP_SERVER 端口无效: {server!r}")
        return hostname.strip(), int(port_text)
    return host, None


def _smtp_attempts(
    host: str,
    port: int | None,
    port_override: str,
    use_ssl: bool,
    use_starttls: bool,
) -> list[tuple[str, int]]:
    """Return ordered ``(mode, port)`` connection attempts for the SMTP channel.

    Modes: ``ssl`` (implicit TLS, e.g. 465), ``starttls`` (STARTTLS, e.g. 587),
    ``plain`` (unencrypted). When neither ``SMTP_SSL`` nor ``SMTP_STARTTLS`` is
    enabled, the channel tries the most likely mode first and falls back on
    connection-level failures so a mismatched server/flag combination still works.
    Port priority: ``SMTP_PORT`` > port embedded in ``SMTP_SERVER`` > mode default.
    """
    explicit = int(port_override) if port_override else port
    if use_ssl:
        return [("ssl", explicit or 465)]
    if use_starttls:
        return [("starttls", explicit or 587)]
    if explicit:
        if explicit == 465:
            return [("ssl", 465), ("starttls", 465), ("plain", 465)]
        if explicit == 587:
            return [("starttls", 587), ("plain", 587), ("ssl", 587)]
        return [("starttls", explicit), ("plain", explicit), ("ssl", explicit)]
    return [("starttls", 587), ("ssl", 465), ("plain", 25)]


def _smtp_send(
    host: str,
    port: int,
    mode: str,
    email: str,
    recipient: str,
    password: str,
    message: MIMEText,
) -> None:
    """Connect in one mode and send the message, raising on any failure."""
    if mode == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT)
    else:
        client = smtplib.SMTP(host, port, timeout=TIMEOUT)
        client.ehlo()
        if mode == "starttls":
            if not client.has_extn("starttls"):
                raise smtplib.SMTPServerDisconnected("服务器未提供 STARTTLS")
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
    try:
        client.login(email, password)
        client.sendmail(email, recipient, message.as_bytes())
    finally:
        try:
            client.quit()
        except Exception:
            client.close()


def smtp(title: str, content: str) -> None:
    server = _env("SMTP_SERVER")
    use_ssl = _truthy(_env("SMTP_SSL"))
    use_starttls = _truthy(_env("SMTP_STARTTLS"))
    email = _env("SMTP_EMAIL")
    password = _env("SMTP_PASSWORD")
    name = _env("SMTP_NAME")
    if not server or not email or not password or not name:
        return
    recipient = _env("SMTP_TO") or email
    port_override = _env("SMTP_PORT")
    if port_override and not port_override.isdigit():
        raise ValueError(f"SMTP_PORT 无效: {port_override!r}")
    host, port = _parse_smtp_server(server)
    message = MIMEText(content, "plain", "utf-8")
    message["Subject"] = Header(title, "utf-8")
    message["From"] = formataddr((Header(name, "utf-8").encode(), email))
    message["To"] = formataddr((Header(name, "utf-8").encode(), recipient))
    attempts = _smtp_attempts(host, port, port_override, use_ssl, use_starttls)
    last_error: Exception | None = None
    for mode, target_port in attempts:
        try:
            _smtp_send(host, target_port, mode, email, recipient, password, message)
            return
        except _SMTP_DEFINITIVE_ERRORS:
            raise
        except Exception as exc:  # 连接层错误：尝试下一种模式
            last_error = exc
    if last_error is not None:
        raise last_error


CHANNELS = (bark, serverJ, telegram, dingtalk, feishu, qywx_bot, pushplus, pushdeer, webhook, ntfy, smtp, console)


CHANNEL_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "bark": ("BARK_PUSH",),
    "serverJ": ("PUSH_KEY",),
    "telegram": ("TG_BOT_TOKEN", "TG_USER_ID"),
    "dingtalk": ("DD_BOT_TOKEN", "DD_BOT_SECRET"),
    "feishu": ("FSKEY",),
    "qywx_bot": ("QYWX_KEY",),
    "pushplus": ("PUSH_PLUS_TOKEN",),
    "pushdeer": ("DEER_KEY",),
    "webhook": ("WEBHOOK_URL", "WEBHOOK_METHOD"),
    "ntfy": ("NTFY_TOPIC",),
    "smtp": ("SMTP_SERVER", "SMTP_EMAIL", "SMTP_PASSWORD", "SMTP_NAME"),
    "console": ("CONSOLE",),
}


def active_channels() -> list[str]:
    """Return names of channels whose required environment variables are enabled."""
    active: list[str] = []
    for name, keys in CHANNEL_REQUIREMENTS.items():
        if name == "console":
            if _env("CONSOLE").lower() in {"1", "true", "yes", "on"}:
                active.append(name)
        elif all(_env(key) for key in keys):
            active.append(name)
    return active


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
