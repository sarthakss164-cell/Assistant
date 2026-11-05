import { useState, useEffect, useRef, useCallback } from 'react';
import {
  BridgeStatus,
  SystemMetrics,
  ProcessWatcher,
  ConversationItem,
  VoiceState,
  ActiveAction,
  MusicPlaybackState,
  PlaylistState,
  TextCommandAckResult,
  AiCoreData,
  GatewayStatus,
  AiRuntimeState,
  SessionMemoryStatus,
} from '../types/dashboard';

export const DEFAULT_AI_CORE_DATA: AiCoreData = {
  engine: 'CoE AI Gateway (vLLM)',
  activePersona: 'Assistant Mode',
  contextWindowUsed: 0,
  contextWindowTotal: 0,
  uptimeSeconds: 0,
  actionsExecutedCount: 0,
  systemState: 'STANDBY',
  configuredModel: 'qwen3.6',
  resolvedModel: 'Unknown',
  provider: 'CoE AI Gateway (vLLM)',
  gatewayStatus: 'DISCONNECTED',
  runtimeState: 'IDLE',
  inFlightRequests: 0,
  lastTokens: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
  sessionTokens: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
  contextCapacity: null,
  remainingTokens: null,
  utilizationPercentage: null,
  lastRequestLatencyMs: null,
  lastSuccessfulLatencyMs: null,
  avgLatencyMs: null,
  recentLatenciesMs: [],
  successCount: 0,
  failureCount: 0,
  lastSuccessTimestamp: null,
  lastRequestStatus: null,
  lastErrorCategory: null,
  historyIncluded: false,
  sessionMemoryTurns: 0,
  sessionMemoryMaxTurns: 10,
  sessionMemoryAvailable: true,
  sessionMemoryStatus: 'EMPTY',
};

function parseAiCorePayload(payload: any, prev: AiCoreData): AiCoreData {
  if (!payload || typeof payload !== 'object') return prev;

  const configuredModel = payload.configured_model ? String(payload.configured_model) : (prev.configuredModel || 'qwen3.6');
  const resolvedModel = payload.resolved_model ? String(payload.resolved_model) : (prev.resolvedModel || 'Unknown');
  const provider = payload.provider ? String(payload.provider) : (prev.provider || 'CoE AI Gateway (vLLM)');

  const rawStatus = String(payload.status || prev.gatewayStatus || 'STANDBY').toUpperCase();
  const validStatuses: GatewayStatus[] = ['ONLINE', 'STANDBY', 'PROCESSING', 'ERROR', 'DISCONNECTED'];
  const gatewayStatus: GatewayStatus = validStatuses.includes(rawStatus as GatewayStatus)
    ? (rawStatus as GatewayStatus)
    : 'STANDBY';

  const rawRuntime = String(payload.runtime_state || prev.runtimeState || 'IDLE').toUpperCase();
  const validRuntimes: AiRuntimeState[] = ['IDLE', 'PROCESSING', 'SUCCESS', 'ERROR'];
  const runtimeState: AiRuntimeState = validRuntimes.includes(rawRuntime as AiRuntimeState)
    ? (rawRuntime as AiRuntimeState)
    : 'IDLE';

  const inFlightRequests = typeof payload.in_flight_requests === 'number' ? payload.in_flight_requests : 0;

  const lastTokens = {
    promptTokens: Number(payload.last_tokens?.prompt_tokens) || 0,
    completionTokens: Number(payload.last_tokens?.completion_tokens) || 0,
    totalTokens: Number(payload.last_tokens?.total_tokens) || 0,
  };

  const sessionTokens = {
    promptTokens: Number(payload.session_tokens?.prompt_tokens) || 0,
    completionTokens: Number(payload.session_tokens?.completion_tokens) || 0,
    totalTokens: Number(payload.session_tokens?.total_tokens) || 0,
  };

  const contextCapacity = payload.context_capacity !== null && payload.context_capacity !== undefined
    ? Number(payload.context_capacity)
    : null;

  const remainingTokens = payload.remaining_tokens !== null && payload.remaining_tokens !== undefined
    ? Number(payload.remaining_tokens)
    : null;

  const utilizationPercentage = payload.utilization_percentage !== null && payload.utilization_percentage !== undefined
    ? Number(payload.utilization_percentage)
    : null;

  const lastRequestLatencyMs = payload.last_request_latency_ms !== null && payload.last_request_latency_ms !== undefined
    ? Number(payload.last_request_latency_ms)
    : prev.lastRequestLatencyMs;

  const lastSuccessfulLatencyMs = payload.last_successful_latency_ms !== null && payload.last_successful_latency_ms !== undefined
    ? Number(payload.last_successful_latency_ms)
    : prev.lastSuccessfulLatencyMs;

  const avgLatencyMs = payload.avg_latency_ms !== null && payload.avg_latency_ms !== undefined
    ? Number(payload.avg_latency_ms)
    : prev.avgLatencyMs;

  const recentLatenciesMs = Array.isArray(payload.recent_latencies_ms)
    ? payload.recent_latencies_ms.map((n: any) => Number(n))
    : prev.recentLatenciesMs;

  const successCount = typeof payload.success_count === 'number' ? payload.success_count : prev.successCount;
  const failureCount = typeof payload.failure_count === 'number' ? payload.failure_count : prev.failureCount;

  const lastSuccessTimestamp = payload.last_success_timestamp !== null && payload.last_success_timestamp !== undefined
    ? Number(payload.last_success_timestamp)
    : prev.lastSuccessTimestamp;

  const lastRequestStatus = payload.last_request_status ? String(payload.last_request_status) : prev.lastRequestStatus;
  const lastErrorCategory = payload.last_error_category ? String(payload.last_error_category) : prev.lastErrorCategory;
  const historyIncluded = payload.history_included !== undefined ? Boolean(payload.history_included) : prev.historyIncluded;

  const sessionMemoryTurns = typeof payload.session_memory_turns === 'number' ? payload.session_memory_turns : prev.sessionMemoryTurns;
  const sessionMemoryMaxTurns = typeof payload.session_memory_max_turns === 'number' ? payload.session_memory_max_turns : 10;
  const sessionMemoryAvailable = payload.session_memory_available !== undefined ? Boolean(payload.session_memory_available) : true;

  const rawMemStatus = String(payload.session_memory_status || prev.sessionMemoryStatus || 'EMPTY').toUpperCase();
  const validMemStatuses: SessionMemoryStatus[] = ['EMPTY', 'ACTIVE', 'MAX_CAPACITY', 'DISABLED'];
  const sessionMemoryStatus: SessionMemoryStatus = validMemStatuses.includes(rawMemStatus as SessionMemoryStatus)
    ? (rawMemStatus as SessionMemoryStatus)
    : 'EMPTY';

  const uptimeSeconds = typeof payload.uptime_seconds === 'number' ? payload.uptime_seconds : prev.uptimeSeconds;
  const actionsExecutedCount = typeof payload.actions_executed_count === 'number' ? payload.actions_executed_count : prev.actionsExecutedCount;

  // Derive systemState for ThreeOrb and backward compatibility
  let systemState: 'ONLINE' | 'STANDBY' | 'BUSY' | 'ERROR' = 'STANDBY';
  if (runtimeState === 'PROCESSING' || inFlightRequests > 0) {
    systemState = 'BUSY';
  } else if (gatewayStatus === 'ERROR' || runtimeState === 'ERROR') {
    systemState = 'ERROR';
  } else if (gatewayStatus === 'ONLINE') {
    systemState = 'ONLINE';
  } else if (gatewayStatus === 'STANDBY') {
    systemState = 'STANDBY';
  }

  return {
    engine: provider,
    activePersona: 'Assistant Mode',
    contextWindowUsed: lastTokens.totalTokens || 0,
    contextWindowTotal: contextCapacity || 0,
    uptimeSeconds,
    actionsExecutedCount,
    systemState,
    configuredModel,
    resolvedModel,
    provider,
    gatewayStatus,
    runtimeState,
    inFlightRequests,
    lastTokens,
    sessionTokens,
    contextCapacity,
    remainingTokens,
    utilizationPercentage,
    lastRequestLatencyMs,
    lastSuccessfulLatencyMs,
    avgLatencyMs,
    recentLatenciesMs,
    successCount,
    failureCount,
    lastSuccessTimestamp,
    lastRequestStatus,
    lastErrorCategory,
    historyIncluded,
    sessionMemoryTurns,
    sessionMemoryMaxTurns,
    sessionMemoryAvailable,
    sessionMemoryStatus,
  };
}

export const DEFAULT_PLAYLIST_STATE: PlaylistState = {
  hasActiveSession: false,
  playlistId: null,
  name: null,
  entries: [],
  currentIndex: -1,
  isShuffle: false,
  state: 'IDLE',
  revision: 0,
};

function parsePlaylistPayload(payload: any): PlaylistState {
  if (!payload || typeof payload !== 'object') return DEFAULT_PLAYLIST_STATE;
  const hasActiveSession = Boolean(payload.has_active_session);
  const playlistId = payload.playlist_id ? String(payload.playlist_id) : null;
  const name = payload.name ? String(payload.name) : null;
  const currentIndex = typeof payload.current_index === 'number' ? payload.current_index : -1;
  const isShuffle = Boolean(payload.is_shuffle);
  const rawState = String(payload.state || 'IDLE').toUpperCase();
  const validStates: PlaylistState['state'][] = ['IDLE', 'PLAYING', 'PAUSED', 'COMPLETED', 'STOPPED'];
  const state: PlaylistState['state'] = validStates.includes(rawState as any) ? (rawState as any) : 'IDLE';
  const revision = Number(payload.revision) || 0;

  const rawEntries = Array.isArray(payload.entries) ? payload.entries : [];
  const entries = rawEntries.map((e: any, idx: number) => ({
    id: e.id ? String(e.id) : String(e.index !== undefined ? e.index : idx),
    title: String(e.title || `Track ${idx + 1}`),
    query: e.query ? String(e.query) : undefined,
  }));

  return {
    hasActiveSession,
    playlistId,
    name,
    entries,
    currentIndex,
    isShuffle,
    state,
    revision,
  };
}

const BRIDGE_WS_URL = 'ws://127.0.0.1:8765/ws';
const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 5000;

export const DEFAULT_ACTIVE_ACTION: ActiveAction = {
  type: 'IDLE',
  title: 'NO ACTIVE PLAYBACK',
  subtitle: 'STANDBY // READY FOR AUDIO',
  durationSeconds: 0,
  positionSeconds: 0,
  isPlaying: false,
  source: 'YouTube',
  playbackState: 'IDLE',
  lastPlayed: null,
};

function parseMusicPayload(payload: any, prevAction: ActiveAction): ActiveAction {
  if (!payload || typeof payload !== 'object') return prevAction;
  const rawState = String(payload.state || 'IDLE').toUpperCase();
  const validStates: MusicPlaybackState[] = ['IDLE', 'LOADING', 'PLAYING', 'PAUSED', 'STOPPED', 'ERROR'];
  const playbackState: MusicPlaybackState = validStates.includes(rawState as MusicPlaybackState)
    ? (rawState as MusicPlaybackState)
    : 'IDLE';

  const isPlaying = Boolean(payload.is_playing);
  const title = String(payload.title || '').trim();
  const artist = String(payload.artist || '').trim();
  const lastPlayed = payload.last_played ? String(payload.last_played).trim() : prevAction.lastPlayed;

  let displayTitle = title;
  let displaySubtitle = artist;

  if (playbackState === 'IDLE') {
    displayTitle = 'NO ACTIVE PLAYBACK';
    displaySubtitle = lastPlayed ? `LAST PLAYED // ${lastPlayed}` : 'STANDBY // READY FOR AUDIO';
  } else if (playbackState === 'STOPPED') {
    displayTitle = title || 'NO ACTIVE PLAYBACK';
    displaySubtitle = lastPlayed ? `LAST PLAYED // ${lastPlayed}` : (artist || 'STOPPED // STANDBY');
  } else if (playbackState === 'LOADING') {
    displayTitle = title || 'SEARCHING & BUFFERING...';
    displaySubtitle = artist ? `${artist} // BUFFERING` : 'FETCHING STREAM...';
  } else if (playbackState === 'ERROR') {
    displayTitle = title || 'PLAYBACK FAILED';
    displaySubtitle = artist ? `${artist} // STREAM UNAVAILABLE` : 'STREAM ERROR // TRY ANOTHER QUERY';
  } else {
    // PLAYING or PAUSED
    displayTitle = title || 'UNKNOWN TRACK';
    displaySubtitle = artist || 'AUDIO STREAM';
  }

  return {
    type: playbackState === 'IDLE' ? 'IDLE' : 'MUSIC',
    title: displayTitle,
    subtitle: displaySubtitle,
    durationSeconds: Number(payload.duration_seconds) || 0,
    positionSeconds: Number(payload.position_seconds) || 0,
    isPlaying,
    source: String(payload.source || 'YouTube'),
    playbackState,
    lastPlayed,
    volume: payload.volume !== undefined ? Number(payload.volume) : prevAction.volume,
    isMuted: payload.is_muted !== undefined ? Boolean(payload.is_muted) : prevAction.isMuted,
  };
}

export const DEFAULT_VOICE_STATE: VoiceState = {
  userState: 'IDLE',
  aiState: 'STANDBY',
  recognizedUtterance: '',
  spokenResponse: '',
  userActivityLevel: 0.0,
  aiActivityLevel: 0.0,
};

export interface UseTelemetryBridgeResult {
  bridgeStatus: BridgeStatus;
  liveMetrics: SystemMetrics | null;
  liveProcessWatcher: ProcessWatcher | null;
  liveAiCoreData: AiCoreData;
  conversationLog: ConversationItem[];
  liveVoiceState: VoiceState;
  liveActiveAction: ActiveAction;
  livePlaylistState: PlaylistState;
  isMicActive: boolean;
  addLocalMessage: (item: ConversationItem) => void;
  clearConversation: () => void;
  sendMusicControl: (action: string, value?: any) => boolean;
  sendPlaylistControl: (action: string, payload?: any) => boolean;
  sendMicControl: (active: boolean) => boolean;
  sendTextCommand: (text: string) => Promise<TextCommandAckResult>;
}

export function useTelemetryBridge(): UseTelemetryBridgeResult {
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>('CONNECTING');
  const [liveMetrics, setLiveMetrics] = useState<SystemMetrics | null>(null);
  const [liveProcessWatcher, setLiveProcessWatcher] = useState<ProcessWatcher | null>(null);
  const [liveAiCoreData, setLiveAiCoreData] = useState<AiCoreData>(DEFAULT_AI_CORE_DATA);
  const [conversationLog, setConversationLog] = useState<ConversationItem[]>([]);
  const [liveVoiceState, setLiveVoiceState] = useState<VoiceState>(DEFAULT_VOICE_STATE);
  const [liveActiveAction, setLiveActiveAction] = useState<ActiveAction>(DEFAULT_ACTIVE_ACTION);
  const [livePlaylistState, setLivePlaylistState] = useState<PlaylistState>(DEFAULT_PLAYLIST_STATE);
  const [isMicActive, setIsMicActive] = useState<boolean>(true);

  const clearConversation = useCallback(() => {
    setConversationLog([]);
  }, []);

  const addLocalMessage = useCallback((item: ConversationItem) => {
    setConversationLog((prev) => {
      if (prev.some((existing) => existing.id === item.id)) {
        return prev;
      }
      const updated = [...prev, item];
      return updated.length > 100 ? updated.slice(updated.length - 100) : updated;
    });
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectDelayRef = useRef<number>(INITIAL_RECONNECT_DELAY_MS);
  const isMountedRef = useRef<boolean>(true);
  const pendingTextAcksRef = useRef<Map<string, {
    resolve: (res: TextCommandAckResult) => void;
    timer: number;
  }>>(new Map());

  const sendMusicControl = useCallback((action: string, value?: any): boolean => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[BRIDGE] Cannot send music control: WebSocket is not connected');
      return false;
    }
    const cleanAction = (action || '').trim().toLowerCase();
    const payload: { action: string; value?: any } = { action: cleanAction };
    if (value !== undefined) {
      payload.value = value;
    }
    const message = {
      schema_version: '1.0',
      type: 'music_control',
      timestamp: Date.now() / 1000,
      payload,
    };
    try {
      wsRef.current.send(JSON.stringify(message));
      return true;
    } catch (err) {
      console.error('[BRIDGE] Failed to dispatch music control command:', err);
      return false;
    }
  }, []);

  const sendPlaylistControl = useCallback((action: string, payloadData?: any): boolean => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[BRIDGE] Cannot send playlist control: WebSocket is not connected');
      return false;
    }
    const cleanAction = (action || '').trim().toLowerCase();
    const payload = { action: cleanAction, ...(payloadData || {}) };
    const message = {
      schema_version: '1.0',
      type: 'playlist_control',
      timestamp: Date.now() / 1000,
      payload,
    };
    try {
      wsRef.current.send(JSON.stringify(message));
      return true;
    } catch (err) {
      console.error('[BRIDGE] Failed to dispatch playlist control command:', err);
      return false;
    }
  }, []);

  const sendMicControl = useCallback((active: boolean): boolean => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[BRIDGE] Cannot send mic control: WebSocket is not connected');
      return false;
    }
    const message = {
      schema_version: '1.0',
      type: 'mic_control',
      timestamp: Date.now() / 1000,
      payload: { action: 'set_active', value: Boolean(active) },
    };
    try {
      wsRef.current.send(JSON.stringify(message));
      return true;
    } catch (err) {
      console.error('[BRIDGE] Failed to dispatch mic control command:', err);
      return false;
    }
  }, []);

  const sendTextCommand = useCallback((text: string): Promise<TextCommandAckResult> => {
    return new Promise((resolve) => {
      const clean = (text || '').trim();
      if (!clean) {
        resolve({ success: false, status: 'EMPTY_TEXT', message: 'Command cannot be empty' });
        return;
      }
      if (clean.length > 500) {
        resolve({ success: false, status: 'TEXT_TOO_LONG', message: 'Command exceeds 500 characters' });
        return;
      }
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        resolve({ success: false, status: 'DISCONNECTED', message: 'Bridge WebSocket is not connected' });
        return;
      }

      const reqId = `txt_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      const message = {
        schema_version: '1.0',
        type: 'text_command',
        timestamp: Date.now() / 1000,
        payload: {
          text: clean,
          request_id: reqId,
        },
      };

      const timer = window.setTimeout(() => {
        if (pendingTextAcksRef.current.has(reqId)) {
          pendingTextAcksRef.current.delete(reqId);
          resolve({ success: false, status: 'TIMEOUT', message: 'Command acknowledgement timed out' });
        }
      }, 10000);

      pendingTextAcksRef.current.set(reqId, { resolve, timer });

      try {
        wsRef.current.send(JSON.stringify(message));
      } catch (err: any) {
        window.clearTimeout(timer);
        pendingTextAcksRef.current.delete(reqId);
        resolve({ success: false, status: 'SEND_FAILED', message: err?.message || 'Failed to send message' });
      }
    });
  }, []);

  useEffect(() => {
    isMountedRef.current = true;

    function connect() {
      if (!isMountedRef.current) return;

      setBridgeStatus((prev) => (prev === 'ONLINE' ? 'CONNECTING' : prev));

      try {
        const ws = new WebSocket(BRIDGE_WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMountedRef.current) {
            ws.close();
            return;
          }
          setBridgeStatus('ONLINE');
          setLiveAiCoreData((prev) => ({
            ...prev,
            gatewayStatus: prev.gatewayStatus === 'DISCONNECTED' ? 'STANDBY' : prev.gatewayStatus,
          }));
          reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS; // Reset backoff on success
        };

        ws.onmessage = (event) => {
          if (!isMountedRef.current) return;

          try {
            const data = JSON.parse(event.data);
            if (data.schema_version !== '1.0' || !data.type || !data.payload) {
              return;
            }

            if (data.type === 'telemetry') {
              const { system_metrics: m, process_watcher: p } = data.payload;

              if (m) {
                setLiveMetrics({
                  ramUsedGb: Number(m.ram_used_gb) || 0,
                  ramTotalGb: Number(m.ram_total_gb) || 0,
                  ramPercent: Number(m.ram_percent) || 0,
                  cpuPercent: Number(m.cpu_percent) || 0,
                  cpuHistory: Array.isArray(m.cpu_history) ? m.cpu_history : [],
                  storageUsedGb: Number(m.storage_used_gb) || 0,
                  storageTotalGb: Number(m.storage_total_gb) || 0,
                  storagePercent: Number(m.storage_percent) || 0,
                  storageDrive: m.storage_drive || 'C:',
                  batteryPercent:
                    m.battery_percent !== null && m.battery_percent !== undefined
                      ? Number(m.battery_percent)
                      : null,
                  batteryCharging: Boolean(m.battery_charging),
                  hasBattery: Boolean(m.has_battery),
                });
              }

              if (p) {
                setLiveProcessWatcher({
                  foregroundApp: String(p.foreground_app || 'DESKTOP / SYSTEM'),
                  foregroundPid:
                    p.foreground_pid !== null && p.foreground_pid !== undefined
                      ? Number(p.foreground_pid)
                      : null,
                  activeProcess: String(p.active_process || 'STANDBY'),
                  activeProcessPid:
                    p.active_process_pid !== null && p.active_process_pid !== undefined
                      ? Number(p.active_process_pid)
                      : null,
                  toolLatencyMs:
                    p.tool_latency_ms !== null && p.tool_latency_ms !== undefined
                      ? Number(p.tool_latency_ms)
                      : null,
                });
              }

              if (data.payload?.music) {
                setLiveActiveAction((prev) => parseMusicPayload(data.payload.music, prev));
              }

              if (data.payload?.playlist) {
                setLivePlaylistState(parsePlaylistPayload(data.payload.playlist));
              }

              if (data.payload?.microphone && data.payload.microphone.is_active !== undefined) {
                setIsMicActive(Boolean(data.payload.microphone.is_active));
              }

              if (data.payload?.ai_core) {
                setLiveAiCoreData((prev) => parseAiCorePayload(data.payload.ai_core, prev));
              }
            } else if (data.type === 'user_utterance') {
              const text = data.payload?.text;
              if (typeof text === 'string' && text.trim().length > 0) {
                const eventId = data.event_id || `u_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
                const timestamp = data.timestamp
                  ? new Date(data.timestamp * 1000).toTimeString().substring(0, 8)
                  : new Date().toTimeString().substring(0, 8);

                setConversationLog((prev) => {
                  if (prev.some((item) => item.id === eventId)) {
                    return prev;
                  }
                  const newItem: ConversationItem = {
                    id: eventId,
                    sender: 'USER',
                    text: text.trim(),
                    timestamp,
                    status: 'RECOGNIZED',
                  };
                  const updated = [...prev, newItem];
                  return updated.length > 100 ? updated.slice(updated.length - 100) : updated;
                });

                // Update real recognized utterance display
                setLiveVoiceState((prev) => ({
                  ...prev,
                  recognizedUtterance: text.trim(),
                  userState: 'IDLE',
                  userActivityLevel: 0.0,
                }));
              }
            } else if (data.type === 'assistant_spoken') {
              const text = data.payload?.text;
              if (typeof text === 'string' && text.trim().length > 0) {
                const eventId = data.event_id || `a_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
                const timestamp = data.timestamp
                  ? new Date(data.timestamp * 1000).toTimeString().substring(0, 8)
                  : new Date().toTimeString().substring(0, 8);

                setConversationLog((prev) => {
                  if (prev.some((item) => item.id === eventId)) {
                    return prev;
                  }
                  const newItem: ConversationItem = {
                    id: eventId,
                    sender: 'ASSISTANT',
                    text: text.trim(),
                    timestamp,
                    status: 'COMPLETED',
                  };
                  const updated = [...prev, newItem];
                  return updated.length > 100 ? updated.slice(updated.length - 100) : updated;
                });

                // Update real spoken response display
                setLiveVoiceState((prev) => ({
                  ...prev,
                  spokenResponse: text.trim(),
                  aiState: 'STANDBY',
                  aiActivityLevel: 0.0,
                }));
              }
            } else if (data.type === 'voice_state') {
              const { channel, state: vState, detail } = data.payload || {};
              const chan = String(channel || '').toLowerCase();
              const st = String(vState || '').toUpperCase();

              setLiveVoiceState((prev) => {
                if (chan === 'user') {
                  if (st === 'MUTED') {
                    setIsMicActive(false);
                  }
                  const userState = (st || 'IDLE') as VoiceState['userState'];
                  const isListening = userState === 'LISTENING';
                  const isProcessing = userState === 'PROCESSING';
                  return {
                    ...prev,
                    userState,
                    userActivityLevel: isListening ? 0.8 : isProcessing ? 0.35 : 0.0,
                    recognizedUtterance: detail ? String(detail) : prev.recognizedUtterance,
                  };
                } else if (chan === 'assistant') {
                  const isSpeaking = st === 'SPEAKING';
                  const aiState = (isSpeaking ? 'SPEAKING' : st === 'ERROR' ? 'ERROR' : 'STANDBY') as VoiceState['aiState'];
                  return {
                    ...prev,
                    aiState,
                    aiActivityLevel: isSpeaking ? 0.85 : 0.0,
                    spokenResponse: detail ? String(detail) : prev.spokenResponse,
                  };
                }
                return prev;
              });
            } else if (data.type === 'music_state') {
              setLiveActiveAction((prev) => parseMusicPayload(data.payload, prev));
            } else if (data.type === 'playlist_state') {
              setLivePlaylistState(parsePlaylistPayload(data.payload));
            } else if (data.type === 'mic_state') {
              if (data.payload && data.payload.is_active !== undefined) {
                setIsMicActive(Boolean(data.payload.is_active));
              }
            } else if (data.type === 'ai_core_state') {
              if (data.payload) {
                setLiveAiCoreData((prev) => parseAiCorePayload(data.payload, prev));
              }
            } else if (data.type === 'text_command_ack') {
              const { request_id, success, status, message } = data.payload || {};
              const reqId = request_id || data.correlation_id;
              if (reqId && pendingTextAcksRef.current.has(String(reqId))) {
                const pending = pendingTextAcksRef.current.get(String(reqId));
                if (pending) {
                  window.clearTimeout(pending.timer);
                  pending.resolve({
                    success: Boolean(success),
                    status: String(status || (success ? 'ACCEPTED' : 'REJECTED')),
                    message: message ? String(message) : undefined,
                    requestId: String(reqId),
                  });
                }
                pendingTextAcksRef.current.delete(String(reqId));
              }
            }
          } catch (err) {
            console.warn('[BRIDGE] Error parsing telemetry message:', err);
          }
        };

        ws.onerror = () => {
          if (!isMountedRef.current) return;
          pendingTextAcksRef.current.forEach((pending) => {
            window.clearTimeout(pending.timer);
            pending.resolve({ success: false, status: 'DISCONNECTED', message: 'Bridge WebSocket error' });
          });
          pendingTextAcksRef.current.clear();
          setBridgeStatus('ERROR');
          setLiveVoiceState(DEFAULT_VOICE_STATE);
          setLiveActiveAction((prev) => ({
            ...prev,
            isPlaying: false,
            playbackState: prev.playbackState === 'PLAYING' ? 'PAUSED' : prev.playbackState,
          }));
          setLiveAiCoreData((prev) => ({
            ...prev,
            gatewayStatus: 'ERROR',
            runtimeState: 'ERROR',
            inFlightRequests: 0,
            systemState: 'ERROR',
          }));
        };

        ws.onclose = () => {
          if (!isMountedRef.current) return;
          pendingTextAcksRef.current.forEach((pending) => {
            window.clearTimeout(pending.timer);
            pending.resolve({ success: false, status: 'DISCONNECTED', message: 'Bridge WebSocket connection closed' });
          });
          pendingTextAcksRef.current.clear();
          setBridgeStatus('DISCONNECTED');
          setLiveVoiceState(DEFAULT_VOICE_STATE);
          setLiveActiveAction((prev) => ({
            ...prev,
            isPlaying: false,
            playbackState: prev.playbackState === 'PLAYING' ? 'PAUSED' : prev.playbackState,
          }));
          setLiveAiCoreData((prev) => ({
            ...prev,
            gatewayStatus: 'DISCONNECTED',
            runtimeState: 'IDLE',
            inFlightRequests: 0,
            systemState: 'STANDBY',
          }));
          wsRef.current = null;

          // Schedule reconnection with bounded backoff
          const delay = reconnectDelayRef.current;
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 1.5, MAX_RECONNECT_DELAY_MS);
          reconnectTimeoutRef.current = window.setTimeout(connect, delay);
        };
      } catch (err) {
        if (!isMountedRef.current) return;
        setBridgeStatus('ERROR');
        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 1.5, MAX_RECONNECT_DELAY_MS);
        reconnectTimeoutRef.current = window.setTimeout(connect, delay);
      }
    }

    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return {
    bridgeStatus,
    liveMetrics,
    liveProcessWatcher,
    liveAiCoreData,
    conversationLog,
    liveVoiceState,
    liveActiveAction,
    livePlaylistState,
    isMicActive,
    addLocalMessage,
    clearConversation,
    sendMusicControl,
    sendPlaylistControl,
    sendMicControl,
    sendTextCommand,
  };
}

