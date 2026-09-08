from __future__ import annotations

import socket
import sys
import os
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher import (
    backend_config,
    configure_bundled_model_repository,
    configure_webview,
    model_executable,
    reserve_port,
    runtime_root,
)


def test_reserve_port_returns_a_bindable_local_port() -> None:
    port = reserve_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", port))


def test_model_companion_location_is_inside_runtime_folder() -> None:
    expected = runtime_root() / "model-service" / "StrokeModelService.exe"
    assert model_executable() == expected


def test_bundled_weights_override_remote_repository(monkeypatch, tmp_path) -> None:
    import launcher

    executable = tmp_path / "model-service" / "StrokeModelService.exe"
    (executable.parent / "models").mkdir(parents=True)
    monkeypatch.setattr(launcher, "model_executable", lambda: executable)
    monkeypatch.setenv("LINEART_MODEL_REPOSITORY", "remote/repository")

    repository = configure_bundled_model_repository()

    assert repository == executable.parent / "models"
    assert os.environ["LINEART_MODEL_REPOSITORY"] == str(repository)


def test_backend_config_supports_windowed_build_without_console(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    config = backend_config(object(), 8123)

    assert config.log_config is None
    assert config.access_log is False


def test_configure_webview_enables_native_download_dialog() -> None:
    webview = SimpleNamespace(settings={"ALLOW_DOWNLOADS": False})

    configure_webview(webview)

    assert webview.settings["ALLOW_DOWNLOADS"] is True
