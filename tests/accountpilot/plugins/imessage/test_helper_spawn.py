"""Tests for the disclaim-aware helper-spawn primitive.

The TCC responsibility chain on macOS makes plain `subprocess.Popen`
unsuitable for spawning the FDA helper from a parent that lacks FDA
itself (the entire point of the helper is that the parent — Python —
does not need FDA). `helper_client._spawn_helper` patches around this
by calling `responsibility_spawnattrs_setdisclaim(1)` so the helper
becomes its own TCC responsible process.

These tests exercise the spawn wrapper against benign system binaries
(`/bin/echo`, `/usr/bin/false`) — no helper or FDA required.
"""

from __future__ import annotations

import os
import platform
import subprocess

import pytest

from accountpilot.plugins.imessage import helper_client


def test_disclaim_symbol_resolved_on_macos() -> None:
    """The Apple-private disclaim symbol must be loadable on every supported macOS."""
    if platform.system() != "Darwin":
        pytest.skip("disclaim is macOS-only")
    assert helper_client._DISCLAIM is not None


def test_resolve_disclaim_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The escape hatch env var must opt out of the disclaim spawn path."""
    monkeypatch.setenv(helper_client.DISABLE_DISCLAIM_ENV, "1")
    assert helper_client._resolve_disclaim_symbol() is None


def test_resolve_disclaim_returns_none_off_darwin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux / Windows fall back to subprocess.Popen — symbol not bound."""
    monkeypatch.setattr(helper_client.platform, "system", lambda: "Linux")
    assert helper_client._resolve_disclaim_symbol() is None


def test_spawn_helper_disclaim_path_runs_real_subprocess() -> None:
    """End-to-end: spawn /bin/echo via the disclaim path, read its stdout."""
    if helper_client._DISCLAIM is None:
        pytest.skip("disclaim path unavailable on this platform")
    proc = helper_client._DisclaimedProcess(["/bin/echo", "hello-disclaim"])
    try:
        out = proc.stdout.read()
        err = proc.stderr.read()
        rc = proc.wait()
    finally:
        proc.kill()
    assert rc == 0, f"echo exited {rc}, stderr={err!r}"
    assert out.strip() == "hello-disclaim"


def test_spawn_helper_disclaim_propagates_nonzero_exit() -> None:
    """Exit code must surface through wait() — needed by iter_records."""
    if helper_client._DISCLAIM is None:
        pytest.skip("disclaim path unavailable on this platform")
    proc = helper_client._DisclaimedProcess(["/usr/bin/false"])
    proc.stdout.read()
    proc.stderr.read()
    assert proc.wait() == 1


def test_spawn_helper_falls_back_to_popen_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When disclaim is unavailable, _spawn_helper returns a real Popen."""
    monkeypatch.setattr(helper_client, "_DISCLAIM", None)
    proc = helper_client._spawn_helper(["/bin/echo", "via-popen"])
    try:
        assert isinstance(proc, subprocess.Popen)
        out, err = proc.communicate(timeout=5)
        assert out.strip() == "via-popen"
        assert proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_iter_records_routes_through_spawn_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """iter_records must spawn via _spawn_helper, not subprocess.Popen."""
    from accountpilot.plugins.imessage import helper_client as hc

    # The package conftest autopatches helper_client.iter_records to a
    # SQLite stub. Restore the real one so this test exercises the
    # production code path.
    monkeypatch.setattr(hc, "iter_records", _real_iter_records)

    calls: list[list[str]] = []

    class FakeProc:
        stdout = iter([])
        stderr = type("E", (), {"read": lambda self: ""})()

        def wait(self) -> int:
            return 0

        def kill(self) -> None:
            pass

    def fake_spawn(args: list[str]) -> FakeProc:
        calls.append(args)
        return FakeProc()

    monkeypatch.setattr(hc, "_spawn_helper", fake_spawn)
    list(hc.iter_records(since_ns=42, helper_path=os.fspath("/tmp/fake-helper")))

    assert len(calls) == 1
    assert calls[0][0] == "/tmp/fake-helper"
    assert "read-imessages" in calls[0]
    assert "--since-ns" in calls[0]
    assert "42" in calls[0]


# Bind a reference to the un-patched iter_records *at import time*, before
# any conftest autouse fixture has had a chance to swap it out.
_real_iter_records = helper_client.iter_records
