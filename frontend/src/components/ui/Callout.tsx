import React from 'react';
import { AlertTriangle, Info, AlertCircle, CheckCircle2, ShieldAlert } from 'lucide-react';

export interface CalloutProps {
  type?: 'neutral' | 'warning' | 'error' | 'info' | 'success';
  title?: string;
  children: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}

export function Callout({ type = 'neutral', title, children, className = '', icon }: CalloutProps) {
  const styles = {
    neutral: 'bg-slate-50 border-slate-300 text-slate-800',
    warning: 'bg-amber-50/90 border-amber-300 text-amber-900',
    error: 'bg-rose-50/90 border-rose-300 text-rose-900',
    info: 'bg-sky-50/90 border-sky-300 text-sky-900',
    success: 'bg-emerald-50/90 border-emerald-300 text-emerald-900',
  }[type];

  const defaultIcons = {
    neutral: <ShieldAlert className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />,
    warning: <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />,
    error: <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />,
    info: <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />,
    success: <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />,
  }[type];

  return (
    <div className={`p-3.5 rounded-lg border text-sm flex gap-3 ${styles} ${className}`}>
      {icon ?? defaultIcons}
      <div className="flex-1 min-w-0">
        {title && <h4 className="font-semibold text-xs uppercase tracking-wider mb-1">{title}</h4>}
        <div className="text-xs leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
