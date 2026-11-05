import React, { useState, useEffect } from 'react';
import { HeaderBar } from './components/HeaderBar';
import { SystemMetrics } from './components/SystemMetrics';
import { ProcessWatcher } from './components/ProcessWatcher';
import { AiCoreData } from './components/AiCoreData';
import { ThreeOrb } from './components/ThreeOrb';
import { ActiveAction } from './components/ActiveAction';
import { ConversationLog } from './components/ConversationLog';
import { PlaylistPanel } from './components/PlaylistPanel';
import { VoiceMonitor } from './components/VoiceMonitor';
import { DateTimeWeather } from './components/DateTimeWeather';
import { AudioOutputs } from './components/AudioOutputs';
import { TextCommandConsole } from './components/TextCommandConsole';
import { PanicAbortButton } from './components/PanicAbortButton';
import { DashboardState } from './types/dashboard';
import { useTelemetryBridge, DEFAULT_AI_CORE_DATA } from './hooks/useTelemetryBridge';

// Initial realistic placeholder state (decoupled for Phase A/B visual shell)
const INITIAL_STATE: DashboardState = {
  systemMetrics: {
    ramUsedGb: 14.2,
    ramTotalGb: 32.0,
    ramPercent: 44,
    cpuPercent: 28,
    cpuHistory: [18, 22, 19, 35, 42, 28, 30, 25, 48, 55, 38, 26, 29, 32, 28, 24, 30, 27, 28, 28],
    storageUsedGb: 384,
    storageTotalGb: 1000,
    storagePercent: 38,
    batteryPercent: 92,
    batteryCharging: true,
  },
  processWatcher: {
    foregroundApp: 'BRAVE BROWSER (LIGHT AI DOCUMENTATION)',
    activeProcess: 'yt-dlp.exe (AUDIO EXTRACTOR)',
    activeProcessPid: 14280,
    toolLatencyMs: 22,
  },
  aiCoreData: DEFAULT_AI_CORE_DATA,
  activeAction: {
    type: 'IDLE',
    title: 'NO ACTIVE PLAYBACK',
    subtitle: 'STANDBY // READY FOR AUDIO',
    durationSeconds: 0,
    positionSeconds: 0,
    isPlaying: false,
    source: 'YouTube',
    playbackState: 'IDLE',
    lastPlayed: null,
  },
  conversationLog: [
    {
      id: 'log-1',
      sender: 'USER',
      text: 'Light, open Brave and search for latest quantum computing breakthroughs.',
      timestamp: '19:42:10',
    },
    {
      id: 'log-2',
      sender: 'ASSISTANT',
      text: 'Opening Brave and searching for recent quantum computing breakthroughs.',
      timestamp: '19:42:12',
    },
    {
      id: 'log-3',
      sender: 'USER',
      text: 'Play Channa Mereya by Arijit Singh.',
      timestamp: '19:45:02',
    },
    {
      id: 'log-4',
      sender: 'ASSISTANT',
      text: 'Streaming Channa Mereya by Arijit Singh on custom music player.',
      timestamp: '19:45:05',
    },
  ],
  voiceState: {
    userState: 'IDLE',
    aiState: 'IDLE',
    recognizedUtterance: 'play channa mereya by arijit singh',
    spokenResponse: 'Streaming Channa Mereya by Arijit Singh on custom music player.',
    userActivityLevel: 0.15,
    aiActivityLevel: 0.1,
  },
  audioOutputs: {
    volumePercent: 78,
    isMuted: false,
    isMicActive: true,
  },
};

export const App: React.FC = () => {
  const [state, setState] = useState<DashboardState>(INITIAL_STATE);
  const {
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
    sendMusicControl,
    sendPlaylistControl,
    sendMicControl,
    sendTextCommand,
  } = useTelemetryBridge();

  // Keep AudioOutputs synchronized with authoritative music player volume & mute
  useEffect(() => {
    if (liveActiveAction.volume !== undefined || liveActiveAction.isMuted !== undefined) {
      setState((prev) => {
        const nextVol = liveActiveAction.volume !== undefined ? liveActiveAction.volume : prev.audioOutputs.volumePercent;
        const nextMute = liveActiveAction.isMuted !== undefined ? liveActiveAction.isMuted : prev.audioOutputs.isMuted;
        if (prev.audioOutputs.volumePercent === nextVol && prev.audioOutputs.isMuted === nextMute) {
          return prev;
        }
        return {
          ...prev,
          audioOutputs: {
            ...prev.audioOutputs,
            volumePercent: nextVol,
            isMuted: nextMute,
          },
        };
      });
    }
  }, [liveActiveAction.volume, liveActiveAction.isMuted]);

  // Keep AudioOutputs synchronized with authoritative mic state
  useEffect(() => {
    setState((prev) => {
      if (prev.audioOutputs.isMicActive === isMicActive) return prev;
      return {
        ...prev,
        audioOutputs: {
          ...prev.audioOutputs,
          isMicActive,
        },
      };
    });
  }, [isMicActive]);

  const handleTogglePlay = () => {
    sendMusicControl('toggle_play');
  };

  const handleNext = () => {
    sendMusicControl('next');
  };

  const handlePrev = () => {
    sendMusicControl('previous');
  };

  const handleVolumeChange = (vol: number) => {
    sendMusicControl('volume', vol);
    setState((prev) => ({
      ...prev,
      audioOutputs: { ...prev.audioOutputs, volumePercent: vol, isMuted: false },
    }));
  };

  const handleToggleMute = () => {
    const nextMuted = !state.audioOutputs.isMuted;
    sendMusicControl('mute', nextMuted);
    setState((prev) => ({
      ...prev,
      audioOutputs: { ...prev.audioOutputs, isMuted: nextMuted },
    }));
  };

  const handleToggleMic = () => {
    const nextActive = !state.audioOutputs.isMicActive;
    sendMicControl(nextActive);
    setState((prev) => ({
      ...prev,
      audioOutputs: { ...prev.audioOutputs, isMicActive: nextActive },
    }));
  };

  const handlePanicAbort = () => {
    sendMusicControl('stop');
    setState((prev) => ({
      ...prev,
      activeAction: {
        ...prev.activeAction,
        isPlaying: false,
      },
      voiceState: {
        ...prev.voiceState,
        userState: 'IDLE',
        aiState: 'IDLE',
      },
    }));

    addLocalMessage({
      id: `abort-${Date.now()}`,
      sender: 'ASSISTANT',
      text: '[SAFEGUARD ACTIVATED] Non-destructive abort dispatched: Music stopped and pending requests cleared.',
      timestamp: new Date().toTimeString().substring(0, 8),
      status: 'COMPLETED',
    });

    // If electron bridge is available, notify electron
    if ((window as any).electronAPI?.sendAction) {
      (window as any).electronAPI.sendAction('PANIC_ABORT', {});
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Subtle scanline animation */}
      <div className="hud-scanline" />

      {/* Top Header Bar */}
      <HeaderBar bridgeStatus={bridgeStatus} />

      {/* Main Grid Content */}
      <main
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '320px 1.4fr 1.1fr 340px',
          gap: '12px',
          padding: '12px',
          overflow: 'hidden',
        }}
      >
        {/* COLUMN 1: System Metrics & Process Watcher & AI Core Data */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflow: 'hidden',
            height: '100%',
          }}
        >
          <div style={{ flexShrink: 0 }}>
            <SystemMetrics metrics={liveMetrics || state.systemMetrics} />
          </div>
          <ProcessWatcher data={liveProcessWatcher || state.processWatcher} />
          <AiCoreData data={liveAiCoreData || state.aiCoreData} />
        </div>

        {/* COLUMN 2: 3D Orb Stage & Active Action Music Player */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflow: 'hidden',
          }}
        >
          {/* Orb HUD Panel */}
          <div
            className="hud-panel"
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              position: 'relative',
              background: 'radial-gradient(circle at 50% 45%, rgba(40, 28, 16, 0.45) 0%, rgba(14, 10, 6, 0.95) 80%)',
            }}
          >
            {/* Orb Stage Header */}
            <div className="panel-header">
              <span className="panel-title">AI CORE // DYNAMIC ACTION STAGE</span>
              <span className="panel-tag font-mono">THREE.JS WEBGL</span>
            </div>

            {/* Genuine Three.js 3D Orb Canvas */}
            <div style={{ flex: 1, position: 'relative', minHeight: '340px' }}>
              <ThreeOrb
                activityLevel={liveVoiceState.aiActivityLevel}
                systemState={liveAiCoreData?.systemState || state.aiCoreData.systemState}
              />

              {/* Status pill under orb */}
              <div
                style={{
                  position: 'absolute',
                  bottom: '12px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  background: 'rgba(18, 14, 9, 0.85)',
                  border: '1px solid var(--border-gold-medium)',
                  padding: '4px 14px',
                  borderRadius: '16px',
                  boxShadow: 'var(--glow-gold-sm)',
                }}
              >
                <span
                  className="animate-pulse-glow"
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--accent-gold)',
                  }}
                />
                <span
                  className="font-mono glow-gold"
                  style={{
                    fontSize: '11px',
                    fontWeight: 700,
                    color: 'var(--accent-gold)',
                    letterSpacing: '0.1em',
                  }}
                >
                  SYSTEM: ONLINE - LISTENING
                </span>
              </div>
            </div>
          </div>

          {/* Active Action Player */}
          <ActiveAction
            action={liveActiveAction || state.activeAction}
            onTogglePlay={handleTogglePlay}
            onNext={handleNext}
            onPrev={handlePrev}
            canNavigate={livePlaylistState.hasActiveSession}
          />
        </div>

        {/* COLUMN 3: Conversation Log & Playlist System */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflow: 'hidden',
            height: '100%',
          }}
        >
          <div style={{ flex: '1 1 50%', minHeight: 0, overflow: 'hidden' }}>
            <ConversationLog logs={conversationLog} />
          </div>
          <div style={{ flex: '1 1 50%', minHeight: 0, overflow: 'hidden' }}>
            <PlaylistPanel
              playlist={livePlaylistState}
              onSelectSong={(index) => sendPlaylistControl('select_song', { index })}
              onToggleShuffle={() => sendPlaylistControl('toggle_shuffle')}
              onStopPlaylist={() => sendPlaylistControl('stop')}
            />
          </div>
        </div>

        {/* COLUMN 4: Chrono/Weather, Voice Monitor, Audio Outputs, Panic Button */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflowY: 'auto',
          }}
        >
          <DateTimeWeather />
          <VoiceMonitor voiceState={liveVoiceState} />
          <AudioOutputs
            data={state.audioOutputs}
            onVolumeChange={handleVolumeChange}
            onToggleMute={handleToggleMute}
            onToggleMic={handleToggleMic}
          />
          <TextCommandConsole
            onSendCommand={sendTextCommand}
            bridgeStatus={bridgeStatus}
          />
          <PanicAbortButton onAbort={handlePanicAbort} />
        </div>
      </main>
    </div>
  );
};
export default App;
