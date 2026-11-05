import React, { useEffect, useRef } from 'react';
import { HudPanel } from './HudPanel';
import { Mic, Volume2 } from 'lucide-react';
import { VoiceState } from '../types/dashboard';

interface VoiceMonitorProps {
  voiceState: VoiceState;
}

// Waveform Canvas component drawing animated audio spectrum bars
const WaveformVisualizer: React.FC<{
  isActive: boolean;
  color: string;
  barCount?: number;
}> = ({ isActive, color, barCount = 28 }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const barWidth = width / barCount - 2;

    // When inactive, render flat resting baseline dots once without running animation loop
    if (!isActive) {
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = 'rgba(245, 175, 55, 0.18)';
      ctx.shadowBlur = 0;
      for (let i = 0; i < barCount; i++) {
        const x = i * (barWidth + 2);
        const y = (height - 2) / 2;
        ctx.fillRect(x, y, barWidth, 2);
      }
      return;
    }

    let animId: number;
    let phase = 0;

    const render = () => {
      phase += 0.08;
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < barCount; i++) {
        const sine = Math.sin(phase + i * 0.35);
        const noise = Math.cos(phase * 1.5 + i * 0.6);
        const factor = Math.abs(sine * 0.7 + noise * 0.3);
        const barHeight = Math.max(4, factor * (height - 6));

        const x = i * (barWidth + 2);
        const y = (height - barHeight) / 2;

        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 8;
        ctx.fillRect(x, y, barWidth, barHeight);
      }

      animId = requestAnimationFrame(render);
    };

    render();

    return () => cancelAnimationFrame(animId);
  }, [isActive, color, barCount]);

  return (
    <canvas
      ref={canvasRef}
      width={280}
      height={36}
      style={{
        width: '100%',
        height: '36px',
        background: 'rgba(0, 0, 0, 0.4)',
        borderRadius: '2px',
        border: '1px solid var(--border-gold-subtle)',
      }}
    />
  );
};

export const VoiceMonitor: React.FC<VoiceMonitorProps> = ({ voiceState }) => {
  const isUserListening = voiceState.userState === 'LISTENING';
  const isUserProcessing = voiceState.userState === 'PROCESSING';
  const isAiSpeaking = voiceState.aiState === 'SPEAKING';
  const isAiError = voiceState.aiState === 'ERROR';

  const userStatusLabel = isUserListening
    ? '[LISTENING]'
    : isUserProcessing
    ? '[PROCESSING]'
    : '[IDLE]';

  const userStatusColor = isUserListening
    ? '#28e070'
    : isUserProcessing
    ? 'var(--accent-gold)'
    : 'var(--text-muted)';

  const userStatusBg = isUserListening
    ? 'rgba(40, 224, 112, 0.12)'
    : isUserProcessing
    ? 'rgba(245, 175, 55, 0.12)'
    : 'transparent';

  const aiStatusLabel = isAiSpeaking
    ? '[SPEAKING]'
    : isAiError
    ? '[ERROR]'
    : '[STANDBY]';

  const aiStatusColor = isAiSpeaking
    ? 'var(--accent-orange)'
    : isAiError
    ? '#ff4800'
    : 'var(--text-muted)';

  const aiStatusBg = isAiSpeaking
    ? 'rgba(255, 115, 0, 0.15)'
    : isAiError
    ? 'rgba(255, 72, 0, 0.15)'
    : 'transparent';

  return (
    <HudPanel title="Voice Stream Monitor" icon={<Mic size={14} />} tag="AUDIO I/O">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* User Voice */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Mic size={12} style={{ color: 'var(--accent-gold)' }} />
              <span className="font-hud" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                USER INPUT CHANNEL
              </span>
            </div>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                color: userStatusColor,
                background: userStatusBg,
                padding: '1px 5px',
                borderRadius: '2px',
              }}
            >
              {userStatusLabel}
            </span>
          </div>

          <WaveformVisualizer isActive={isUserListening || isUserProcessing} color="#f5af37" />

          {voiceState.recognizedUtterance ? (
            <div
              className="font-mono"
              style={{
                fontSize: '11px',
                color: 'var(--accent-gold-light)',
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px 6px',
                borderRadius: '2px',
                borderLeft: '2px solid var(--accent-gold)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              "{voiceState.recognizedUtterance}"
            </div>
          ) : null}
        </div>

        {/* AI Voice Output */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Volume2 size={12} style={{ color: 'var(--accent-orange)' }} />
              <span className="font-hud" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                AI SPEECH CHANNEL (TTS)
              </span>
            </div>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                color: aiStatusColor,
                background: aiStatusBg,
                padding: '1px 5px',
                borderRadius: '2px',
              }}
            >
              {aiStatusLabel}
            </span>
          </div>

          <WaveformVisualizer isActive={isAiSpeaking} color="#ff7300" />

          {voiceState.spokenResponse ? (
            <div
              className="font-mono"
              style={{
                fontSize: '11px',
                color: 'var(--text-primary)',
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px 6px',
                borderRadius: '2px',
                borderLeft: '2px solid var(--accent-orange)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              "{voiceState.spokenResponse}"
            </div>
          ) : null}
        </div>
      </div>
    </HudPanel>
  );
};
