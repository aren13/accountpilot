"""Tests for SP3 IMAP auth dispatch in MailPlugin._make_real_imap.

The SP3 model: MailPlugin resolves the credential via Secrets.resolve()
and picks XOAUTH2 vs LOGIN based on whether credentials_ref is an
``oauth:`` URI. ImapClient never resolves credentials itself.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from accountpilot.core.auth import Secrets
from accountpilot.plugins.mail.config import MailAccountConfig, MailPluginConfig
from accountpilot.plugins.mail.plugin import MailPlugin


def _make_plugin(credentials_ref: str, *, fake_token: str) -> MailPlugin:
    """Build a MailPlugin with one account + a stubbed Secrets.resolve."""
    cfg = MailPluginConfig(
        accounts=[
            MailAccountConfig(
                identifier="aren@example.com",
                owner="aren@example.com",
                provider="gmail",
                credentials_ref=credentials_ref,
            )
        ]
    )
    secrets = Secrets({})
    # Stub the SP3 Secrets.resolve so we don't hit real OAuth/shell.
    secrets.resolve = lambda uri: fake_token  # type: ignore[method-assign]
    return MailPlugin(
        config=cfg.model_dump(),
        storage=object(),  # not used by _make_real_imap
        secrets=secrets,
    )


def test_make_real_imap_picks_xoauth2_when_credentials_ref_is_oauth_google() -> None:
    """credentials_ref='oauth:google:1' → IMAP auth.method='oauth2'."""
    plugin = _make_plugin("oauth:google:1", fake_token="ya29.fake-access-token")
    account = plugin._accounts["aren@example.com"]

    client = plugin._make_real_imap(account)

    assert client._account.imap.auth.method == "oauth2"
    assert client._account.imap.auth.password == "ya29.fake-access-token"


def test_make_real_imap_picks_xoauth2_when_credentials_ref_is_oauth_microsoft() -> None:
    """credentials_ref='oauth:microsoft:2' → IMAP auth.method='oauth2'."""
    plugin = _make_plugin("oauth:microsoft:2", fake_token="EwB-fake-msal-token")
    account = plugin._accounts["aren@example.com"]

    client = plugin._make_real_imap(account)

    assert client._account.imap.auth.method == "oauth2"
    assert client._account.imap.auth.password == "EwB-fake-msal-token"


def test_make_real_imap_picks_password_when_credentials_ref_is_password_cmd() -> None:
    """credentials_ref='password_cmd:...' → IMAP auth.method='password'."""
    plugin = _make_plugin(
        "password_cmd:op read op://Personal/Gmail/password",
        fake_token="resolved-pw",
    )
    account = plugin._accounts["aren@example.com"]

    client = plugin._make_real_imap(account)

    assert client._account.imap.auth.method == "password"
    assert client._account.imap.auth.password == "resolved-pw"


def test_make_real_imap_picks_password_for_literal_credentials_ref() -> None:
    """credentials_ref='literal-secret' → IMAP auth.method='password'."""
    plugin = _make_plugin("literal-secret", fake_token="literal-secret")
    account = plugin._accounts["aren@example.com"]

    client = plugin._make_real_imap(account)

    assert client._account.imap.auth.method == "password"
    assert client._account.imap.auth.password == "literal-secret"


# ─── ImapClient SASL dispatch (driven off auth.method) ───────────────────


class _FakeResponse:
    def __init__(self, result: str = "OK") -> None:
        self.result = result
        self.lines: list[Any] = []


class _FakeIMAP4SSL:
    """Minimal aioimaplib.IMAP4_SSL stand-in capturing login/xoauth2 calls."""

    last_instance: _FakeIMAP4SSL | None = None

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.login_called_with: tuple[str, str] | None = None
        self.xoauth2_called_with: tuple[str, str] | None = None
        self.selected: str | None = None
        _FakeIMAP4SSL.last_instance = self

    async def wait_hello_from_server(self) -> None:
        return None

    async def login(self, email: str, password: str) -> _FakeResponse:
        self.login_called_with = (email, password)
        return _FakeResponse("OK")

    async def xoauth2(self, email: str, token: str) -> _FakeResponse:
        self.xoauth2_called_with = (email, token)
        return _FakeResponse("OK")

    async def select(self, folder: str) -> _FakeResponse:
        self.selected = folder
        return _FakeResponse("OK")


def _build_imap_client(auth_method: str, credential: str) -> Any:
    from types import SimpleNamespace

    from accountpilot.plugins.mail.imap.client import ImapClient

    legacy_account = SimpleNamespace(
        email="aren@example.com",
        name="aren@example.com",
        provider="gmail",
        imap=SimpleNamespace(
            host="imap.gmail.com",
            port=993,
            encryption="tls",
            auth=SimpleNamespace(
                method=auth_method,
                password=credential,
            ),
        ),
    )
    legacy_sync = SimpleNamespace(
        idle_timeout=1740,
        reconnect_base_delay=5,
        reconnect_max_delay=300,
    )
    return ImapClient(account=legacy_account, sync_config=legacy_sync)


@pytest.mark.asyncio
async def test_imap_connect_uses_xoauth2_when_auth_method_is_oauth2() -> None:
    """auth.method='oauth2' → conn.xoauth2(email, token), NOT conn.login."""
    client = _build_imap_client("oauth2", "fake-access-token")
    with patch(
        "accountpilot.plugins.mail.imap.client.IMAP4_SSL", _FakeIMAP4SSL
    ):
        await client.connect("INBOX")

    fake = _FakeIMAP4SSL.last_instance
    assert fake is not None
    assert fake.xoauth2_called_with == ("aren@example.com", "fake-access-token")
    assert fake.login_called_with is None


@pytest.mark.asyncio
async def test_imap_connect_uses_login_when_auth_method_is_password() -> None:
    """auth.method='password' → conn.login(email, password), NOT conn.xoauth2."""
    client = _build_imap_client("password", "plaintext-pw")
    with patch(
        "accountpilot.plugins.mail.imap.client.IMAP4_SSL", _FakeIMAP4SSL
    ):
        await client.connect("INBOX")

    fake = _FakeIMAP4SSL.last_instance
    assert fake is not None
    assert fake.login_called_with == ("aren@example.com", "plaintext-pw")
    assert fake.xoauth2_called_with is None
