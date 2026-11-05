"""
Local WebSocket Bridge Server for LIGHT AI V1.0.
Hosts a secure, localhost-only WebSocket server on 127.0.0.1:8765 using aiohttp.
Broadcasts periodic telemetry and handles safe client communication without blocking the assistant.
"""

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional, Set

from aiohttp import web, WSMsgType

from core.bridge.schema import (
    BridgeMessageType,
    create_error_message,
    create_message,
    create_status_message,
    create_telemetry_message,
    create_text_command_ack_event,
    validate_incoming_message,
)
from core.bridge.telemetry import TelemetryCollector
from utils.logger import logger

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TELEMETRY_INTERVAL_SECONDS = 1.0


class WebSocketBridgeServer:
    """
    Secure local WebSocket bridge server.
    Binds strictly to 127.0.0.1:8765. Rejects any non-local connection attempts.
    Runs in its own background daemon thread with a dedicated asyncio event loop.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        telemetry_interval: float = TELEMETRY_INTERVAL_SECONDS,
        collector: Optional[TelemetryCollector] = None,
        music_player: Optional[Any] = None,
    ):
        # Strict security constraint: only local interface allowed
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                f"[BRIDGE SECURITY] Prohibited host '{host}'. "
                "Bridge server must bind strictly to local interface 127.0.0.1."
            )

        self._host = host
        self._port = port
        self._telemetry_interval = telemetry_interval
        self.collector = collector or TelemetryCollector()
        self._music_player = music_player
        if self._music_player and hasattr(self.collector, "set_music_player"):
            self.collector.set_music_player(self._music_player)

        self._server_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False
        self._started_event = threading.Event()
        self._startup_error: Optional[str] = None

        self._clients: Set[web.WebSocketResponse] = set()
        self._clients_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Returns True if the bridge server is currently running and listening."""
        return self._running and self._server_thread is not None and self._server_thread.is_alive()

    @property
    def client_count(self) -> int:
        """Returns the number of currently connected WebSocket clients."""
        with self._clients_lock:
            return len(self._clients)

    def set_music_player(self, player: Any) -> None:
        """Registers the authoritative MusicPlayer instance for commands and telemetry."""
        self._music_player = player
        if self.collector and hasattr(self.collector, "set_music_player"):
            self.collector.set_music_player(player)

    def set_gateway_client(self, client: Any) -> None:
        """Registers the active CoeGatewayClient instance for AI Core telemetry."""
        if self.collector and hasattr(self.collector, "set_gateway_client"):
            self.collector.set_gateway_client(client)

    def set_session_memory(self, memory: Any) -> None:
        """Registers the active SessionMemory instance for AI Core telemetry."""
        if self.collector and hasattr(self.collector, "set_session_memory"):
            self.collector.set_session_memory(memory)

    def set_assistant(self, assistant: Any) -> None:
        """Registers the active LightAssistant instance for microphone, voice commands, and AI telemetry."""
        self._assistant = assistant
        if self.collector and hasattr(self.collector, "set_assistant"):
            self.collector.set_assistant(assistant)
        if assistant:
            if hasattr(assistant, "gateway_client"):
                self.set_gateway_client(assistant.gateway_client)
            if hasattr(assistant, "session_memory"):
                self.set_session_memory(assistant.session_memory)

    def broadcast_ai_core_state(self, payload: Dict[str, Any], correlation_id: Optional[Any] = None) -> None:
        """Constructs and broadcasts an ai_core_state event to connected clients."""
        from core.bridge.schema import create_ai_core_state_event
        msg = create_ai_core_state_event(payload, correlation_id=correlation_id)
        self.broadcast_event(msg)

    def start(self) -> bool:
        """
        Starts the WebSocket server in a background daemon thread.
        Returns True if started successfully, False otherwise.
        """
        if self.is_running:
            logger.info("Local bridge server is already running.")
            return True

        self._running = True
        self._started_event.clear()
        self._startup_error = None

        self._server_thread = threading.Thread(
            target=self._run_server_thread,
            name="BridgeServerThread",
            daemon=True,
        )
        self._server_thread.start()

        # Wait up to 5 seconds for the server to bind and start
        if not self._started_event.wait(timeout=5.0):
            logger.error(f"Bridge server failed to start on {self._host}:{self._port}: Timeout waiting for server startup.")
            self.stop()
            return False

        if self._startup_error:
            logger.error(f"Bridge server failed to start on {self._host}:{self._port}: {self._startup_error}")
            self.stop()
            return False

        logger.info(f"Local bridge server successfully listening on ws://{self._host}:{self._port}/ws")
        return True

    def stop(self) -> None:
        """
        Gracefully stops the WebSocket server, disconnects all clients,
        and joins the server thread.
        """
        if not self._running:
            return

        logger.info("Stopping local bridge server...")
        self._running = False

        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._cleanup_async(), self._loop)
            try:
                future.result(timeout=3.0)
            except Exception as e:
                logger.debug(f"Bridge async cleanup notice: {e}")

        if self._server_thread and self._server_thread.is_alive():
            if threading.current_thread() != self._server_thread:
                self._server_thread.join(timeout=2.0)
        self._server_thread = None

        with self._clients_lock:
            self._clients.clear()

        logger.info("Local bridge server stopped cleanly.")

    def broadcast_event(self, event_json: str) -> None:
        """
        Thread-safely schedules a broadcast of an event (e.g. user_utterance or assistant_spoken)
        to all active WebSocket clients. Completely non-blocking for caller.
        """
        if not self._running or not self._loop or not self._loop.is_running():
            return

        with self._clients_lock:
            if not self._clients:
                return

        try:
            asyncio.run_coroutine_threadsafe(self._async_broadcast(event_json), self._loop)
        except Exception as e:
            logger.debug(f"[BRIDGE] Failed to dispatch broadcast coroutine: {e}")

    async def _async_broadcast(self, msg_str: str) -> None:
        """Coroutine that delivers a message string to all active clients."""
        with self._clients_lock:
            active_clients = list(self._clients)

        stale_clients = []
        for ws in active_clients:
            if ws.closed:
                stale_clients.append(ws)
                continue
            try:
                await ws.send_str(msg_str)
            except Exception:
                stale_clients.append(ws)

        if stale_clients:
            with self._clients_lock:
                for s in stale_clients:
                    self._clients.discard(s)

    def _run_server_thread(self) -> None:
        """Target function running the asyncio event loop on a dedicated thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._init_server())
            self._loop.create_task(self._telemetry_broadcast_loop())
            self._started_event.set()
            self._loop.run_forever()
        except Exception as e:
            self._startup_error = str(e)
            self._started_event.set()
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.close()
            except Exception:
                pass

    async def _init_server(self) -> None:
        """Initializes the aiohttp application, routes, and TCP site."""
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/", self._ws_handler)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

    async def _cleanup_async(self) -> None:
        """Asynchronously closes all active client sockets and stops the site/runner."""
        with self._clients_lock:
            active_clients = list(self._clients)
            self._clients.clear()

        # Close all active WebSockets with a clean normal close code
        for ws in active_clients:
            if not ws.closed:
                try:
                    await ws.close(code=web.WSCloseCode.GOING_AWAY, message=b"Server shutting down")
                except Exception:
                    pass

        if self._site:
            try:
                await self._site.stop()
            except Exception:
                pass
            self._site = None

        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception:
                pass
            self._runner = None

        if self._loop and self._loop.is_running():
            self._loop.stop()

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handles incoming WebSocket connections and messages from desktop clients."""
        # 1. Security Check: verify client IP is strictly localhost
        remote_ip = request.remote or "unknown"
        if remote_ip not in ("127.0.0.1", "::1", "localhost"):
            logger.warning(f"[BRIDGE SECURITY] Rejected remote connection attempt from {remote_ip}")
            return web.Response(status=403, text="Forbidden: Localhost connections only.")

        ws = web.WebSocketResponse(heartbeat=15.0, max_msg_size=65536)
        await ws.prepare(request)

        with self._clients_lock:
            self._clients.add(ws)
            current_count = len(self._clients)

        logger.info(f"Dashboard client connected to bridge (active clients: {current_count})")

        # 2. Send immediate initial telemetry snapshot upon connection
        try:
            snapshot = self.collector.collect_snapshot()
            initial_msg = create_telemetry_message(snapshot)
            await ws.send_str(initial_msg)
        except Exception as e:
            logger.warning(f"Failed to send initial telemetry snapshot: {e}")

        # 3. Message Processing Loop
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    is_valid, parsed, error_reason = validate_incoming_message(msg.data)
                    if not is_valid:
                        logger.warning(f"Rejected invalid message from client: {error_reason}")
                        await ws.send_str(create_error_message("INVALID_MESSAGE", error_reason or "Validation failed"))
                        continue

                    msg_type = (parsed.get("type") or "").strip().lower()
                    if msg_type == "ping":
                        await ws.send_str(create_message(BridgeMessageType.PONG, {"status": "ONLINE"}))
                    elif msg_type == "status":
                        with self._clients_lock:
                            count = len(self._clients)
                        await ws.send_str(create_status_message("ONLINE", {"client_count": count}))
                    elif msg_type == "music_control":
                        action_res = await self._handle_music_control(parsed.get("payload", {}))
                        await ws.send_str(create_message(
                            BridgeMessageType.STATUS,
                            {"music_control_result": action_res}
                        ))
                    elif msg_type == "playlist_control":
                        action_res = await self._handle_playlist_control(parsed.get("payload", {}))
                        await ws.send_str(create_message(
                            BridgeMessageType.STATUS,
                            {"playlist_control_result": action_res}
                        ))
                    elif msg_type == "mic_control":
                        action_res = await self._handle_mic_control(parsed.get("payload", {}))
                        await ws.send_str(create_message(
                            BridgeMessageType.STATUS,
                            {"mic_control_result": action_res}
                        ))
                    elif msg_type == "text_command":
                        payload = parsed.get("payload", {})
                        action_res = await self._handle_text_command(payload)
                        req_id = payload.get("request_id") or parsed.get("correlation_id") or action_res.get("request_id", "")
                        ack_msg = create_text_command_ack_event(
                            request_id=str(req_id),
                            success=action_res.get("success", False),
                            status=action_res.get("status", "ERROR"),
                            message=action_res.get("message", ""),
                            correlation_id=parsed.get("correlation_id"),
                        )
                        await ws.send_str(ack_msg)

                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
                elif msg.type == WSMsgType.ERROR:
                    logger.warning(f"WebSocket connection closed with error: {ws.exception()}")
                    break
        except Exception as e:
            logger.debug(f"Exception in WebSocket client handler: {e}")
        finally:
            with self._clients_lock:
                self._clients.discard(ws)
                remaining_count = len(self._clients)
            logger.info(f"Dashboard client disconnected from bridge (active clients: {remaining_count})")

        return ws

    async def _handle_music_control(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Safely dispatches validated music control commands to the music engine."""
        action = payload.get("action", "").lower()
        player = getattr(self, "_music_player", None)
        if not player:
            return {"success": False, "action": action, "reason": "Music player unavailable"}

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._dispatch_music_action, player, payload)
        except Exception as e:
            logger.warning(f"[BRIDGE] Error executing music action '{action}': {e}")
            return {"success": False, "action": action, "reason": str(e)}

    def _dispatch_music_action(self, player: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes synchronous music player action in worker thread."""
        action = (payload.get("action") or "").strip().lower()
        val = payload.get("value")

        if action in ("play", "resume"):
            state = getattr(player, "playback_state", "")
            if state == "PAUSED" and hasattr(player, "resume"):
                ok = player.resume()
            elif hasattr(player, "play_song") and getattr(player, "_last_played_title", None):
                ok, _ = player.play_song(player._last_played_title)
            else:
                ok = False
            return {"success": ok, "action": action}

        elif action == "pause":
            ok = player.pause() if hasattr(player, "pause") else False
            return {"success": ok, "action": action}

        elif action == "toggle_play":
            ok = player.toggle_play() if hasattr(player, "toggle_play") else False
            return {"success": ok, "action": action}

        elif action == "stop":
            ok = player.stop() if hasattr(player, "stop") else False
            return {"success": ok, "action": action}

        elif action == "next":
            if hasattr(player, "next_track"):
                ok, reason = player.next_track()
            else:
                ok, reason = False, "Unsupported action"
            return {"success": ok, "action": action, "reason": reason}

        elif action == "previous":
            if hasattr(player, "previous_track"):
                ok, reason = player.previous_track()
            else:
                ok, reason = False, "Unsupported action"
            return {"success": ok, "action": action, "reason": reason}

        elif action == "volume":
            if hasattr(player, "set_volume") and val is not None:
                ok = player.set_volume(int(val))
            else:
                ok = False
            return {"success": ok, "action": action, "value": val}

        elif action == "mute":
            if hasattr(player, "set_mute"):
                is_muted = bool(val) if val is not None else not getattr(player, "_is_muted", False)
                ok = player.set_mute(is_muted)
            elif hasattr(player, "set_volume"):
                is_muted = bool(val) if val is not None else True
                ok = player.set_volume(0 if is_muted else 80)
            else:
                ok, is_muted = False, False
            return {"success": ok, "action": action, "is_muted": is_muted}

        elif action == "seek":
            if hasattr(player, "seek") and val is not None:
                ok = player.seek(float(val))
            else:
                ok = False
            return {"success": ok, "action": action, "value": val}

        return {"success": False, "action": action, "reason": "Unknown action"}

    async def _handle_playlist_control(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Safely dispatches validated playlist control commands to the music engine."""
        action = payload.get("action", "").lower()
        player = getattr(self, "_music_player", None)
        if not player:
            return {"success": False, "action": action, "reason": "Music player unavailable"}

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._dispatch_playlist_action, player, payload)
        except Exception as e:
            logger.warning(f"[BRIDGE] Error executing playlist action '{action}': {e}")
            return {"success": False, "action": action, "reason": str(e)}

    def _dispatch_playlist_action(self, player: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes synchronous playlist action in worker thread."""
        action = (payload.get("action") or "").strip().lower()

        if action == "start":
            pl_id = payload.get("playlist_id", "")
            shuffle = bool(payload.get("shuffle", False))
            ok, msg = player.play_playlist(pl_id, shuffle=shuffle)
            return {"success": ok, "action": action, "message": msg}

        elif action == "select_song":
            if "index" in payload and payload["index"] is not None:
                ok, msg = player.play_playlist_song_by_index(int(payload["index"]))
            elif "title" in payload and payload["title"]:
                ok, msg = player.play_playlist_song_by_title(str(payload["title"]))
            else:
                ok, msg = False, "Missing song index or title"
            return {"success": ok, "action": action, "message": msg}

        elif action == "next":
            ok, msg = player.next_track()
            return {"success": ok, "action": action, "message": msg}

        elif action == "previous":
            ok, msg = player.previous_track()
            return {"success": ok, "action": action, "message": msg}

        elif action == "toggle_shuffle":
            ok, is_shuffle = player.toggle_shuffle()
            return {"success": ok, "action": action, "is_shuffle": is_shuffle}

        elif action == "stop":
            ok = player.stop_playlist() if hasattr(player, "stop_playlist") else player.stop()
            return {"success": ok, "action": action}

        elif action == "get_snapshot":
            snap = player.get_playlist_snapshot() if hasattr(player, "get_playlist_snapshot") else {}
            return {"success": True, "action": action, "snapshot": snap}

        return {"success": False, "action": action, "reason": "Unknown action"}

    async def _handle_mic_control(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Safely dispatches validated microphone control commands."""
        action = payload.get("action", "").lower()
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._dispatch_mic_action, payload)
        except Exception as e:
            logger.warning(f"[BRIDGE] Error executing mic action '{action}': {e}")
            return {"success": False, "action": action, "reason": str(e)}

    def _dispatch_mic_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes synchronous microphone state update in worker thread."""
        action = (payload.get("action") or "").strip().lower()
        assistant = getattr(self, "_assistant", None)

        if action == "set_active":
            val = bool(payload.get("value"))
            if assistant and hasattr(assistant, "set_mic_active"):
                assistant.set_mic_active(val)
            elif assistant and getattr(assistant, "listener", None):
                assistant.listener.set_mic_active(val)
            return {"success": True, "action": action, "is_active": val}

        elif action == "toggle":
            curr = True
            if assistant and getattr(assistant, "listener", None):
                curr = getattr(assistant.listener, "is_mic_active", True)
            new_val = not curr
            if assistant and hasattr(assistant, "set_mic_active"):
                assistant.set_mic_active(new_val)
            elif assistant and getattr(assistant, "listener", None):
                assistant.listener.set_mic_active(new_val)
            return {"success": True, "action": action, "is_active": new_val}

        return {"success": False, "action": action, "reason": "Unknown action"}

    async def _handle_text_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Safely dispatches validated text command to the assistant request queue."""
        text = payload.get("text", "")
        request_id = payload.get("request_id")
        assistant = getattr(self, "_assistant", None)
        if not assistant:
            return {
                "success": False,
                "status": "ASSISTANT_UNAVAILABLE",
                "message": "Assistant instance unavailable on bridge server",
                "request_id": request_id,
            }

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._dispatch_text_command, assistant, text, request_id)
        except Exception as e:
            logger.warning(f"[BRIDGE] Error dispatching text command '{text}': {e}")
            return {
                "success": False,
                "status": "INTERNAL_ERROR",
                "message": str(e),
                "request_id": request_id,
            }

    def _dispatch_text_command(self, assistant: Any, text: str, request_id: Optional[str]) -> Dict[str, Any]:
        """Executes synchronous text command enqueue in worker thread."""
        if hasattr(assistant, "admit_text_command"):
            success, status, message = assistant.admit_text_command(text, request_id=request_id)
            return {
                "success": success,
                "status": status,
                "message": message,
                "request_id": request_id,
            }
        return {
            "success": False,
            "status": "NOT_IMPLEMENTED",
            "message": "Assistant does not support admit_text_command",
            "request_id": request_id,
        }

    async def _telemetry_broadcast_loop(self) -> None:
        """Periodically samples telemetry and broadcasts to all connected clients."""
        while self._running:
            try:
                await asyncio.sleep(self._telemetry_interval)
                if not self._running:
                    break

                with self._clients_lock:
                    if not self._clients:
                        continue
                    active_clients = list(self._clients)

                snapshot = self.collector.collect_snapshot()
                msg = create_telemetry_message(snapshot)
                await self._async_broadcast(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry broadcast loop: {e}", exc_info=True)

