"""The eyes layer: every failure must say what to install, never traceback."""
import json
import os
import sys
import time

import pytest

from deskmark.look import LookError, ask, available_tools, capture
from deskmark.look.screen import active_window
from deskmark.look import understand


# --- capture ---

def test_capture_says_what_to_install_when_nothing_works(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("deskmark.look.screen._has_pil", lambda: False)

    with pytest.raises(LookError) as excinfo:
        capture()
    message = str(excinfo.value)
    assert "no working screenshot tool" in message
    assert "scrot" in message          # the hint, not a bare OSError


def test_capture_prefers_grim_on_wayland(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setattr("deskmark.look.screen._has_pil", lambda: False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "grim" else None)

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        open(argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr("deskmark.look.screen._run", lambda argv: (calls.append(argv), open(argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + b"0" * 32), "")[2])

    target = str(tmp_path / "shot.png")
    result = capture(target)
    assert result.method == "grim"
    assert calls and calls[0][0] == "grim"
    assert os.path.getsize(result.path) > 0


def test_capture_reports_attempts_that_found_a_tool_but_failed(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr("deskmark.look.screen._has_pil", lambda: False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/import" if name == "import" else None)

    def boom(argv):
        raise LookError("import failed: unable to open X display")

    monkeypatch.setattr("deskmark.look.screen._run", boom)
    with pytest.raises(LookError) as excinfo:
        capture(str(tmp_path / "x.png"))
    assert "unable to open X display" in str(excinfo.value)
    assert "hint" in str(excinfo.value)


def test_available_tools_is_a_list_even_on_a_bare_machine(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("deskmark.look.screen._has_pil", lambda: False)
    assert available_tools() == []


# --- active window ---

def test_active_window_reads_hyprctl_json(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/hyprctl" if name == "hyprctl" else None)
    monkeypatch.setattr(
        "deskmark.look.screen._run",
        lambda argv: json.dumps({"class": "kitty", "title": "vim ~/api/server.py"}),
    )
    ref = active_window()
    assert ref.app == "kitty"
    assert ref.title == "vim ~/api/server.py"
    assert ref.method == "hyprctl"
    assert "kitty" in ref.describe()


def test_active_window_finds_the_focused_sway_node(monkeypatch):
    tree = {"nodes": [{"focused": False, "pid": 1, "name": "a"},
                      {"nodes": [{"focused": True, "pid": 42, "name": "b.py", "app_id": "code"}],
                       "floating_nodes": []}],
            "floating_nodes": []}
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/swaymsg" if name == "swaymsg" else None)
    monkeypatch.setattr("deskmark.look.screen._run", lambda argv: json.dumps(tree))
    ref = active_window()
    assert ref.app == "code" and ref.title == "b.py"


def test_active_window_explains_itself_when_nothing_is_available(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(LookError) as excinfo:
        active_window()
    assert "hyprctl" in str(excinfo.value)


# --- asking a model ---

def test_ask_without_a_key_names_the_variables(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LookError) as excinfo:
        ask("what is this?")
    assert "GEMINI_API_KEY" in str(excinfo.value)


def test_gemini_request_keeps_the_key_out_of_the_body(monkeypatch, png_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["headers"] = dict(request.headers)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [{"text": "a terminal, mid-edit"}]}}]}).encode()

        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    answer = ask("what is this?", image=png_file)
    assert answer.text == "a terminal, mid-edit"
    assert answer.provider == "gemini"
    assert "key=test-key" in captured["url"]
    assert "test-key" not in json.dumps(captured["body"])
    parts = captured["body"]["contents"][0]["parts"]
    assert parts[1]["inline_data"]["mime_type"] == "image/png"
    assert parts[1]["inline_data"]["data"]


def test_openai_uses_a_data_url_and_a_bearer_header(monkeypatch, png_file):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "a code editor"}}]}).encode()

        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    answer = ask("describe", image=png_file, provider="openai")
    assert answer.text == "a code editor"
    image_part = captured["body"]["messages"][0]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert any(value == "Bearer sk-test" for value in captured["headers"].values())


def test_anthropic_sends_the_version_header(monkeypatch, png_file):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"content": [{"text": "a spreadsheet"}]}).encode()

        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    answer = ask("describe", image=png_file, provider="anthropic")
    assert answer.text == "a spreadsheet"
    assert captured["body"]["messages"][0]["content"][0]["source"]["type"] == "base64"
    assert any("2023-06-01" in value for value in captured["headers"].values())


def test_ask_refuses_a_missing_or_enormous_image(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(LookError):
        ask("q", image=str(tmp_path / "nope.png"))

    big = tmp_path / "big.png"
    big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (8 * 1024 * 1024 + 10))
    with pytest.raises(LookError) as excinfo:
        ask("q", image=str(big))
    assert "too large" in str(excinfo.value)


def test_http_error_is_reported_without_leaking_the_key(monkeypatch, png_file):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-value")
    import urllib.error

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many Requests", {}, None
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(LookError) as excinfo:
        ask("q", image=png_file)
    assert "429" in str(excinfo.value)
    assert "secret-key-value" not in str(excinfo.value)


def test_unknown_provider_is_refused(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with pytest.raises(LookError) as excinfo:
        ask("q", provider="gpt4-all")
    assert "unknown provider" in str(excinfo.value)
