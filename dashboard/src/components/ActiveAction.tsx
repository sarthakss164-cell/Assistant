import React from 'react';
import { Play, Pause, SkipBack, SkipForward, Shuffle, Repeat, Music2 } from 'lucide-react';
import { ActiveAction as ActiveActionType } from '../types/dashboard';

interface ActiveActionProps {
  action: ActiveActionType;
  onTogglePlay?: () => void;
  onNext?: () => void;
  onPrev?: () => void;
  canNavigate?: boolean;
}

export const ActiveAction: React.FC<ActiveActionProps> = ({
  action,
  onTogglePlay,
  onNext,
  onPrev,
  canNavigate = true,
}) => {
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const progressPercent = action.durationSeconds > 0
    ? (action.positionSeconds / action.durationSeconds) * 100
    : 0;

  const playbackState = action.playbackState || (action.isPlaying ? 'PLAYING' : 'IDLE');

  let statusColor = 'var(--accent-gold)';
  let dotColor = 'var(--accent-gold)';
  let dotGlow = 'var(--glow-gold-sm)';
  const statusText = playbackState;

  if (playbackState === 'PLAYING') {
    statusColor = '#28e070';
    dotColor = '#28e070';
    dotGlow = '0 0 8px #28e070';
  } else if (playbackState === 'LOADING') {
    statusColor = 'var(--accent-gold)';
    dotColor = '#f5af37';
    dotGlow = '0 0 8px rgba(245, 175, 55, 0.8)';
  } else if (playbackState === 'PAUSED') {
    statusColor = 'var(--accent-gold)';
    dotColor = '#f5af37';
    dotGlow = 'var(--glow-gold-sm)';
  } else if (playbackState === 'STOPPED') {
    statusColor = 'var(--text-muted)';
    dotColor = '#777777';
    dotGlow = 'none';
  } else if (playbackState === 'ERROR') {
    statusColor = '#ef4444';
    dotColor = '#ef4444';
    dotGlow = '0 0 8px rgba(239, 68, 68, 0.8)';
  } else {
    // IDLE
    statusColor = 'var(--text-muted)';
    dotColor = '#555555';
    dotGlow = 'none';
  }

  return (
    <div
      style={{
        background: 'rgba(22, 17, 11, 0.88)',
        backdropFilter: 'blur(16px)',
        border: '1px solid var(--border-gold-subtle)',
        borderRadius: '6px',
        padding: '12px 16px',
        boxShadow: 'var(--shadow-panel)',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-gold-subtle)',
          paddingBottom: '6px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Music2 size={13} style={{ color: 'var(--accent-gold)' }} />
          <span
            className="font-display"
            style={{ fontSize: '11px', fontWeight: 700, color: 'var(--accent-gold)', letterSpacing: '0.1em' }}
          >
            ACTIVE ACTION
          </span>
        </div>
        <span
          className="font-mono"
          style={{
            fontSize: '9px',
            color: 'var(--text-muted)',
            background: 'rgba(0, 0, 0, 0.4)',
            padding: '1px 6px',
            borderRadius: '2px',
            border: '1px solid var(--border-gold-subtle)',
          }}
        >
          {action.source}
        </span>
      </div>

      {/* Track & Artist Info */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div
            className="font-hud glow-gold"
            style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}
          >
            {action.title}
          </div>
          <div
            className="font-mono"
            style={{ fontSize: '11px', color: 'var(--text-secondary)' }}
          >
            {action.subtitle}
          </div>
        </div>

        {/* Action Status Pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'rgba(245, 175, 55, 0.1)',
            border: '1px solid var(--border-gold-medium)',
            padding: '2px 8px',
            borderRadius: '10px',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: dotColor,
              boxShadow: dotGlow,
            }}
          />
          <span className="font-mono" style={{ fontSize: '9px', color: statusColor, letterSpacing: '0.05em' }}>
            {statusText}
          </span>
        </div>
      </div>

      {/* Progress Bar & Timestamps */}
      <div>
        <div
          style={{
            height: '4px',
            background: 'rgba(245, 175, 55, 0.15)',
            borderRadius: '2px',
            overflow: 'hidden',
            marginBottom: '4px',
            cursor: 'default',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${progressPercent}%`,
              background: 'linear-gradient(90deg, var(--accent-bronze), var(--accent-gold))',
              boxShadow: '0 0 8px rgba(245, 175, 55, 0.6)',
              transition: 'width 0.25s linear',
            }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '10px',
            color: 'var(--text-muted)',
          }}
          className="font-mono"
        >
          <span>{formatTime(action.positionSeconds)}</span>
          <span>{formatTime(action.durationSeconds)}</span>
        </div>
      </div>

      {/* Controls Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '14px',
          paddingTop: '4px',
        }}
      >
        <button
          title="Shuffle"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
          }}
        >
          <Shuffle size={14} />
        </button>

        <button
          onClick={canNavigate ? onPrev : undefined}
          disabled={!canNavigate}
          title={canNavigate ? "Previous Track" : "Navigation disabled (Standalone mode)"}
          style={{
            background: 'transparent',
            border: 'none',
            color: canNavigate ? 'var(--text-secondary)' : 'var(--text-muted)',
            cursor: canNavigate ? 'pointer' : 'not-allowed',
            opacity: canNavigate ? 1 : 0.35,
          }}
        >
          <SkipBack size={16} />
        </button>

        <button
          onClick={onTogglePlay}
          title={action.isPlaying ? 'Pause' : 'Play'}
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, var(--accent-gold), var(--accent-orange))',
            border: 'none',
            color: '#070604',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: 'var(--glow-gold-sm)',
            transition: 'transform 0.15s ease',
          }}
          onMouseDown={(e) => (e.currentTarget.style.transform = 'scale(0.92)')}
          onMouseUp={(e) => (e.currentTarget.style.transform = 'scale(1)')}
        >
          {action.isPlaying ? <Pause size={16} /> : <Play size={16} style={{ marginLeft: '2px' }} />}
        </button>

        <button
          onClick={canNavigate ? onNext : undefined}
          disabled={!canNavigate}
          title={canNavigate ? "Next Track" : "Navigation disabled (Standalone mode)"}
          style={{
            background: 'transparent',
            border: 'none',
            color: canNavigate ? 'var(--text-secondary)' : 'var(--text-muted)',
            cursor: canNavigate ? 'pointer' : 'not-allowed',
            opacity: canNavigate ? 1 : 0.35,
          }}
        >
          <SkipForward size={16} />
        </button>

        <button
          title="Repeat"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
          }}
        >
          <Repeat size={14} />
        </button>
      </div>
    </div>
  );
};
