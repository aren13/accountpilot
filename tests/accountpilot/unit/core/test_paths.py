from __future__ import annotations

from typing import TYPE_CHECKING

from accountpilot.core import paths

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_data_dir_uses_platformdirs_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACCOUNTPILOT_DATA_DIR", raising=False)
    p = paths.data_dir()
    # The platformdirs default always ends in "accountpilot".
    assert p.name == "accountpilot"


def test_data_dir_honors_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_config_dir_honors_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_CONFIG_DIR", str(tmp_path))
    assert paths.config_dir() == tmp_path


def test_log_dir_honors_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_LOG_DIR", str(tmp_path))
    assert paths.log_dir() == tmp_path


def test_cache_dir_honors_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_CACHE_DIR", str(tmp_path))
    assert paths.cache_dir() == tmp_path


def test_db_path_lives_under_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(tmp_path))
    assert paths.db_path() == tmp_path / "accountpilot.db"


def test_attachments_dir_lives_under_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(tmp_path))
    assert paths.attachments_dir() == tmp_path / "attachments"


def test_config_path_lives_under_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_CONFIG_DIR", str(tmp_path))
    assert paths.config_path() == tmp_path / "config.yaml"


def test_config_path_default_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACCOUNTPILOT_CONFIG_DIR", raising=False)
    p = paths.config_path()
    assert p.name == "config.yaml"


def test_secrets_dir_lives_under_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCOUNTPILOT_DATA_DIR", str(tmp_path))
    assert paths.secrets_dir() == tmp_path / "secrets"
