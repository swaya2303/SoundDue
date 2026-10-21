import React from 'react';
import { AlertTriangle, AlertCircle, Info, CheckCircle2, Clock, XCircle, ShieldCheck } from 'lucide-react';

export interface SeverityBadgeProps {
  severity: 'error' | 'warning' | 'info' | string;
  size?: 'sm' | 'md';
}

export function SeverityBadge({ severity, size = 'sm' }: SeverityBadgeProps) {
  const norm = severity?.toLowerCase();

  const styles = {
    error: 'bg-status-error-bg text-status-error-text border-status-error-border',
    warning: 'bg-status-warning-bg text-status-warning-text border-status-warning-border',
    info: 'bg-status-info-bg text-status-info-text border-status-info-border',
  }[norm] || 'bg-slate-100 text-slate-700 border-slate-200';

  const icons = {
    error: <AlertCircle className="w-3 h-3 text-status-error-solid shrink-0" />,
    warning: <AlertTriangle className="w-3 h-3 text-status-warning-solid shrink-0" />,
    info: <Info className="w-3 h-3 text-status-info-solid shrink-0" />,
  }[norm] || <Info className="w-3 h-3 shrink-0" />;

  const sizeClasses = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1';

  return (
    <span className={`inline-flex items-center gap-1.5 font-medium rounded border ${styles} ${sizeClasses} capitalize select-none`}>
      {icons}
      <span>{severity}</span>
    </span>
  );
}

export interface StatusPillProps {
  status: 'open' | 'resolved' | 'accepted' | 'rejected' | 'pending' | string;
  size?: 'sm' | 'md';
}

export function StatusPill({ status, size = 'sm' }: StatusPillProps) {
  const norm = status?.toLowerCase();

  const styles = {
    resolved: 'bg-status-success-bg text-status-success-text border-status-success-border',
    accepted: 'bg-brand-50 text-brand-800 border-brand-200',
    rejected: 'bg-status-error-bg text-status-error-text border-status-error-border',
    open: 'bg-amber-50 text-amber-800 border-amber-200',
    pending: 'bg-slate-100 text-slate-700 border-slate-300',
  }[norm] || 'bg-slate-100 text-slate-700 border-slate-200';

  const icons = {
    resolved: <CheckCircle2 className="w-3 h-3 text-status-success-solid shrink-0" />,
    accepted: <ShieldCheck className="w-3 h-3 text-brand-600 shrink-0" />,
    rejected: <XCircle className="w-3 h-3 text-status-error-solid shrink-0" />,
    open: <Clock className="w-3 h-3 text-amber-600 shrink-0" />,
    pending: <Clock className="w-3 h-3 text-slate-500 shrink-0" />,
  }[norm] || null;

  const sizeClasses = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1';

  return (
    <span className={`inline-flex items-center gap-1.5 font-medium rounded border ${styles} ${sizeClasses} capitalize select-none`}>
      {icons}
      <span>{status}</span>
    </span>
  );
}

export function Tag({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono bg-slate-100 text-slate-700 border border-slate-200 ${className}`}>
      {children}
    </span>
  );
}
