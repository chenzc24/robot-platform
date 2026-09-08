from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path


APP_NAME = "线稿预处理与笔触审核工具"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root()


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_url(url: str, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - error text is reported below
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"服务未能按时启动：{url}（{last_error}）")


def model_executable() -> Path:
    return runtime_root() / "model-service" / "StrokeModelService.exe"


def configure_bundled_model_repository() -> Path | None:
    """Prefer the weights shipped next to the companion executable.

    A source checkout without bundled weights keeps the existing environment or
    Hugging Face behavior. A packaged build therefore works offline while local
    development remains configurable.
    """

    repository = model_executable().parent / "models"
    if not repository.is_dir():
        return None
    os.environ["LINEART_MODEL_REPOSITORY"] = str(repository)
    return repository


def start_model_service(port: int, log_file) -> subprocess.Popen[bytes] | None:
    executable = model_executable()
    if not executable.is_file():
        return None
    process = subprocess.Popen(
        [str(executable), "--host", "127.0.0.1", "--port", str(port)],
        cwd=executable.parent,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    try:
        wait_for_url(f"http://127.0.0.1:{port}/api/health", timeout_seconds=60)
    except Exception:
        process.terminate()
        process.wait(timeout=10)
        return None
    return process


def import_backend_app():
    backend_dir = project_root() / "backend"
    if not getattr(sys, "frozen", False) and str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from app.main import app

    return app


def backend_config(app, port: int):
    import uvicorn

    # PyInstaller 的 windowed/console=False 程序没有 stdout/stderr。Uvicorn
    # 默认 LOGGING_CONFIG 会在 DefaultFormatter 初始化时调用
    # sys.stderr.isatty()，从而让便携版在真正启动 WebView 前崩溃。
    # 桌面版已有独立的 desktop.log / desktop-crash.log，因此关闭 Uvicorn
    # 的控制台日志配置最安全；开发服务器仍继续使用自己的日志配置。
    return uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_level="warning",
        log_config=None,
    )


def run_backend(app, port: int):
    import uvicorn

    config = backend_config(app, port)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="stroke-review-api", daemon=True)
    thread.start()
    return server, thread


def configure_webview(webview_module) -> None:
    # pywebview disables downloads by default. On Windows/WebView2 that causes
    # every <a download> export to be cancelled before a destination is chosen.
    # Enabling downloads makes pywebview show the native Save As dialog and
    # preserves the browser build's existing Blob-based export implementation.
    webview_module.settings["ALLOW_DOWNLOADS"] = True


def log_directory() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    location = base / "StrokeReview" / "logs"
    location.mkdir(parents=True, exist_ok=True)
    return location


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--no-model", action="store_true")
    args = parser.parse_args()

    backend_port = reserve_port()
    model_port = reserve_port()
    os.environ["LINEART_LOCAL_SERVICE_URL"] = f"http://127.0.0.1:{model_port}"
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    configure_bundled_model_repository()

    model_process: subprocess.Popen[bytes] | None = None
    log_path = log_directory() / "desktop.log"
    with log_path.open("ab", buffering=0) as log_file:
        if not args.no_model:
            model_process = start_model_service(model_port, log_file)
            if model_executable().is_file() and model_process is None:
                raise RuntimeError(
                    "内置 CNN 模型服务启动失败；请查看 desktop.log 获取详细原因。"
                )

        server = None
        thread = None
        try:
            app = import_backend_app()
            server, thread = run_backend(app, backend_port)
            url = f"http://127.0.0.1:{backend_port}"
            wait_for_url(f"{url}/api/health")
            wait_for_url(url)
            if args.smoke_test:
                return 0

            import webview

            configure_webview(webview)
            webview.create_window(
                APP_NAME,
                url,
                width=1440,
                height=920,
                min_size=(960, 640),
            )
            webview.start(private_mode=False)
            return 0
        finally:
            if server is not None:
                server.should_exit = True
            if thread is not None:
                thread.join(timeout=10)
            stop_process(model_process)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        crash_log = log_directory() / "desktop-crash.log"
        crash_log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
