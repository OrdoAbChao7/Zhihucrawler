"""Exercise real CustomTkinter widgets without opening a browser or running a crawl."""
from types import SimpleNamespace
import tkinter as tk

import customtkinter as ctk
import pytest

from zhihu_app.config.settings import AppSettings
from zhihu_app.gui.app import ZhihuApp


@pytest.fixture(scope="module")
def gui_app():
    try:
        root = ctk.CTk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("zhihu_app.gui.app.ctk.CTk", lambda: root)
        try:
            yield ZhihuApp(AppSettings.defaults())
        finally:
            root.destroy()


@pytest.fixture
def app(gui_app, tmp_path, monkeypatch):
    monkeypatch.setattr("zhihu_app.gui.app.messagebox.showerror", lambda *args: None)
    gui_app.settings.output_dir = tmp_path
    gui_app._set_activity("idle")
    gui_app.vars["target"].set("")
    return gui_app


def states(app):
    return tuple(button.cget("state") for button in (app.btn_start, app.btn_login, app.btn_stop))


def test_task_buttons_follow_success_and_cancellation(app, monkeypatch):
    submitted = []
    monkeypatch.setattr(app.runner, "submit", submitted.append)
    app.vars["target"].set("test")
    assert states(app) == ("normal", "normal", "disabled")
    app._start()
    assert len(submitted) == 1
    assert states(app) == ("disabled", "disabled", "normal")
    app._cancel()
    assert states(app) == ("disabled", "disabled", "disabled")
    app._finished("cancelled")
    assert states(app) == ("normal", "normal", "disabled")


def test_task_failure_restores_buttons(app, monkeypatch):
    monkeypatch.setattr(app.runner, "submit", lambda task: None)
    app.vars["target"].set("test")
    app._start()
    app._error(RuntimeError("worker failed"))
    assert states(app) == ("normal", "normal", "disabled")


def test_invalid_form_keeps_buttons_idle(app):
    app._start()
    assert states(app) == ("normal", "normal", "disabled")


def test_login_thread_start_failure_restores_buttons(app, monkeypatch):
    def fail():
        raise RuntimeError("cannot start thread")

    monkeypatch.setattr("zhihu_app.gui.app.threading.Thread", lambda **kwargs: SimpleNamespace(start=fail))
    app._login()
    assert states(app) == ("normal", "normal", "disabled")


@pytest.mark.parametrize("succeeds", [True, False])
def test_login_blocks_collection_and_recovers(app, monkeypatch, succeeds):
    threads = []
    monkeypatch.setattr("zhihu_app.gui.app.threading.Thread", lambda **kwargs: threads.append(kwargs) or SimpleNamespace(start=lambda: None))
    app._login()
    app._login()
    app._start()
    assert len(threads) == 1
    assert states(app) == ("disabled", "disabled", "disabled")
    if succeeds:
        app._login_succeeded(object())
    else:
        app._error(RuntimeError("login failed"))
    assert states(app) == ("normal", "normal", "disabled")
