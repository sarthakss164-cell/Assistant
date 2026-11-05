import React, { useState } from 'react';
import { AlertOctagon, CheckCircle2 } from 'lucide-react';

interface PanicAbortButtonProps {
  onAbort?: () => void;
}

export const PanicAbortButton: React.FC<PanicAbortButtonProps> = ({ onAbort }) => {
  const [triggered, setTriggered] = useState(false);

  const handleClick = () => {
    setTriggered(true);
    if (onAbort) onAbort();
    setTimeout(() => setTriggered(false), 2500);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
      }}
    >
      <button
        onClick={handleClick}
        className="font-display border-glow-orange"
        style={{
          width: '100%',
          padding: '12px 16px',
          background: triggered
            ? 'linear-gradient(135deg, rgba(255, 115, 0, 0.4) 0%, rgba(255, 72, 0, 0.6) 100%)'
            : 'linear-gradient(135deg, rgba(40, 18, 10, 0.95) 0%, rgba(20, 10, 6, 0.95) 100%)',
          border: '2px solid var(--accent-orange)',
          borderRadius: '4px',
          color: triggered ? '#fff' : 'var(--accent-orange)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px',
          cursor: 'pointer',
          letterSpacing: '0.15em',
          fontSize: '13px',
          fontWeight: 900,
          textTransform: 'uppercase',
          boxShadow: '0 0 16px rgba(255, 115, 0, 0.45)',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#ff4800';
          e.currentTarget.style.boxShadow = '0 0 24px rgba(255, 72, 0, 0.7)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'var(--accent-orange)';
          e.currentTarget.style.boxShadow = '0 0 16px rgba(255, 115, 0, 0.45)';
        }}
        onMouseDown={(e) => (e.currentTarget.style.transform = 'scale(0.98)')}
        onMouseUp={(e) => (e.currentTarget.style.transform = 'scale(1)')}
      >
        {triggered ? (
          <>
            <CheckCircle2 size={16} style={{ color: '#fff' }} />
            <span>ABORT SIGNAL DISPATCHED</span>
          </>
        ) : (
          <>
            <AlertOctagon size={16} style={{ color: 'var(--accent-orange)' }} />
            <span>[ PANIC / ABORT ]</span>
          </>
        )}
      </button>

      <div
        className="font-mono"
        style={{
          fontSize: '9px',
          color: 'var(--text-muted)',
          textAlign: 'center',
          letterSpacing: '0.04em',
        }}
      >
        NON-DESTRUCTIVE // HALT SPEECH & PURGE PENDING QUEUE
      </div>
    </div>
  );
};
