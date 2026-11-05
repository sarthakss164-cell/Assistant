import React, { useEffect, useRef } from 'react';
import { HudPanel } from './HudPanel';
import { MessageSquare, User, Bot } from 'lucide-react';
import { ConversationItem } from '../types/dashboard';

interface ConversationLogProps {
  logs: ConversationItem[];
}

export const ConversationLog: React.FC<ConversationLogProps> = ({ logs }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <HudPanel
      title="Conversation Log"
      icon={<MessageSquare size={14} />}
      tag="STRUCTURED SPEECH FEED"
      style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}
      contentStyle={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          overflowY: 'auto',
          flex: 1,
          paddingRight: '4px',
        }}
      >
        {logs.length === 0 ? (
          <div
            style={{
              padding: '28px 16px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '11px',
              letterSpacing: '0.12em',
              border: '1px dashed rgba(245, 175, 55, 0.2)',
              borderRadius: '4px',
              background: 'rgba(20, 15, 10, 0.4)',
              margin: 'auto 0',
            }}
            className="font-mono"
          >
            AWAITING VOICE INTERACTION...
          </div>
        ) : (
          logs.map((item) => {
            const isUser = item.sender === 'USER';
            return (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  background: isUser
                    ? 'rgba(245, 175, 55, 0.05)'
                    : 'rgba(30, 22, 14, 0.65)',
                  border: isUser
                    ? '1px solid rgba(245, 175, 55, 0.25)'
                    : '1px solid rgba(245, 175, 55, 0.15)',
                  borderRadius: '3px',
                  padding: '8px 10px',
                }}
              >
                {/* Sender & Timestamp Header */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '11px',
                      fontWeight: 700,
                    }}
                    className="font-display"
                  >
                    {isUser ? (
                      <>
                        <User size={12} style={{ color: 'var(--accent-gold)' }} />
                        <span style={{ color: 'var(--accent-gold)' }}>USER UTTERANCE</span>
                      </>
                    ) : (
                      <>
                        <Bot size={12} style={{ color: 'var(--accent-orange)' }} />
                        <span style={{ color: 'var(--accent-orange)' }}>LIGHT AI RESPONSE</span>
                      </>
                    )}
                  </div>
                  <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {item.timestamp}
                  </span>
                </div>

                {/* Message Body */}
                <div
                  className="font-hud"
                  style={{
                    fontSize: '13px',
                    color: isUser ? 'var(--text-primary)' : 'var(--accent-gold-light)',
                    lineHeight: '1.4',
                  }}
                >
                  {item.text}
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </HudPanel>
  );
};
