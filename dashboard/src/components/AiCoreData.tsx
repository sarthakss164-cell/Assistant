import React from 'react';
import { HudPanel } from './HudPanel';
import {
  Cpu,
  Terminal,
  Zap,
  Activity,
  HardDrive,
  Clock,
  ShieldCheck,
  Layers,
} from 'lucide-react';
import {
  AiCoreData as AiCoreDataType,
  GatewayStatus,
  AiRuntimeState,
  SessionMemoryStatus,
} from '../types/dashboard';

interface AiCoreDataProps {
  data: AiCoreDataType;
}

export const AiCoreData: React.FC<AiCoreDataProps> = ({ data }) => {
  // Format uptime seconds into HH:MM:SS
  const formatUptime = (totalSeconds: number) => {
    const s = Math.max(0, Math.floor(totalSeconds || 0));
    const hours = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTimestamp = (ts: number | null) => {
    if (!ts) return '--';
    try {
      const d = new Date(ts * 1000);
      return d.toTimeString().substring(0, 8);
    } catch {
      return '--';
    }
  };

  // Helper for Gateway Status badge styling
  const getGatewayStatusBadge = (status: GatewayStatus) => {
    switch (status) {
      case 'ONLINE':
        return {
          label: 'ONLINE',
          bg: 'rgba(34, 197, 94, 0.15)',
          color: '#4ade80',
          border: 'rgba(34, 197, 94, 0.35)',
        };
      case 'PROCESSING':
        return {
          label: 'PROCESSING',
          bg: 'rgba(255, 115, 0, 0.22)',
          color: '#ff9838',
          border: 'rgba(255, 115, 0, 0.55)',
          animate: true,
        };
      case 'STANDBY':
        return {
          label: 'STANDBY',
          bg: 'rgba(245, 175, 55, 0.12)',
          color: 'var(--accent-gold)',
          border: 'var(--border-gold-subtle)',
        };
      case 'ERROR':
        return {
          label: 'ERROR',
          bg: 'rgba(239, 68, 68, 0.22)',
          color: '#f87171',
          border: 'rgba(239, 68, 68, 0.5)',
        };
      case 'DISCONNECTED':
      default:
        return {
          label: 'DISCONNECTED',
          bg: 'rgba(120, 113, 108, 0.22)',
          color: '#a8a29e',
          border: 'rgba(120, 113, 108, 0.4)',
        };
    }
  };

  // Helper for Session Memory badge styling
  const getMemoryStatusBadge = (status: SessionMemoryStatus) => {
    switch (status) {
      case 'ACTIVE':
        return {
          label: 'ACTIVE',
          bg: 'rgba(34, 197, 94, 0.15)',
          color: '#4ade80',
          border: 'rgba(34, 197, 94, 0.35)',
        };
      case 'MAX_CAPACITY':
        return {
          label: 'MAX (FIFO)',
          bg: 'rgba(255, 115, 0, 0.2)',
          color: '#ffaa44',
          border: 'rgba(255, 115, 0, 0.45)',
        };
      case 'EMPTY':
        return {
          label: 'EMPTY',
          bg: 'rgba(245, 175, 55, 0.08)',
          color: 'var(--text-muted)',
          border: 'var(--border-gold-subtle)',
        };
      case 'DISABLED':
      default:
        return {
          label: 'DISABLED',
          bg: 'rgba(120, 113, 108, 0.15)',
          color: '#a8a29e',
          border: 'rgba(120, 113, 108, 0.3)',
        };
    }
  };

  // Helper for Runtime State badge styling
  const getRuntimeStateBadge = (state: AiRuntimeState) => {
    switch (state) {
      case 'PROCESSING':
        return {
          label: 'PROCESSING',
          bg: 'rgba(255, 115, 0, 0.22)',
          color: '#ff9838',
          border: 'rgba(255, 115, 0, 0.55)',
          animate: true,
        };
      case 'SUCCESS':
        return {
          label: 'SUCCESS',
          bg: 'rgba(34, 197, 94, 0.15)',
          color: '#4ade80',
          border: 'rgba(34, 197, 94, 0.35)',
        };
      case 'ERROR':
        return {
          label: 'ERROR',
          bg: 'rgba(239, 68, 68, 0.22)',
          color: '#f87171',
          border: 'rgba(239, 68, 68, 0.5)',
        };
      case 'IDLE':
      default:
        return {
          label: 'IDLE',
          bg: 'rgba(245, 175, 55, 0.08)',
          color: 'var(--accent-gold-light)',
          border: 'var(--border-gold-subtle)',
        };
    }
  };

  const gwBadge = getGatewayStatusBadge(data.gatewayStatus || 'DISCONNECTED');
  const memBadge = getMemoryStatusBadge(data.sessionMemoryStatus || 'EMPTY');
  const runBadge = getRuntimeStateBadge(data.runtimeState || 'IDLE');

  const maxTurns = data.sessionMemoryMaxTurns || 10;
  const currentTurns = Math.min(maxTurns, Math.max(0, data.sessionMemoryTurns || 0));

  const hasCapacity = typeof data.contextCapacity === 'number' && data.contextCapacity > 0;
  const utilizationPct = typeof data.utilizationPercentage === 'number'
    ? Math.min(100, Math.max(0, data.utilizationPercentage))
    : null;

  return (
    <HudPanel
      title="AI Core Data"
      icon={<Cpu size={14} />}
      tag="RUNTIME TELEMETRY"
      style={{
        flex: 1,
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingBottom: '6px' }}>
        
        {/* ===================================================================
            SECTION 1: MODEL STATUS
            =================================================================== */}
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.32)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 8px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '5px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
              }}
              className="font-hud"
            >
              <Terminal size={11} style={{ color: 'var(--accent-gold)' }} />
              MODEL STATUS
            </div>
            <span
              className={`font-mono ${gwBadge.animate ? 'animate-pulse-glow' : ''}`}
              style={{
                fontSize: '9px',
                fontWeight: 700,
                padding: '1px 6px',
                borderRadius: '2px',
                background: gwBadge.bg,
                color: gwBadge.color,
                border: `1px solid ${gwBadge.border}`,
                letterSpacing: '0.06em',
              }}
            >
              {gwBadge.label}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="font-hud" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                CONFIGURED
              </span>
              <span
                className="font-mono"
                style={{ fontSize: '11px', color: 'var(--accent-gold-light)', fontWeight: 600 }}
              >
                {data.configuredModel || 'qwen3.6'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
              <span className="font-hud" style={{ fontSize: '9px', color: 'var(--text-muted)', flexShrink: 0 }}>
                RESOLVED
              </span>
              <span
                className="font-mono"
                title={data.resolvedModel || 'Unknown'}
                style={{
                  fontSize: '10px',
                  color: data.resolvedModel && data.resolvedModel !== 'Unknown' ? 'var(--accent-gold)' : 'var(--text-dim)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  maxWidth: '200px',
                  textAlign: 'right',
                }}
              >
                {data.resolvedModel || 'Unknown'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="font-hud" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                PROVIDER
              </span>
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                {data.provider || 'CoE AI Gateway (vLLM)'}
              </span>
            </div>
          </div>
        </div>

        {/* ===================================================================
            SECTION 2: CONTEXT WINDOW & TOKEN TRACKING
            =================================================================== */}
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.32)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 8px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '5px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
              }}
              className="font-hud"
            >
              <Zap size={11} style={{ color: 'var(--accent-gold)' }} />
              CONTEXT &amp; TOKENS
            </div>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                color: hasCapacity ? 'var(--accent-gold)' : 'var(--text-dim)',
              }}
            >
              {hasCapacity ? `${data.contextCapacity?.toLocaleString()} MAX` : 'CAPACITY UNKNOWN'}
            </span>
          </div>

          {/* Last Request Tokens Breakdown */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '4px',
              background: 'rgba(0, 0, 0, 0.25)',
              padding: '4px',
              borderRadius: '2px',
              marginBottom: '5px',
              border: '1px solid rgba(245, 175, 55, 0.1)',
            }}
          >
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">LAST PROMPT</div>
              <div className="font-mono" style={{ fontSize: '10px', color: 'var(--accent-gold-light)', fontWeight: 600 }}>
                {(data.lastTokens?.promptTokens ?? 0).toLocaleString()}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">LAST COMPL</div>
              <div className="font-mono" style={{ fontSize: '10px', color: 'var(--accent-gold-light)', fontWeight: 600 }}>
                {(data.lastTokens?.completionTokens ?? 0).toLocaleString()}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">LAST TOTAL</div>
              <div className="font-mono glow-gold" style={{ fontSize: '10px', color: 'var(--accent-gold)', fontWeight: 700 }}>
                {(data.lastTokens?.totalTokens ?? 0).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Session Cumulative Tokens */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '9px',
              color: 'var(--text-muted)',
              marginBottom: '4px',
            }}
          >
            <span className="font-hud">SESSION CUMULATIVE</span>
            <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
              P: {(data.sessionTokens?.promptTokens ?? 0).toLocaleString()} / C: {(data.sessionTokens?.completionTokens ?? 0).toLocaleString()} / T:{' '}
              <strong style={{ color: 'var(--accent-gold-light)' }}>
                {(data.sessionTokens?.totalTokens ?? 0).toLocaleString()}
              </strong>
            </span>
          </div>

          {/* Utilization Progress Bar */}
          <div style={{ marginTop: '4px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '8px',
                color: 'var(--text-muted)',
                marginBottom: '2px',
              }}
              className="font-hud"
            >
              <span>WINDOW UTILIZATION</span>
              <span className="font-mono">
                {utilizationPct !== null
                  ? `${utilizationPct.toFixed(1)}%`
                  : 'UNVERIFIED // CALIBRATION PENDING'}
              </span>
            </div>
            <div
              style={{
                height: '4px',
                background: 'rgba(245, 175, 55, 0.08)',
                borderRadius: '2px',
                overflow: 'hidden',
                border: '1px solid rgba(245, 175, 55, 0.1)',
                position: 'relative',
              }}
            >
              {utilizationPct !== null ? (
                <div
                  style={{
                    height: '100%',
                    width: `${utilizationPct}%`,
                    background: 'linear-gradient(90deg, var(--accent-bronze), var(--accent-gold))',
                    transition: 'width 0.3s ease',
                  }}
                />
              ) : (
                <div
                  style={{
                    height: '100%',
                    width: '100%',
                    background: 'repeating-linear-gradient(45deg, rgba(245, 175, 55, 0.05), rgba(245, 175, 55, 0.05) 4px, rgba(0, 0, 0, 0.2) 4px, rgba(0, 0, 0, 0.2) 8px)',
                  }}
                />
              )}
            </div>
          </div>
        </div>

        {/* ===================================================================
            SECTION 3: SESSION MEMORY
            =================================================================== */}
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.32)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 8px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '5px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
              }}
              className="font-hud"
            >
              <Layers size={11} style={{ color: 'var(--accent-gold)' }} />
              SESSION MEMORY
            </div>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                fontWeight: 700,
                padding: '1px 6px',
                borderRadius: '2px',
                background: memBadge.bg,
                color: memBadge.color,
                border: `1px solid ${memBadge.border}`,
                letterSpacing: '0.06em',
              }}
            >
              {memBadge.label}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
            <span className="font-hud" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
              BUFFER DEPTH
            </span>
            <span className="font-mono" style={{ fontSize: '11px', color: 'var(--accent-gold-light)', fontWeight: 600 }}>
              {currentTurns} / {maxTurns} TURNS
            </span>
          </div>

          {/* 10-segment visual turn pip indicator */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(${maxTurns}, 1fr)`,
              gap: '2px',
              marginBottom: '5px',
            }}
          >
            {Array.from({ length: maxTurns }).map((_, idx) => {
              const isFilled = idx < currentTurns;
              return (
                <div
                  key={idx}
                  style={{
                    height: '3px',
                    borderRadius: '1px',
                    background: isFilled
                      ? 'linear-gradient(90deg, var(--accent-bronze), var(--accent-gold))'
                      : 'rgba(245, 175, 55, 0.1)',
                    boxShadow: isFilled ? '0 0 3px rgba(245, 175, 55, 0.3)' : 'none',
                  }}
                />
              );
            })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="font-hud" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
              LAST REQ CONTEXT
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                color: data.historyIncluded ? '#4ade80' : 'var(--text-dim)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <span
                style={{
                  width: '5px',
                  height: '5px',
                  borderRadius: '50%',
                  background: data.historyIncluded ? '#4ade80' : 'var(--text-dim)',
                  display: 'inline-block',
                }}
              />
              {data.historyIncluded ? 'YES (CONTEXT SENT)' : 'NO (FIRST TURN)'}
            </span>
          </div>
        </div>

        {/* ===================================================================
            SECTION 4: GATEWAY PERFORMANCE
            =================================================================== */}
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.32)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 8px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '5px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
              }}
              className="font-hud"
            >
              <Activity size={11} style={{ color: 'var(--accent-gold)' }} />
              GATEWAY PERFORMANCE
            </div>
            <span
              className={`font-mono ${data.inFlightRequests > 0 ? 'animate-pulse-glow' : ''}`}
              style={{
                fontSize: '9px',
                fontWeight: 600,
                color: data.inFlightRequests > 0 ? '#ff9838' : 'var(--text-dim)',
              }}
            >
              {data.inFlightRequests > 0 ? `${data.inFlightRequests} ACTIVE` : '0 IDLE'}
            </span>
          </div>

          {/* Latency 2-column stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '5px' }}>
            <div
              style={{
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px 6px',
                borderRadius: '2px',
                border: '1px solid rgba(245, 175, 55, 0.08)',
              }}
            >
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">LAST LATENCY</div>
              <div className="font-mono" style={{ fontSize: '11px', color: 'var(--accent-gold-light)', fontWeight: 600 }}>
                {data.lastRequestLatencyMs !== null ? `${data.lastRequestLatencyMs} ms` : '--'}
              </div>
            </div>

            <div
              style={{
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px 6px',
                borderRadius: '2px',
                border: '1px solid rgba(245, 175, 55, 0.08)',
              }}
            >
              <div style={{ fontSize: '8px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }} className="font-hud">
                <span>AVG LATENCY</span>
                <span style={{ fontSize: '7px', color: 'var(--text-dim)' }}>(OK ONLY)</span>
              </div>
              <div className="font-mono" style={{ fontSize: '11px', color: 'var(--accent-gold-light)', fontWeight: 600 }}>
                {data.avgLatencyMs !== null ? `${data.avgLatencyMs} ms` : '--'}
              </div>
            </div>
          </div>

          {/* Success / Failure Counters */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="font-hud" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
              GATEWAY CALLS
            </span>
            <span className="font-mono" style={{ fontSize: '10px' }}>
              <span style={{ color: '#4ade80', fontWeight: 600 }}>{data.successCount ?? 0} OK</span>
              <span style={{ color: 'var(--text-dim)', margin: '0 4px' }}>/</span>
              <span style={{ color: (data.failureCount ?? 0) > 0 ? '#f87171' : 'var(--text-dim)', fontWeight: 600 }}>
                {data.failureCount ?? 0} FAIL
              </span>
            </span>
          </div>
        </div>

        {/* ===================================================================
            SECTION 5: RUNTIME STATE
            =================================================================== */}
        <div
          style={{
            background: 'rgba(0, 0, 0, 0.32)',
            border: '1px solid var(--border-gold-subtle)',
            borderRadius: '3px',
            padding: '6px 8px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '5px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '9px',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
              }}
              className="font-hud"
            >
              <ShieldCheck size={11} style={{ color: 'var(--accent-gold)' }} />
              RUNTIME STATE
            </div>
            <span
              className={`font-mono ${runBadge.animate ? 'animate-pulse-glow' : ''}`}
              style={{
                fontSize: '9px',
                fontWeight: 700,
                padding: '1px 6px',
                borderRadius: '2px',
                background: runBadge.bg,
                color: runBadge.color,
                border: `1px solid ${runBadge.border}`,
                letterSpacing: '0.06em',
              }}
            >
              {runBadge.label}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px' }}>
            <div
              style={{
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px',
                borderRadius: '2px',
                textAlign: 'center',
                border: '1px solid rgba(245, 175, 55, 0.08)',
              }}
            >
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">CORE UPTIME</div>
              <div className="font-mono" style={{ fontSize: '10px', color: 'var(--accent-gold-light)', fontWeight: 600 }}>
                {formatUptime(data.uptimeSeconds)}
              </div>
            </div>

            <div
              style={{
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px',
                borderRadius: '2px',
                textAlign: 'center',
                border: '1px solid rgba(245, 175, 55, 0.08)',
              }}
            >
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">ACTIONS</div>
              <div className="font-mono glow-gold" style={{ fontSize: '10px', color: 'var(--accent-gold)', fontWeight: 700 }}>
                {data.actionsExecutedCount ?? 0}
              </div>
            </div>

            <div
              style={{
                background: 'rgba(0, 0, 0, 0.25)',
                padding: '4px',
                borderRadius: '2px',
                textAlign: 'center',
                border: '1px solid rgba(245, 175, 55, 0.08)',
              }}
            >
              <div style={{ fontSize: '8px', color: 'var(--text-muted)' }} className="font-hud">LAST SUCCESS</div>
              <div className="font-mono" style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                {formatTimestamp(data.lastSuccessTimestamp)}
              </div>
            </div>
          </div>
        </div>

      </div>
    </HudPanel>
  );
};
