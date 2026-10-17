#!/usr/bin/env python3
"""Capture high-resolution screenshots of the Antigravity Quota Portal dashboard and developer views."""

import os
import shutil
import subprocess
import sys
import tempfile
import time

import httpx

PORT = 8089
BASE_URL = f"http://localhost:{PORT}"
IMAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../docs/images"))
CHROME_BIN = (
    shutil.which("google-chrome")
    or shutil.which("google-chrome-stable")
    or shutil.which("chromium")
    or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)

TARGET_SCREENSHOTS = [
    {
        "name": "portal_dashboard.png",
        "url": f"{BASE_URL}/",
        "desc": "Admin Dashboard (Users)",
    },
    {
        "name": "portal_quota_requests.png",
        "url": f"{BASE_URL}/#requests",
        "desc": "Admin Quota Increase Requests Governance Tab",
    },
    {
        "name": "portal_developer_self_service.png",
        "url": f"{BASE_URL}/#my-quota",
        "desc": "Developer Self-Service View (My Quota)",
    },
    {
        "name": "portal_developer_throttled.png",
        "url": f"{BASE_URL}/?as_user=infrasec@example.com#my-quota",
        "desc": "Throttled Developer View with Pending Quota Request",
    },
]


def capture():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    temp_profile_dir = tempfile.mkdtemp(prefix="chrome_portal_")

    # 1. Start demo portal server
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    env["USE_MOCK_SERVICES"] = "true"

    print(f"==> Launching demo portal server on {BASE_URL}...")
    server_proc = subprocess.Popen(
        [sys.executable, "scripts/run_local_demo.py"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Wait for portal health endpoint
        ready = False
        for _ in range(30):
            try:
                r = httpx.get(f"{BASE_URL}/api/health", timeout=1.0)
                if r.status_code == 200:
                    ready = True
                    print("✅ Portal server is running.")
                    break
            except Exception:
                time.sleep(0.3)

        if not ready:
            print("❌ Server failed to start.")
            sys.exit(1)

        # 2. Check for Chrome binary
        if not os.path.exists(CHROME_BIN):
            print(f"❌ Google Chrome binary not found at {CHROME_BIN}")
            sys.exit(1)

        print(f"==> Using Chrome binary: {CHROME_BIN}")

        # 3. Capture each view
        for target in TARGET_SCREENSHOTS:
            output_path = os.path.join(IMAGES_DIR, target["name"])
            print(f"==> Capturing {target['desc']} from {target['url']}...")

            cmd = [
                CHROME_BIN,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                f"--user-data-dir={temp_profile_dir}",
                f"--screenshot={output_path}",
                "--window-size=1440,960",
                "--virtual-time-budget=3500",
                target["url"],
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(output_path):
                    size_kb = os.path.getsize(output_path) / 1024
                    print(f"  🎉 Saved: {target['name']} ({size_kb:.1f} KB)")
                else:
                    print(f"  ⚠️ File was not created: {output_path}")
            except Exception as e:
                print(f"  ❌ Failed to capture {target['name']}: {e}")

    finally:
        print("==> Shutting down demo server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except Exception:
            server_proc.kill()

        if os.path.exists(temp_profile_dir):
            shutil.rmtree(temp_profile_dir, ignore_errors=True)


if __name__ == "__main__":
    capture()
