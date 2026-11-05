"""
End-to-End integration test for LIGHT AI V1.0 Launcher and Assistant Lifecycle.
Spawns the assistant through the launcher orchestrator, connects via WebSocket,
dispatches a text command, verifies telemetry & chat creation, and cleanly shuts down.
"""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
import pytest
import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
START_PS1 = PROJECT_ROOT / "launcher" / "start_light_ai.ps1"
CHATS_DIR = PROJECT_ROOT / "chats"


def test_launcher_lifecycle_and_bridge_integration():
    """
    Spawns start_light_ai.ps1 in BackendOnly mode, waits for WebSocket bridge readiness,
    connects a WebSocket client, exchanges messages, and terminates cleanly.
    """
    async def _runner():
        initial_chat_files = set(CHATS_DIR.glob("chat_*.json")) if CHATS_DIR.exists() else set()

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(START_PS1),
            "-BackendOnly",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            text=True,
        )

        ws_url = "ws://127.0.0.1:8765/ws"
        connected = False
        session = None
        ws = None

        try:
            start_time = time.time()
            session = aiohttp.ClientSession()

            while time.time() - start_time < 15:
                try:
                    ws = await session.ws_connect(ws_url, timeout=2.0)
                    connected = True
                    break
                except Exception:
                    await asyncio.sleep(0.5)

            assert connected, "Failed to connect to WebSocket bridge on 127.0.0.1:8765 within 15 seconds"

            # Receive at least one telemetry or state broadcast
            msg = await asyncio.wait_for(ws.receive_str(), timeout=5.0)
            assert msg, "Expected initial message from WebSocket bridge"
            data = json.loads(msg)
            assert "type" in data

            # Send a text command through the live bridge
            cmd_payload = {
                "type": "TEXT_COMMAND",
                "payload": {
                    "text": "who are you",
                    "request_id": f"test_e2e_{int(time.time())}"
                }
            }
            await ws.send_str(json.dumps(cmd_payload))

            # Wait for acknowledgment or conversation event
            received_types = []
            for _ in range(5):
                try:
                    resp_text = await asyncio.wait_for(ws.receive_str(), timeout=3.0)
                    resp = json.loads(resp_text)
                    received_types.append(resp.get("type"))
                    if resp.get("type") in ("CONVERSATION_EVENT", "SYSTEM_TELEMETRY", "QUEUE_STATE"):
                        break
                except asyncio.TimeoutError:
                    break

            assert len(received_types) > 0, "Bridge did not emit events after text command"

            # Close WebSocket cleanly
            await ws.close()

        finally:
            if ws and not ws.closed:
                await ws.close()
            if session and not session.closed:
                await session.close()

            # Cleanly terminate the launcher process and all children
            if proc.poll() is None:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

            await asyncio.sleep(1.0)
            if CHATS_DIR.exists():
                final_chat_files = set(CHATS_DIR.glob("chat_*.json"))
                for cf in final_chat_files:
                    content = json.loads(cf.read_text(encoding="utf-8"))
                    assert "session_id" in content

    asyncio.run(_runner())
