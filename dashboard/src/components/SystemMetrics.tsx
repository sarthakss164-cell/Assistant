import React from 'react';
import { HudPanel } from './HudPanel';
import { Activity, HardDrive, BatteryCharging, Zap } from 'lucide-react';
import { SystemMetrics as SystemMetricsType } from '../types/dashboard';

interface SystemMetricsProps {
  metrics: SystemMetricsType;
}

export const SystemMetrics: React.FC<SystemMetricsProps> = ({ metrics }) => {
  // Circular donut gauge parameters for RAM
  const size = 110;
  const strokeWidth = 9;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (metrics.ramPercent / 100) * circumference;

  return (
    <HudPanel title="System Metrics" icon={<Activity size={14} />} tag="LIVE TELEMETRY">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* RAM Donut + Details */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
            <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
              {/* Background ring */}
              <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                stroke="rgba(245, 175, 55, 0.12)"
                strokeWidth={strokeWidth}
                fill="none"
              />
              {/* Active animated stroke */}
              <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                stroke="var(--accent-gold)"
                strokeWidth={strokeWidth}
                fill="none"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                style={{
                  transition: 'stroke-dashoffset 0.8s ease',
                  filter: 'drop-shadow(0 0 6px rgba(245, 175, 55, 0.5))',
                }}
              />
            </svg>
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <span
                className="font-display"
                style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-gold)' }}
              >
                {metrics.ramPercent}%
              </span>
              <span className="font-mono" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                RAM LOAD
              </span>
            </div>
          </div>

          {/* RAM & CPU Stats */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '11px',
                  marginBottom: '2px',
                }}
              >
                <span className="font-hud" style={{ color: 'var(--text-secondary)' }}>
                  MEMORY ALLOCATION
                </span>
                <span className="font-mono" style={{ color: 'var(--accent-gold-light)' }}>
                  {metrics.ramUsedGb.toFixed(1)} / {metrics.ramTotalGb} GB
                </span>
              </div>
              <div
                style={{
                  height: '4px',
                  background: 'rgba(245, 175, 55, 0.1)',
                  borderRadius: '2px',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${metrics.ramPercent}%`,
                    background: 'linear-gradient(90deg, var(--accent-bronze), var(--accent-gold))',
                  }}
                />
              </div>
            </div>

            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '11px',
                  marginBottom: '2px',
                }}
              >
                <span className="font-hud" style={{ color: 'var(--text-secondary)' }}>
                  CPU CORE USAGE
                </span>
                <span className="font-mono" style={{ color: 'var(--accent-gold-light)' }}>
                  {metrics.cpuPercent}%
                </span>
              </div>
              {/* CPU Sparkline */}
              <div
                style={{
                  height: '24px',
                  background: 'rgba(0, 0, 0, 0.35)',
                  border: '1px solid var(--border-gold-subtle)',
                  borderRadius: '2px',
                  display: 'flex',
                  alignItems: 'flex-end',
                  gap: '2px',
                  padding: '2px 4px',
                }}
              >
                {metrics.cpuHistory.map((val, idx) => (
                  <div
                    key={idx}
                    style={{
                      flex: 1,
                      height: `${Math.max(10, val)}%`,
                      background:
                        val > 70
                          ? 'var(--accent-orange)'
                          : 'var(--accent-gold)',
                      opacity: 0.85,
                      borderRadius: '1px',
                      transition: 'height 0.3s ease',
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Storage and Battery Bars */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '10px',
            paddingTop: '8px',
            borderTop: '1px solid var(--border-gold-subtle)',
          }}
        >
          {/* Storage */}
          <div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '11px',
                color: 'var(--text-secondary)',
                marginBottom: '4px',
              }}
            >
              <HardDrive size={12} style={{ color: 'var(--accent-gold)' }} />
              <span className="font-hud">{metrics.storageDrive || 'C:'} SSD STORAGE</span>
            </div>
            <div
              style={{
                height: '4px',
                background: 'rgba(245, 175, 55, 0.1)',
                borderRadius: '2px',
                overflow: 'hidden',
                marginBottom: '4px',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(100, Math.max(0, metrics.storagePercent))}%`,
                  background: 'var(--accent-gold)',
                }}
              />
            </div>
            <div className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              {metrics.storageUsedGb.toFixed(0)} / {metrics.storageTotalGb.toFixed(0)} GB ({metrics.storagePercent}%)
            </div>
          </div>

          {/* Battery */}
          <div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontSize: '11px',
                color: 'var(--text-secondary)',
                marginBottom: '4px',
              }}
            >
              <BatteryCharging size={12} style={{ color: 'var(--accent-gold)' }} />
              <span className="font-hud">POWER CELL</span>
            </div>
            <div
              style={{
                height: '4px',
                background: 'rgba(245, 175, 55, 0.1)',
                borderRadius: '2px',
                overflow: 'hidden',
                marginBottom: '4px',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width:
                    metrics.hasBattery && metrics.batteryPercent !== null
                      ? `${Math.min(100, Math.max(0, metrics.batteryPercent))}%`
                      : '100%',
                  background:
                    metrics.hasBattery && metrics.batteryPercent !== null
                      ? 'linear-gradient(90deg, #f5af37, #ffd57a)'
                      : 'rgba(245, 175, 55, 0.35)',
                }}
              />
            </div>
            <div className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              {metrics.hasBattery && metrics.batteryPercent !== null
                ? `${metrics.batteryPercent}% ${metrics.batteryCharging ? '[CHARGING]' : '[BATTERY]'}`
                : '[AC MAINS / NO BATTERY]'}
            </div>
          </div>
        </div>
      </div>
    </HudPanel>
  );
};
