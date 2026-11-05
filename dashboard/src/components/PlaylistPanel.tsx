import React from 'react';
import { HudPanel } from './HudPanel';
import { ListMusic, Shuffle, Square, Play, Pause, Check } from 'lucide-react';
import { PlaylistState } from '../types/dashboard';

interface PlaylistPanelProps {
  playlist: PlaylistState;
  onSelectSong: (index: number) => void;
  onToggleShuffle: () => void;
  onStopPlaylist: () => void;
}

export const PlaylistPanel: React.FC<PlaylistPanelProps> = ({
  playlist,
  onSelectSong,
  onToggleShuffle,
  onStopPlaylist,
}) => {
  const hasActiveSession = playlist.hasActiveSession && playlist.entries.length > 0;
  const playlistName = playlist.name ? playlist.name.toUpperCase() : 'NO ACTIVE PLAYLIST';

  const getStatusBadge = () => {
    if (!hasActiveSession) {
      return (
        <span
          className="font-mono"
          style={{
            fontSize: '9px',
            padding: '2px 6px',
            borderRadius: '2px',
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            color: 'var(--text-muted)',
            letterSpacing: '0.08em',
          }}
        >
          IDLE
        </span>
      );
    }

    let bg = 'rgba(245, 175, 55, 0.15)';
    let border = 'rgba(245, 175, 55, 0.4)';
    let color = 'var(--accent-gold)';

    if (playlist.state === 'PLAYING') {
      bg = 'rgba(40, 224, 112, 0.15)';
      border = 'rgba(40, 224, 112, 0.4)';
      color = '#28e070';
    } else if (playlist.state === 'COMPLETED') {
      bg = 'rgba(56, 189, 248, 0.15)';
      border = 'rgba(56, 189, 248, 0.4)';
      color = '#38bdf8';
    } else if (playlist.state === 'STOPPED') {
      bg = 'rgba(255, 72, 0, 0.12)';
      border = 'rgba(255, 72, 0, 0.4)';
      color = 'var(--accent-orange)';
    }

    return (
      <span
        className="font-mono"
        style={{
          fontSize: '9px',
          padding: '2px 6px',
          borderRadius: '2px',
          background: bg,
          border: `1px solid ${border}`,
          color,
          letterSpacing: '0.08em',
          fontWeight: 700,
        }}
      >
        {playlist.state}
      </span>
    );
  };

  return (
    <HudPanel
      title="Playlist System"
      icon={<ListMusic size={14} />}
      tag="SPOTIFY HUD"
      style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}
      contentStyle={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}
    >
      {/* Subheader: Playlist Name, Status & Shuffle Toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingBottom: '8px',
          marginBottom: '8px',
          borderBottom: '1px solid var(--border-gold-subtle)',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
          <span
            className="font-hud"
            style={{
              fontSize: '11px',
              fontWeight: 700,
              color: hasActiveSession ? 'var(--accent-gold)' : 'var(--text-muted)',
              letterSpacing: '0.08em',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {playlistName}
          </span>
          {getStatusBadge()}
        </div>

        <button
          onClick={onToggleShuffle}
          disabled={!hasActiveSession}
          title={playlist.isShuffle ? 'Disable Shuffle' : 'Enable Shuffle'}
          className="font-mono"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '9px',
            padding: '3px 8px',
            borderRadius: '2px',
            background: playlist.isShuffle ? 'rgba(245, 175, 55, 0.22)' : 'rgba(0, 0, 0, 0.3)',
            border: playlist.isShuffle
              ? '1px solid rgba(245, 175, 55, 0.5)'
              : '1px solid var(--border-gold-subtle)',
            color: playlist.isShuffle ? 'var(--accent-gold)' : 'var(--text-muted)',
            cursor: hasActiveSession ? 'pointer' : 'not-allowed',
            opacity: hasActiveSession ? 1 : 0.4,
            transition: 'all 0.15s ease',
          }}
        >
          <Shuffle size={11} />
          <span>SHUFFLE: {playlist.isShuffle ? 'ON' : 'OFF'}</span>
        </button>
      </div>

      {/* Main Track List */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          minHeight: 0,
          paddingRight: '4px',
        }}
      >
        {!hasActiveSession ? (
          <div
            style={{
              padding: '28px 16px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '11px',
              letterSpacing: '0.12em',
              border: '1px dashed rgba(245, 175, 55, 0.2)',
              borderRadius: '4px',
              background: 'rgba(20, 15, 10, 0.4)',
              margin: 'auto 0',
            }}
            className="font-mono"
          >
            <div>NO ACTIVE PLAYLIST</div>
            <div style={{ fontSize: '9px', marginTop: '6px', opacity: 0.7 }}>
              SAY &quot;PLAY HINDI PLAYLIST&quot; OR &quot;PLAY ENGLISH PLAYLIST&quot;
            </div>
          </div>
        ) : (
          playlist.entries.map((entry, idx) => {
            const isActive = idx === playlist.currentIndex;
            const isPlaying = isActive && playlist.state === 'PLAYING';
            const isPaused = isActive && playlist.state === 'PAUSED';
            const isCompleted = isActive && playlist.state === 'COMPLETED';

            return (
              <div
                key={entry.id || idx}
                onClick={() => onSelectSong(idx)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '6px 8px',
                  borderRadius: '3px',
                  background: isActive
                    ? 'rgba(245, 175, 55, 0.16)'
                    : 'rgba(18, 14, 9, 0.45)',
                  border: isActive
                    ? '1px solid rgba(245, 175, 55, 0.5)'
                    : '1px solid rgba(245, 175, 55, 0.08)',
                  boxShadow: isActive ? '0 0 10px rgba(245, 175, 55, 0.15)' : 'none',
                  cursor: 'pointer',
                  transition: 'background 0.15s ease, border-color 0.15s ease',
                  gap: '8px',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'rgba(245, 175, 55, 0.08)';
                    e.currentTarget.style.borderColor = 'rgba(245, 175, 55, 0.25)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'rgba(18, 14, 9, 0.45)';
                    e.currentTarget.style.borderColor = 'rgba(245, 175, 55, 0.08)';
                  }
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
                  {/* Track Number */}
                  <span
                    className="font-mono"
                    style={{
                      fontSize: '10px',
                      color: isActive ? 'var(--accent-gold)' : 'var(--text-muted)',
                      width: '24px',
                      flexShrink: 0,
                    }}
                  >
                    #{String(idx + 1).padStart(2, '0')}
                  </span>

                  {/* Icon Indicator */}
                  <div style={{ width: '12px', flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                    {isPlaying && <Play size={11} fill="#28e070" color="#28e070" />}
                    {isPaused && <Pause size={11} fill="var(--accent-gold)" color="var(--accent-gold)" />}
                    {isCompleted && <Check size={11} color="#38bdf8" />}
                    {!isActive && (
                      <span
                        style={{
                          width: '4px',
                          height: '4px',
                          borderRadius: '50%',
                          background: 'rgba(255, 255, 255, 0.2)',
                          display: 'inline-block',
                          marginLeft: '3px',
                        }}
                      />
                    )}
                  </div>

                  {/* Title */}
                  <span
                    style={{
                      fontSize: '11px',
                      color: isActive ? '#ffffff' : 'var(--text-secondary)',
                      fontWeight: isActive ? 600 : 400,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {entry.title}
                  </span>
                </div>

                {/* Right Quick-Play Action Hint */}
                <span
                  className="font-mono"
                  style={{
                    fontSize: '9px',
                    color: isActive ? 'var(--accent-gold)' : 'var(--text-muted)',
                    opacity: isActive ? 1 : 0.6,
                    flexShrink: 0,
                  }}
                >
                  {isActive ? (isPlaying ? 'ACTIVE' : 'PAUSED') : 'CLICK TO PLAY'}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* Footer / Controls: Stop Playlist Button & Track Count */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingTop: '8px',
          marginTop: '8px',
          borderTop: '1px solid var(--border-gold-subtle)',
        }}
      >
        <button
          onClick={onStopPlaylist}
          disabled={!hasActiveSession}
          className="font-mono"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '10px',
            padding: '4px 10px',
            borderRadius: '2px',
            background: hasActiveSession ? 'rgba(255, 72, 0, 0.15)' : 'rgba(0, 0, 0, 0.2)',
            border: hasActiveSession
              ? '1px solid rgba(255, 72, 0, 0.4)'
              : '1px solid rgba(255, 255, 255, 0.08)',
            color: hasActiveSession ? 'var(--accent-orange)' : 'var(--text-muted)',
            cursor: hasActiveSession ? 'pointer' : 'not-allowed',
            opacity: hasActiveSession ? 1 : 0.4,
            fontWeight: 700,
            letterSpacing: '0.08em',
            transition: 'all 0.15s ease',
          }}
        >
          <Square size={10} fill={hasActiveSession ? 'var(--accent-orange)' : 'transparent'} />
          <span>STOP PLAYLIST</span>
        </button>

        <span
          className="font-mono"
          style={{
            fontSize: '10px',
            color: 'var(--text-muted)',
            letterSpacing: '0.08em',
          }}
        >
          {hasActiveSession ? `${playlist.entries.length} TRACKS` : '0 TRACKS'}
        </span>
      </div>
    </HudPanel>
  );
};

