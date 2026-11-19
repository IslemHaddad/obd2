#!/usr/bin/env python3
"""Capture the Bluetooth traffic between the official ThinkCar app (on an Android phone) and a ThinkDiag dongle.

The phone does the logging (Android "Bluetooth HCI snoop log"); this script, run on the PC with the phone on USB:
  1. checks the phone is connected over adb,
  2. switches the snoop log on (or tells you how, if the phone doesn't allow it from the PC),
  3. records a timestamped marker for every action you do in the ThinkCar app,
  4. pulls a bug report, keeps ONLY the Bluetooth log, and deletes the rest (it contains personal phone data).

Output: tools/btcapture/out/<date>/btsnoop_hci.log + markers.txt  -> send those two files.

Needs adb:  Linux: sudo apt install adb   ·   Windows/macOS: Google "Android SDK platform-tools".
On the phone: Developer options ON + USB debugging ON (Settings → About phone → tap Build number 7 times).
"""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ACTIONS = [
    "Open the ThinkCar app and CONNECT to the ThinkDiag (wait until it says connected)",
    "Read the VIN / vehicle info (or start auto-detect of the car)",
    "Open ONE module (e.g. Air Conditioning) and READ FAULT CODES",
    "CLEAR the fault codes of that same module (skip with 's' if the app won't)",
    "Read the fault codes of that module again",
    "Open live data of the engine for ~10 seconds (skip with 's' if not available)",
    "Disconnect / close the ThinkCar app",
]


def adb(*args: str, timeout: float = 30, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout, check=check)


def sh(cmd: str, timeout: float = 15) -> str:
    return adb("shell", cmd, timeout=timeout).stdout.strip()


def phone_time() -> str:
    return sh("date +%Y-%m-%dT%H:%M:%S.%N") or dt.datetime.now().isoformat()


def ask(msg: str) -> str:
    try:
        return input(msg).strip().lower()
    except EOFError:
        return ""


def main() -> int:
    if not shutil.which("adb"):
        print("adb is not installed.\n  Linux:   sudo apt install adb\n  Windows: download 'SDK Platform-Tools' from Google, unzip, run this from that folder.")
        return 1

    print("Looking for the phone…")
    adb("start-server", timeout=20)
    devs = [l.split() for l in adb("devices").stdout.splitlines()[1:] if l.strip()]
    if not devs:
        print("No phone found. Plug it in by USB, turn on USB debugging, and accept the 'Allow USB debugging?' prompt.")
        return 1
    if any(d[1] == "unauthorized" for d in devs):
        print("The phone is asking 'Allow USB debugging?' — tap Allow (tick 'Always allow'), then run this again.")
        return 1
    model = sh("getprop ro.product.model")
    android = sh("getprop ro.build.version.release")
    print(f"Phone: {model} (Android {android})")

    # --- switch the Bluetooth snoop log on
    mode = sh("getprop persist.bluetooth.btsnooplogmode")
    if mode != "full":
        sh("setprop persist.bluetooth.btsnooplogmode full")
        sh("settings put secure bluetooth_hci_log 1")
        mode = sh("getprop persist.bluetooth.btsnooplogmode")
    if mode != "full":
        print("\nThe phone didn't let the PC switch the log on. Do it by hand:\n"
              "  Settings → System → Developer options → 'Enable Bluetooth HCI snoop log' → Enabled (or 'Full')\n")
        ask("Press Enter when done… ")
    print("Restarting Bluetooth so the log starts fresh…")
    for off, on in (("cmd bluetooth_manager disable", "cmd bluetooth_manager enable"),
                    ("svc bluetooth disable", "svc bluetooth enable")):
        r = adb("shell", off, timeout=15)
        if r.returncode == 0 and "rror" not in r.stdout + r.stderr and "not found" not in r.stdout + r.stderr:
            time.sleep(3)
            adb("shell", on, timeout=15)
            time.sleep(4)
            break
    else:
        ask("Couldn't restart Bluetooth from the PC — turn Bluetooth OFF and ON on the phone, then press Enter… ")

    # --- guided actions with timestamps
    markers = [f"{phone_time()}  START  phone={model} android={android}"]
    print("\nNow use the ThinkCar app on the phone. Press Enter AFTER each step (s = skipped, q = stop early).\n")
    for i, a in enumerate(ACTIONS, 1):
        before = phone_time()
        r = ask(f"[{i}/{len(ACTIONS)}] {a}\n      → Enter when done: ")
        after = phone_time()
        if r == "q":
            markers.append(f"{after}  STOPPED")
            break
        markers.append(f"{before} .. {after}  STEP {i} {'SKIPPED ' if r == 's' else ''}{a}")
        note = ask("      anything to note (what the app showed, fault codes, VIN…)? ")
        if note:
            markers.append(f"      note: {note}")
    markers.append(f"{phone_time()}  END")

    # --- pull only the Bluetooth log
    out = Path(__file__).resolve().parent / "out" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "markers.txt").write_text("\n".join(markers) + "\n")
    print("\nCollecting the Bluetooth log from the phone (bug report — takes 1–3 minutes)…")
    with tempfile.TemporaryDirectory() as tmp:
        z = Path(tmp) / "bug.zip"
        r = adb("bugreport", str(z), timeout=600)
        if not z.exists():
            # older adb/phones write the zip under another name in the target folder
            zips = list(Path(tmp).glob("*.zip"))
            z = zips[0] if zips else z
        if not z.exists():
            print("Bug report failed:", r.stderr[-400:])
            return 1
        found = 0
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if "btsnoop" in n.lower() or n.lower().endswith(".cfa"):
                    target = out / Path(n).name
                    if target.exists():
                        target = out / f"{found}_{Path(n).name}"
                    target.write_bytes(zf.read(n))
                    found += 1
        # the zip (with all personal phone data) is deleted with the temp folder here
    if not found:
        print("No Bluetooth log inside the bug report. On this phone the snoop log may need 'Full' mode, "
              "or Bluetooth must be restarted after enabling it. Try again after toggling it by hand.")
        return 1
    print(f"\nDone. Send me these files:\n  {out}")
    for p in sorted(out.iterdir()):
        print(f"   - {p.name}  ({p.stat().st_size:,} bytes)")
    print("\nYou can switch 'Bluetooth HCI snoop log' off again in Developer options.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
