import React, { useState, useEffect } from 'react';
import { HudPanel } from './HudPanel';
import { Clock, CloudSun, MapPin } from 'lucide-react';

export const DateTimeWeather: React.FC = () => {
  const [time, setTime] = useState<Date>(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (d: Date) => {
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  };

  const formatDate = (d: Date) => {
    return d.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).toUpperCase();
  };

  return (
    <HudPanel title="Chrono & Atmosphere" icon={<Clock size={14} />} tag="SYNCHRONIZED">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* Large Digital Clock */}
        <div style={{ textAlign: 'center', padding: '6px 0' }}>
          <div
            className="font-display glow-gold"
            style={{
              fontSize: '28px',
              fontWeight: 900,
              color: 'var(--accent-gold-light)',
              letterSpacing: '0.08em',
            }}
          >
            {formatTime(time)}
          </div>
          <div
            className="font-mono"
            style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}
          >
            {formatDate(time)}
          </div>
        </div>

        {/* Location & Atmosphere */}
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
            <MapPin size={12} style={{ color: 'var(--accent-gold)' }} />
            <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              LOCAL STATION
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CloudSun size={13} style={{ color: 'var(--accent-gold-light)' }} />
            <span
              className="font-mono"
              style={{ fontSize: '11px', color: 'var(--accent-gold-light)' }}
            >
              26°C CLEAR
            </span>
          </div>
        </div>
      </div>
    </HudPanel>
  );
};
