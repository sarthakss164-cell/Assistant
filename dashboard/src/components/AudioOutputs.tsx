import React from 'react';
import { HudPanel } from './HudPanel';
import { Volume2, VolumeX, Mic, MicOff, Sliders } from 'lucide-react';
import { AudioOutputs as AudioOutputsType } from '../types/dashboard';

interface AudioOutputsProps {
  data: AudioOutputsType;
  onVolumeChange?: (newVol: number) => void;
  onToggleMute?: () => void;
  onToggleMic?: () => void;
}

export const AudioOutputs: React.FC<AudioOutputsProps> = ({
  data,
  onVolumeChange,
  onToggleMute,
  onToggleMic,
}) => {
  return (
    <HudPanel title="Audio I/O Control" icon={<Sliders size={14} />} tag="HARDWARE">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Master Volume Slider */}
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '11px',
              marginBottom: '4px',
            }}
          >
            <span className="font-hud" style={{ color: 'var(--text-secondary)' }}>
              MASTER OUTPUT GAIN
            </span>
            <span className="font-mono" style={{ color: 'var(--accent-gold)' }}>
              {data.isMuted ? 'MUTED' : `${data.volumePercent}%`}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={onToggleMute}
              title={data.isMuted ? 'Unmute' : 'Mute'}
              style={{
                background: 'transparent',
                border: 'none',
                color: data.isMuted ? 'var(--accent-orange)' : 'var(--accent-gold)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {data.isMuted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            </button>
            <input
              type="range"
              min="0"
              max="100"
              value={data.isMuted ? 0 : data.volumePercent}
              onChange={(e) => onVolumeChange && onVolumeChange(Number(e.target.value))}
              style={{
                flex: 1,
                accentColor: 'var(--accent-gold)',
                cursor: 'pointer',
              }}
            />
          </div>
        </div>

        {/* Input Microphone State */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(0, 0, 0, 0.3)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 10px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {data.isMicActive ? (
              <Mic size={14} style={{ color: '#28e070' }} />
            ) : (
              <MicOff size={14} style={{ color: 'var(--accent-orange)' }} />
            )}
            <span className="font-hud" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              MIC INPUT (PTT / SPEECH GATE)
            </span>
          </div>
          <button
            onClick={onToggleMic}
            className="font-mono"
            style={{
              fontSize: '10px',
              padding: '2px 8px',
              borderRadius: '2px',
              background: data.isMicActive ? 'rgba(40, 224, 112, 0.15)' : 'rgba(255, 72, 0, 0.15)',
              border: data.isMicActive
                ? '1px solid rgba(40, 224, 112, 0.4)'
                : '1px solid rgba(255, 72, 0, 0.4)',
              color: data.isMicActive ? '#28e070' : 'var(--accent-orange)',
              cursor: 'pointer',
            }}
          >
            {data.isMicActive ? 'ACTIVE' : 'MUTED'}
          </button>
        </div>
      </div>
    </HudPanel>
  );
};
