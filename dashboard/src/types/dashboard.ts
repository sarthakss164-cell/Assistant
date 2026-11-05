export type BridgeStatus = 'CONNECTING' | 'ONLINE' | 'DISCONNECTED' | 'ERROR';

export interface SystemMetrics {
  ramUsedGb: number;
  ramTotalGb: number;
  ramPercent: number;
  cpuPercent: number;
  cpuHistory: number[]; // Last 20 points for sparkline
  storageUsedGb: number;
  storageTotalGb: number;
  storagePercent: number;
  storageDrive?: string;
  batteryPercent: number | null;
  batteryCharging: boolean;
  hasBattery?: boolean;
}

export interface ProcessWatcher {
  foregroundApp: string;
  foregroundPid?: number | null;
  activeProcess: string;
  activeProcessPid: number | null;
  toolLatencyMs: number | null;
}

export type GatewayStatus = 'ONLINE' | 'STANDBY' | 'PROCESSING' | 'ERROR' | 'DISCONNECTED';
export type AiRuntimeState = 'IDLE' | 'PROCESSING' | 'SUCCESS' | 'ERROR';
export type SessionMemoryStatus = 'EMPTY' | 'ACTIVE' | 'MAX_CAPACITY' | 'DISABLED';

export interface TokenUsageMetrics {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface AiCoreData {
  // Legacy / Compatibility fields
  engine: string;
  activePersona: string;
  contextWindowUsed: number;
  contextWindowTotal: number;
  uptimeSeconds: number;
  actionsExecutedCount: number;
  systemState: 'ONLINE' | 'STANDBY' | 'BUSY' | 'ERROR';

  // Live Telemetry fields
  configuredModel: string;
  resolvedModel: string;
  provider: string;
  gatewayStatus: GatewayStatus;
  runtimeState: AiRuntimeState;
  inFlightRequests: number;
  lastTokens: TokenUsageMetrics;
  sessionTokens: TokenUsageMetrics;
  contextCapacity: number | null;
  remainingTokens: number | null;
  utilizationPercentage: number | null;
  lastRequestLatencyMs: number | null;
  lastSuccessfulLatencyMs: number | null;
  avgLatencyMs: number | null;
  recentLatenciesMs: number[];
  successCount: number;
  failureCount: number;
  lastSuccessTimestamp: number | null;
  lastRequestStatus: string | null;
  lastErrorCategory: string | null;
  historyIncluded: boolean;
  sessionMemoryTurns: number;
  sessionMemoryMaxTurns: number;
  sessionMemoryAvailable: boolean;
  sessionMemoryStatus: SessionMemoryStatus;
}

export type MusicPlaybackState = 'IDLE' | 'LOADING' | 'PLAYING' | 'PAUSED' | 'STOPPED' | 'ERROR';

export interface ActiveAction {
  type: 'IDLE' | 'MUSIC' | 'APP_LAUNCH' | 'SEARCH' | 'WHATSAPP';
  title: string;
  subtitle: string;
  durationSeconds: number;
  positionSeconds: number;
  isPlaying: boolean;
  source: string;
  playbackState?: MusicPlaybackState;
  lastPlayed?: string | null;
  volume?: number;
  isMuted?: boolean;
}

export interface ConversationItem {
  id: string;
  sender: 'USER' | 'ASSISTANT';
  text: string;
  timestamp: string;
  status?: 'RECOGNIZED' | 'SPEAKING' | 'COMPLETED';
}

export interface VoiceState {
  userState: 'IDLE' | 'LISTENING' | 'PROCESSING' | 'RECOGNIZING';
  aiState: 'STANDBY' | 'SPEAKING' | 'ERROR' | 'IDLE' | 'SYNTHESIZING';
  recognizedUtterance: string;
  spokenResponse: string;
  userActivityLevel: number;
  aiActivityLevel: number;
}

export interface AudioOutputs {
  volumePercent: number;
  isMuted: boolean;
  isMicActive: boolean;
}

export interface PlaylistEntry {
  id: string;
  title: string;
  query?: string;
}

export interface PlaylistState {
  hasActiveSession: boolean;
  playlistId: string | null;
  name: string | null;
  entries: PlaylistEntry[];
  currentIndex: number;
  isShuffle: boolean;
  state: 'IDLE' | 'PLAYING' | 'PAUSED' | 'COMPLETED' | 'STOPPED';
  revision: number;
}

export interface TextCommandAckResult {
  success: boolean;
  status: string;
  message?: string;
  requestId?: string;
}

export interface DashboardState {
  systemMetrics: SystemMetrics;
  processWatcher: ProcessWatcher;
  aiCoreData: AiCoreData;
  activeAction: ActiveAction;
  conversationLog: ConversationItem[];
  voiceState: VoiceState;
  audioOutputs: AudioOutputs;
  bridgeStatus?: BridgeStatus;
}
