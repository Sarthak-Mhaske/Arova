"""Fixtures shared by every test module.

Kept in conftest rather than duplicated per file so that a module-level fixture
can never silently shadow another one (which is exactly how two history tests
broke during the look-layer work).
"""
import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKMARK_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def png_file(tmp_path):
    path = tmp_path / "screen.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return str(path)
