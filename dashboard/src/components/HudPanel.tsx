import React from 'react';

interface HudPanelProps {
  title: string;
  icon?: React.ReactNode;
  tag?: string;
  className?: string;
  contentClassName?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
  contentStyle?: React.CSSProperties;
}

export const HudPanel: React.FC<HudPanelProps> = ({
  title,
  icon,
  tag,
  className = '',
  contentClassName = '',
  children,
  style,
  contentStyle,
}) => {
  return (
    <div className={`hud-panel ${className}`} style={style}>
      <div className="panel-header" style={{ flexShrink: 0 }}>
        <div className="panel-title">
          {icon && <span style={{ color: 'var(--accent-gold)' }}>{icon}</span>}
          <span>{title}</span>
        </div>
        {tag && <span className="panel-tag">{tag}</span>}
      </div>
      <div className={contentClassName} style={{ padding: '12px', ...contentStyle }}>
        {children}
      </div>
    </div>
  );
};
