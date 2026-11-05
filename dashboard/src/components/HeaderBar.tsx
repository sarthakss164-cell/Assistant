import React from 'react';
import { Minus, Square, X, Cpu, ShieldCheck, AlertCircle } from 'lucide-react';
import { BridgeStatus } from '../types/dashboard';

interface HeaderBarProps {
  bridgeStatus?: BridgeStatus;
}

export const HeaderBar: React.FC<HeaderBarProps> = ({ bridgeStatus = 'ONLINE' }) => {
  const handleMinimize = () => {
    if ((window as any).electronAPI?.minimize) {
      (window as any).electronAPI.minimize();
    }
  };

  const handleMaximize = () => {
    if ((window as any).electronAPI?.maximize) {
      (window as any).electronAPI.maximize();
    }
  };

  const handleClose = () => {
    if ((window as any).electronAPI?.close) {
      (window as any).electronAPI.close();
    }
  };

  const getStatusDisplay = () => {
    switch (bridgeStatus) {
      case 'ONLINE':
        return {
          dotColor: 'var(--accent-gold)',
          textColor: 'var(--accent-gold)',
          label: 'CORE: ONLINE // SAFEGUARDS ACTIVE',
          icon: <ShieldCheck size={13} style={{ color: 'var(--accent-gold)' }} />,
          isPulse: false,
        };
      case 'CONNECTING':
        return {
          dotColor: 'var(--accent-gold-light)',
          textColor: 'var(--accent-gold-light)',
          label: 'CORE: ONLINE // BRIDGE: CONNECTING...',
          icon: <Cpu size={13} style={{ color: 'var(--accent-gold-light)' }} />,
          isPulse: true,
        };
      case 'DISCONNECTED':
        return {
          dotColor: 'var(--accent-orange)',
          textColor: 'var(--accent-orange)',
          label: 'CORE: STANDBY // BRIDGE: DISCONNECTED',
          icon: <AlertCircle size={13} style={{ color: 'var(--accent-orange)' }} />,
          isPulse: false,
        };
      case 'ERROR':
      default:
        return {
          dotColor: '#ff4422',
          textColor: '#ff4422',
          label: 'CORE: STANDBY // BRIDGE: ERROR',
          icon: <AlertCircle size={13} style={{ color: '#ff4422' }} />,
          isPulse: false,
        };
    }
  };

  const status = getStatusDisplay();

  return (
    <header
      className="app-drag-region"
      style={{
        height: '42px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        borderBottom: '1px solid var(--border-gold-subtle)',
        background: 'linear-gradient(180deg, rgba(30, 22, 14, 0.95) 0%, rgba(14, 10, 6, 0.9) 100%)',
        zIndex: 100,
      }}
    >
      {/* Title & Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Cpu size={18} style={{ color: 'var(--accent-gold)' }} />
        <span
          className="font-display glow-gold"
          style={{
            fontSize: '13px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            letterSpacing: '0.15em',
          }}
        >
          LIGHT AI <span style={{ color: 'var(--accent-gold)' }}>V1.0</span> // TACTICAL HUD
        </span>
      </div>

      {/* System Status Pill */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: 'rgba(245, 175, 55, 0.08)',
          border: '1px solid var(--border-gold-subtle)',
          padding: '3px 10px',
          borderRadius: '12px',
        }}
      >
        <span
          className={status.isPulse ? 'animate-pulse-glow' : ''}
          style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            backgroundColor: status.dotColor,
            boxShadow: `0 0 6px ${status.dotColor}`,
            display: 'inline-block',
          }}
        />
        {status.icon}
        <span
          className="font-mono"
          style={{ fontSize: '11px', color: status.textColor, letterSpacing: '0.05em' }}
        >
          {status.label}
        </span>
      </div>

      {/* Window Controls */}
      <div className="no-drag" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <button
          onClick={handleMinimize}
          title="Minimize"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-secondary)',
            padding: '6px 8px',
            cursor: 'pointer',
            borderRadius: '3px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Minus size={14} />
        </button>
        <button
          onClick={handleMaximize}
          title="Maximize"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-secondary)',
            padding: '6px 8px',
            cursor: 'pointer',
            borderRadius: '3px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Square size={12} />
        </button>
        <button
          onClick={handleClose}
          title="Close"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--accent-orange)',
            padding: '6px 8px',
            cursor: 'pointer',
            borderRadius: '3px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <X size={14} />
        </button>
      </div>
    </header>
  );
};
