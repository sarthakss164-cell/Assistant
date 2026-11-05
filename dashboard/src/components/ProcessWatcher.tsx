import React from 'react';
import { HudPanel } from './HudPanel';
import { Layers, AppWindow, Cpu, Clock, Hash } from 'lucide-react';
import { ProcessWatcher as ProcessWatcherType } from '../types/dashboard';

interface ProcessWatcherProps {
  data: ProcessWatcherType;
}

export const ProcessWatcher: React.FC<ProcessWatcherProps> = ({ data }) => {
  return (
    <HudPanel
      title="Process Watcher"
      icon={<Layers size={14} />}
      tag="TASK MONITOR"
      style={{
        flex: '0 0 175px',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        overflow: 'hidden',
      }}
      contentClassName="hud-scroll"
      contentStyle={{
        flex: 1,
        minHeight: 0,
        padding: '8px 10px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingBottom: '4px' }}>
        {/* Foreground Focus Application */}
        <div
          style={{
            background: 'rgba(245, 175, 55, 0.06)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '8px 10px',
            minWidth: 0,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '4px',
              gap: '6px',
            }}
          >
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '10px',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
                minWidth: 0,
                whiteSpace: 'nowrap',
              }}
              className="font-hud"
            >
              <AppWindow size={12} style={{ color: 'var(--accent-gold)', flexShrink: 0 }} />
              FOREGROUND APPLICATION
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                color: '#28e070',
                background: 'rgba(40, 224, 112, 0.1)',
                padding: '1px 5px',
                borderRadius: '2px',
                border: '1px solid rgba(40, 224, 112, 0.3)',
                flexShrink: 0,
                letterSpacing: '0.04em',
              }}
            >
              ACTIVE FOCUS
            </span>
          </div>
          <div
            className="font-display"
            style={{
              fontSize: '13px',
              fontWeight: 700,
              color: 'var(--text-primary)',
              letterSpacing: '0.05em',
              wordBreak: 'break-word',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              lineHeight: '1.3',
            }}
            title={data.foregroundApp}
          >
            {data.foregroundApp}
          </div>
        </div>

        {/* Background Worker */}
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.3)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 8px',
            minWidth: 0,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '9px',
              color: 'var(--text-muted)',
              marginBottom: '2px',
              letterSpacing: '0.06em',
            }}
            className="font-hud"
          >
            <Cpu size={11} style={{ color: 'var(--accent-gold)', flexShrink: 0 }} />
            BACKGROUND WORKER
          </div>
          <div
            className="font-mono"
            style={{
              fontSize: '11px',
              color: 'var(--accent-gold-light)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              minWidth: 0,
            }}
            title={data.activeProcess}
          >
            {data.activeProcess}
          </div>
        </div>

        {/* Sub-grid: Process PID & Tool Latency */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
            gap: '8px',
          }}
        >
          {/* Active Process PID */}
          <div
            style={{
              background: 'rgba(0, 0, 0, 0.3)',
              border: '1px solid var(--border-gold-subtle)',
              borderRadius: '3px',
              padding: '6px 8px',
              minWidth: 0,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                marginBottom: '2px',
                letterSpacing: '0.06em',
                whiteSpace: 'nowrap',
              }}
              className="font-hud"
            >
              <Hash size={11} style={{ color: 'var(--accent-gold)', flexShrink: 0 }} />
              PROCESS PID
            </div>
            <div
              className="font-mono"
              style={{
                fontSize: '12px',
                fontWeight: 600,
                color: data.activeProcessPid ? 'var(--accent-gold-light)' : 'var(--text-dim)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {data.activeProcessPid ? `PID ${data.activeProcessPid}` : 'STANDBY'}
            </div>
          </div>

          {/* Tool Latency */}
          <div
            style={{
              background: 'rgba(0, 0, 0, 0.3)',
              border: '1px solid var(--border-gold-subtle)',
              borderRadius: '3px',
              padding: '6px 8px',
              minWidth: 0,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                marginBottom: '2px',
                letterSpacing: '0.06em',
                whiteSpace: 'nowrap',
              }}
              className="font-hud"
            >
              <Clock size={11} style={{ color: 'var(--accent-gold)', flexShrink: 0 }} />
              TOOL LATENCY
            </div>
            <div
              className="font-mono glow-gold"
              style={{
                fontSize: '12px',
                fontWeight: 700,
                color: 'var(--accent-gold)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {data.toolLatencyMs !== null ? `${data.toolLatencyMs} ms` : 'IDLE'}
            </div>
          </div>
        </div>
      </div>
    </HudPanel>
  );
};
