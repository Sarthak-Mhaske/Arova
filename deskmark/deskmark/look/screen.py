"""Screen capture and the active window, using whatever this machine provides.

No dependencies, no daemon, no continuous capture. One screenshot is taken when
a human asks for one, and it is a file on disk that the caller owns.

The rule for every function here: if the machine cannot do it, say what to
install instead of raising a bare ``FileNotFoundError``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deskmark.look.errors import LookError

TIMEOUT = 10

# Ordered per platform: the first tool that exists on PATH wins. grim is first
# on Wayland because it is the only one that works on wlroots compositors
# (Hyprland, sway) without a portal round-trip.
TOOLS = {
    "darwin": ["screencapture"],
    "linux-wayland": ["grim", "grimblast", "gnome-screenshot", "spectacle", "flameshot"],
    "linux-x11": ["scrot", "import", "gnome-screenshot", "maim"],
    "windows": ["powershell"],
}

INSTALL_HINT = {
    "linux-wayland": "install grim (Arch: pacman -S grim; Debian: apt install grim), or flameshot",
    "linux-x11": "install scrot (Arch: pacman -S scrot; Debian: apt install scrot), or imagemagick for `import`",
    "darwin": "screencapture ships with macOS; check `xcode-select --install`",
    "windows": "PowerShell ships with Windows 10 and later",
}


def _platform_key() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return "linux-wayland"
        return "linux-x11"
    return "linux-x11"


def available_tools() -> List[str]:
    """Screenshot tools present on PATH for this session."""
    found = [tool for tool in TOOLS.get(_platform_key(), []) if shutil.which(tool)]
    if _has_pil():
        found.insert(0, "pillow")
    return found


def _has_pil() -> bool:
    try:
        import PIL.ImageGrab  # noqa: F401
    except Exception:
        return False
    return True


@dataclass
class Capture:
    path: str
    method: str
    bytes: int = 0
    seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "method": self.method, "bytes": self.bytes, "seconds": round(self.seconds, 3)}


@dataclass
class WindowRef:
    app: str = ""
    title: str = ""
    method: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"app": self.app, "title": self.title, "method": self.method}

    def describe(self) -> str:
        label = " — ".join(part for part in (self.app, self.title) if part)
        return label or "an unnamed window"


def _short(text: str, limit: int = 60) -> str:
    line = (text or "").strip().splitlines()[0] if text else ""
    line = line.replace("`", "").replace("'", "")
    return line[:limit] + ("…" if len(line) > limit else "")


def _run(argv: List[str]) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError as exc:
        raise LookError(f"{argv[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise LookError(f"{argv[0]} did not finish within {TIMEOUT}s") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise LookError(f"{argv[0]} failed: {detail[0] if detail else 'exit ' + str(result.returncode)}")
    return result.stdout.strip()


def capture(path: Optional[str] = None) -> Capture:
    """Take one screenshot and return where it landed and how it was taken."""
    target = path or os.path.join(tempfile.gettempdir(), "deskmark-look-%d.png" % int(time.time() * 1000))
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)

    started = time.time()
    method = ""
    tried: List[str] = []

    if _has_pil():
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab()
            image.save(target)
            method = "pillow"
        except Exception:
            method = ""

    if not method:
        key = _platform_key()
        for tool in TOOLS.get(key, []):
            if not shutil.which(tool):
                continue
            try:
                if tool == "screencapture":
                    _run([tool, "-x", target])
                elif tool == "grim":
                    _run([tool, target])
                elif tool == "grimblast":
                    _run([tool, "save", "screen", target])
                elif tool == "spectacle":
                    _run([tool, "-b", "-n", "-o", target])
                elif tool == "flameshot":
                    _run([tool, "full", "-p", target])
                elif tool == "import":
                    _run([tool, "-window", "root", target])
                elif tool == "powershell":
                    _powershell_screenshot(target)
                else:
                    _run([tool, target])
                if os.path.exists(target):
                    method = tool
                    break
                tried.append("%s (wrote nothing)" % tool)
            except LookError as exc:
                tried.append("%s (%s)" % (tool, _short(exc.message)))

    if not method or not os.path.exists(target):
        hint = INSTALL_HINT.get(_platform_key(), "install a screenshot tool")
        if tried:
            hint = "tried " + "; ".join(tried) + " — " + hint
        raise LookError("this machine has no working screenshot tool", hint=hint)

    size = os.path.getsize(target)
    if size == 0:
        raise LookError(f"{method} wrote an empty image to {target}")
    return Capture(path=target, method=method, bytes=size, seconds=time.time() - started)


def _powershell_screenshot(target: str) -> None:
    script = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
        "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($bmp);"
        "$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size);"
        "$bmp.Save('%s')" % target.replace("'", "''")
    )
    _run(["powershell", "-NoProfile", "-Command", script])


# ---------------------------------------------------------------------------
# the active window
# ---------------------------------------------------------------------------

def active_window() -> WindowRef:
    """Best-effort: which window has focus, and what is in it."""
    for probe in (_wayland_window, _x11_window, _macos_window, _windows_window):
        try:
            ref = probe()
        except LookError:
            ref = None
        if ref and (ref.app or ref.title):
            return ref
    raise LookError(
        "cannot tell which window is focused on this machine",
        hint="on Wayland install hyprctl (Hyprland) or swaymsg (sway); on X11 install xdotool; "
        "or pass --image explicitly instead",
    )


def _wayland_window() -> Optional[WindowRef]:
    if shutil.which("hyprctl"):
        try:
            data = json.loads(_run(["hyprctl", "activewindow", "-j"]) or "{}")
            if isinstance(data, dict) and (data.get("class") or data.get("title")):
                return WindowRef(app=str(data.get("class") or ""), title=str(data.get("title") or ""), method="hyprctl")
        except (LookError, ValueError):
            pass
    if shutil.which("swaymsg"):
        try:
            tree = json.loads(_run(["swaymsg", "-t", "get_tree", "-r"]) or "{}")
            node = _focused_node(tree)
            if node:
                return WindowRef(
                    app=str(node.get("app_id") or node.get("window_properties", {}).get("class") or ""),
                    title=str(node.get("name") or ""),
                    method="swaymsg",
                )
        except (LookError, ValueError):
            pass
    return None


def _focused_node(node: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(node, dict):
        return None
    if node.get("focused") and node.get("pid") is not None:
        return node
    for key in ("nodes", "floating_nodes"):
        for child in node.get(key) or []:
            found = _focused_node(child)
            if found:
                return found
    return None


def _x11_window() -> Optional[WindowRef]:
    if not shutil.which("xdotool"):
        return None
    try:
        title = _run(["xdotool", "getactivewindow", "getwindowname"])
        app = ""
        try:
            app = _run(["xdotool", "getactivewindow", "getwindowclassname"])
        except LookError:
            pass
        return WindowRef(app=app, title=title, method="xdotool")
    except LookError:
        return None


def _macos_window() -> Optional[WindowRef]:
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return None
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        return WindowRef(app=_run(["osascript", "-e", script]), method="osascript")
    except LookError:
        return None


def _windows_window() -> Optional[WindowRef]:
    if not sys.platform.startswith("win"):
        return None
    script = (
        "Add-Type @'\n"
        "using System;using System.Runtime.InteropServices;\n"
        "public class W{[DllImport(\"user32.dll\")]public static extern IntPtr GetForegroundWindow();"
        "[DllImport(\"user32.dll\")]public static extern int GetWindowText(IntPtr h,System.Text.StringBuilder s,int c);}\n"
        "'@;"
        "$h=[W]::GetForegroundWindow();$s=New-Object System.Text.StringBuilder 512;"
        "[void][W]::GetWindowText($h,$s,512);$s.ToString()"
    )
    try:
        title = _run(["powershell", "-NoProfile", "-Command", script])
        return WindowRef(title=title, method="powershell")
    except LookError:
        return None
