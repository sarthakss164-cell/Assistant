import React, { useState, useRef, useEffect } from 'react';
import { HudPanel } from './HudPanel';
import { Terminal, Send, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { TextCommandAckResult } from '../types/dashboard';

interface TextCommandConsoleProps {
  onSendCommand: (text: string) => Promise<TextCommandAckResult>;
  bridgeStatus?: string;
}

export const TextCommandConsole: React.FC<TextCommandConsoleProps> = ({
  onSendCommand,
  bridgeStatus = 'ONLINE',
}) => {
  const [inputText, setInputText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [feedback, setFeedback] = useState<{
    text: string;
    type: 'idle' | 'success' | 'error' | 'submitting';
  }>({
    text: 'DIRECT INPUT // NO WAKE WORD',
    type: 'idle',
  });

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const feedbackTimerRef = useRef<number | null>(null);

  const isOnline = bridgeStatus === 'ONLINE';

  useEffect(() => {
    return () => {
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current);
      }
    };
  }, []);

  const handleSubmit = async () => {
    const clean = inputText.trim();
    if (!clean || isSubmitting || !isOnline) {
      return;
    }

    setIsSubmitting(true);
    setFeedback({ text: 'SUBMITTING TO QUEUE...', type: 'submitting' });

    try {
      const res = await onSendCommand(clean);
      if (res.success) {
        // Clear input ONLY upon backend confirmation
        setInputText('');
        setFeedback({
          text: `QUEUED // ${res.status || 'ACCEPTED'}`,
          type: 'success',
        });
        if (textareaRef.current) {
          textareaRef.current.focus();
        }
      } else {
        // Retain input upon rejection so user does not lose typed command
        const errDetail = res.message ? `: ${res.message}` : '';
        setFeedback({
          text: `REJECTED // ${res.status || 'ERROR'}${errDetail}`,
          type: 'error',
        });
      }
    } catch (err: any) {
      setFeedback({
        text: `FAILED // ${err?.message || 'SUBMISSION_ERROR'}`,
        type: 'error',
      });
    } finally {
      setIsSubmitting(false);
      // Revert feedback to idle after 4 seconds
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current);
      }
      feedbackTimerRef.current = window.setTimeout(() => {
        setFeedback({
          text: isOnline ? 'DIRECT INPUT // NO WAKE WORD' : 'OFFLINE // BRIDGE DISCONNECTED',
          type: 'idle',
        });
      }, 4000);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Determine feedback badge style
  let badgeColor = 'var(--text-muted)';
  let badgeBg = 'rgba(255, 180, 0, 0.05)';
  let badgeBorder = 'rgba(255, 180, 0, 0.2)';
  let iconNode = null;

  if (!isOnline) {
    badgeColor = 'var(--accent-orange)';
    badgeBg = 'rgba(255, 70, 0, 0.1)';
    badgeBorder = 'rgba(255, 70, 0, 0.3)';
    iconNode = <AlertCircle size={10} />;
  } else if (feedback.type === 'submitting') {
    badgeColor = 'var(--accent-gold)';
    badgeBg = 'rgba(255, 180, 0, 0.15)';
    badgeBorder = 'rgba(255, 180, 0, 0.4)';
    iconNode = <Loader2 size={10} className="animate-spin" />;
  } else if (feedback.type === 'success') {
    badgeColor = '#44ff88';
    badgeBg = 'rgba(68, 255, 136, 0.1)';
    badgeBorder = 'rgba(68, 255, 136, 0.3)';
    iconNode = <CheckCircle2 size={10} />;
  } else if (feedback.type === 'error') {
    badgeColor = 'var(--accent-orange)';
    badgeBg = 'rgba(255, 70, 0, 0.12)';
    badgeBorder = 'rgba(255, 70, 0, 0.4)';
    iconNode = <AlertCircle size={10} />;
  }

  const canSubmit = isOnline && !isSubmitting && inputText.trim().length > 0;

  return (
    <HudPanel
      title="Text Command // Console"
      icon={<Terminal size={14} />}
      tag="DIRECT INPUT"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* Multiline Textarea with Accessible Focus Glow */}
        <div style={{ position: 'relative' }}>
          <textarea
            ref={textareaRef}
            rows={2}
            value={inputText}
            maxLength={500}
            disabled={!isOnline || isSubmitting}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={
              isOnline
                ? 'Type command... (Enter to send, Shift+Enter for newline)'
                : 'Bridge disconnected — reconnecting...'
            }
            className="font-mono"
            style={{
              width: '100%',
              padding: '8px 10px',
              fontSize: '11px',
              lineHeight: '1.4',
              color: isOnline ? '#f5e9d3' : 'var(--text-muted)',
              background: 'linear-gradient(180deg, rgba(14, 11, 8, 0.85) 0%, rgba(8, 6, 4, 0.95) 100%)',
              border: isFocused
                ? '1px solid var(--accent-gold)'
                : '1px solid rgba(255, 180, 0, 0.22)',
              borderRadius: '3px',
              boxShadow: isFocused
                ? '0 0 12px rgba(255, 180, 0, 0.3), inset 0 0 8px rgba(255, 180, 0, 0.05)'
                : 'inset 0 1px 3px rgba(0, 0, 0, 0.5)',
              outline: 'none',
              resize: 'none',
              boxSizing: 'border-box',
              transition: 'border-color 0.18s ease, box-shadow 0.18s ease',
              fontFamily: 'var(--font-mono, monospace)',
            }}
          />
        </div>

        {/* Console Action Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
          }}
        >
          {/* Status Feedback Badge */}
          <div
            className="font-mono"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '3px 7px',
              fontSize: '9px',
              fontWeight: 600,
              letterSpacing: '0.08em',
              color: badgeColor,
              backgroundColor: badgeBg,
              border: `1px solid ${badgeBorder}`,
              borderRadius: '2px',
              maxWidth: '220px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              textTransform: 'uppercase',
            }}
            title={feedback.text}
          >
            {iconNode}
            <span>{feedback.text}</span>
          </div>

          {/* Right Controls: Char Count & Send Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                color: inputText.length > 450 ? 'var(--accent-orange)' : 'var(--text-muted)',
              }}
            >
              {inputText.length}/500
            </span>

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              title={canSubmit ? 'Send text command (Enter)' : 'Enter command text'}
              className="font-display"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 10px',
                fontSize: '10px',
                fontWeight: 700,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: canSubmit ? '#120b04' : 'rgba(255, 180, 0, 0.35)',
                background: canSubmit
                  ? 'linear-gradient(135deg, var(--accent-gold) 0%, #e59400 100%)'
                  : 'rgba(30, 22, 12, 0.5)',
                border: canSubmit
                  ? '1px solid var(--accent-gold)'
                  : '1px solid rgba(255, 180, 0, 0.15)',
                borderRadius: '2px',
                cursor: canSubmit ? 'pointer' : 'not-allowed',
                boxShadow: canSubmit ? '0 0 10px rgba(255, 180, 0, 0.35)' : 'none',
                transition: 'all 0.18s ease',
              }}
              onMouseEnter={(e) => {
                if (canSubmit) {
                  e.currentTarget.style.boxShadow = '0 0 14px rgba(255, 180, 0, 0.55)';
                }
              }}
              onMouseLeave={(e) => {
                if (canSubmit) {
                  e.currentTarget.style.boxShadow = '0 0 10px rgba(255, 180, 0, 0.35)';
                }
              }}
            >
              <Send size={10} />
              <span>SEND</span>
            </button>
          </div>
        </div>
      </div>
    </HudPanel>
  );
};

