#!/usr/bin/env python3
"""
OTA update script for airplay-esp32 (ESP32-S3).

Builds the project, then pushes firmware + web UI to every device.
Edit DEVICE_IPS below to match your devices.

Usage:
    python3 scripts/ota_update.py            # build + update all devices
    python3 scripts/ota_update.py --no-build # skip build, use existing artifacts
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configure your devices here
# ---------------------------------------------------------------------------
DEVICE_IPS = [
    "192.168.1.104", # basement speaker
    "192.168.1.245", # living room speaker
    "192.168.1.154", # garage speaker
]
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILD_ENV = "esp32s3"
FIRMWARE_BIN = PROJECT_ROOT / ".pio" / "build" / BUILD_ENV / "firmware.bin"
WEB_UI_DIR = PROJECT_ROOT / "data" / "www"

# MIME types for web UI files
MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

TIMEOUT_WEB = 30   # seconds for each web file upload
TIMEOUT_OTA = 300  # seconds for firmware flash (device reboots after)


def build():
    print(f"\n{'='*60}")
    print(f"Building {BUILD_ENV}...")
    print(f"{'='*60}\n")
    result = subprocess.run(
        ["pio", "run", "-e", BUILD_ENV],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        print("\nBuild failed. Aborting.")
        sys.exit(1)
    print(f"\nBuild OK -> {FIRMWARE_BIN}")


def upload_web_ui(ip: str) -> list[str]:
    """Upload all files from data/www/ to the device. Returns list of error messages."""
    errors = []
    files = sorted(WEB_UI_DIR.iterdir()) if WEB_UI_DIR.exists() else []
    if not files:
        print(f"  [{ip}] WARNING: no web UI files found in {WEB_UI_DIR}")
        return errors

    for f in files:
        if not f.is_file():
            continue
        spiffs_path = f"/spiffs/www/{f.name}"
        mime = MIME_TYPES.get(f.suffix.lower(), "application/octet-stream")
        url = f"http://{ip}/api/fs/upload?path={spiffs_path}"
        try:
            with open(f, "rb") as fh:
                data = fh.read()
            resp = requests.post(
                url,
                data=data,
                headers={"Content-Type": mime},
                timeout=TIMEOUT_WEB,
            )
            if resp.status_code == 200:
                print(f"  [{ip}] Web UI: {f.name} OK ({len(data)} bytes)")
            else:
                msg = f"  [{ip}] Web UI: {f.name} HTTP {resp.status_code} - {resp.text[:120]}"
                print(msg)
                errors.append(msg)
        except Exception as e:
            msg = f"  [{ip}] Web UI: {f.name} FAILED - {e}"
            print(msg)
            errors.append(msg)

    return errors


def upload_firmware(ip: str) -> list[str]:
    """POST firmware.bin to the OTA endpoint. Device reboots on success."""
    errors = []
    url = f"http://{ip}/api/ota/update"
    try:
        size = FIRMWARE_BIN.stat().st_size
        print(f"  [{ip}] Firmware: uploading {size / 1024:.1f} KB...")
        with open(FIRMWARE_BIN, "rb") as fh:
            resp = requests.post(
                url,
                data=fh,
                headers={"Content-Type": "application/octet-stream"},
                timeout=TIMEOUT_OTA,
            )
        if resp.status_code == 200:
            print(f"  [{ip}] Firmware: OK - device is rebooting")
        else:
            msg = f"  [{ip}] Firmware: HTTP {resp.status_code} - {resp.text[:120]}"
            print(msg)
            errors.append(msg)
    except Exception as e:
        msg = f"  [{ip}] Firmware: FAILED - {e}"
        print(msg)
        errors.append(msg)
    return errors


def update_device(ip: str) -> list[str]:
    print(f"\n--- {ip} ---")
    # Web UI first (no restart), then firmware (triggers restart).
    # SPIFFS survives the reboot so both updates land on the new firmware.
    errors = upload_web_ui(ip)
    errors += upload_firmware(ip)
    return errors


def main():
    parser = argparse.ArgumentParser(description="Build and OTA-update airplay-esp32 devices")
    parser.add_argument("--no-build", action="store_true", help="Skip build step")
    args = parser.parse_args()

    if not DEVICE_IPS:
        print("No devices configured. Edit DEVICE_IPS in this script.")
        sys.exit(1)

    if not args.no_build:
        build()

    if not FIRMWARE_BIN.exists():
        print(f"Firmware not found: {FIRMWARE_BIN}")
        print("Run without --no-build or build manually first.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Updating {len(DEVICE_IPS)} device(s)...")
    print(f"{'='*60}")

    all_errors: dict[str, list[str]] = {}
    for ip in DEVICE_IPS:
        errs = update_device(ip)
        if errs:
            all_errors[ip] = errs

    print(f"\n{'='*60}")
    if not all_errors:
        print(f"All {len(DEVICE_IPS)} device(s) updated successfully.")
    else:
        ok = len(DEVICE_IPS) - len(all_errors)
        print(f"Done: {ok}/{len(DEVICE_IPS)} succeeded. Failures:")
        for ip, errs in all_errors.items():
            for e in errs:
                print(f"  {e}")
        sys.exit(1)
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
