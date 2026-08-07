# -*- coding: utf-8 -*-
"""Desktop launcher for the self-media console.

Called by open_console.bat. Does three things:
1. Probes whether the console server is already running on port 8765.
2. If not running, launches console_server.py in a background process.
3. Opens the default browser to http://127.0.0.1:8765/.

Pure Python standard library, no third-party deps.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "console_server.py"
DEFAULT_URL = "http://127.0.0.1:8765"
DEFAULT_PORT = 8765
PROBE_PATH = "/api/meta"


def port_listening(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> bool:
    """Return True if something is already listening on (host, port)."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def http_probe(url: str, timeout: float = 2.0) -> bool:
    """Return True if GET url returns HTTP 200."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return False


def find_python() -> str:
    """Find a usable Python interpreter path."""
    # Try current sys.executable first (we are already running under Python)
    return sys.executable


def start_server(port: int) -> subprocess.Popen:
    """Launch console_server.py as a background process. Returns the Popen handle."""
    python = find_python()
    cmd = [python, str(SERVER_SCRIPT), "--port", str(port), "--host", "127.0.0.1"]
    creationflags = 0
    if os.name == "nt":
        # CREATE_NO_WINDOW = 0x08000000, minimize the window
        CREATE_NO_WINDOW = 0x08000000
        creationflags = CREATE_NO_WINDOW
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def wait_for_server(url: str, max_wait: float = 12.0) -> bool:
    """Poll the health endpoint until it returns 200 or timeout."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if http_probe(url + PROBE_PATH, timeout=1.0):
            return True
        time.sleep(0.3)
    return False


def open_browser(url: str) -> None:
    """Open the default web browser to url. Uses os.startfile on Windows
    for reliability over webbrowser module."""
    if os.name == "nt":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    webbrowser.open(url)


def main() -> int:
    url = DEFAULT_URL
    port = DEFAULT_PORT

    print(f"[console] Probing {url}{PROBE_PATH} ...")

    # 1) If server is already up, just open the browser
    if port_listening(port=port) and http_probe(url + PROBE_PATH):
        print("[console] Server is already running. Opening browser...")
        open_browser(url)
        return 0

    # 2) Port occupied but not by our server - warn
    if port_listening(port=port):
        print(f"[warn] Port {port} is occupied by another process but not responding.")
        print("[warn] Please close the conflicting program or change the port.")
        input("Press Enter to exit...")
        return 1

    # 3) Start the server
    print("[console] Port is free. Starting server...")
    if not SERVER_SCRIPT.exists():
        print(f"[error] Server script not found: {SERVER_SCRIPT}")
        input("Press Enter to exit...")
        return 2

    proc = start_server(port)
    print(f"[console] Server started (PID {proc.pid}). Waiting for it to be ready...")

    # 4) Wait for readiness
    if wait_for_server(url, max_wait=15.0):
        print("[console] Server is ready. Opening browser...")
        open_browser(url)
        return 0
    else:
        print("[error] Server did not become ready in time.")
        print(f"[hint] You can manually open {url} in your browser.")
        print(f"[hint] Server process (PID {proc.pid}) may still be starting up.")
        # Try one more time with a longer wait
        print("[console] Giving it one more try (10s)...")
        if wait_for_server(url, max_wait=10.0):
            print("[console] Server is ready now. Opening browser...")
            open_browser(url)
            return 0
        input("Press Enter to exit...")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
