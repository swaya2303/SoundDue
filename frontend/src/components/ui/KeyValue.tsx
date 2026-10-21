import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export function MonospaceValue({ value, copyable = true }: { value: string | number | null | undefined; copyable?: boolean }) {
  const [copied, setCopied] = useState(false);
  const textVal = String(value ?? '—');

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!value) return;
    navigator.clipboard.writeText(textVal);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!copyable || !value) {
    return <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">{textVal}</code>;
  }

  return (
    <span className="inline-flex items-center gap-1.5 group">
      <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200 select-all">
        {textVal}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-200"
        title="Copy to clipboard"
        aria-label="Copy to clipboard"
      >
        {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
      </button>
    </span>
  );
}

export function KeyValueRow({ label, value, mono = false }: { label: React.ReactNode; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between py-1.5 border-b border-slate-100 last:border-0 text-xs">
      <span className="text-slate-500 font-medium">{label}</span>
      <span className="text-slate-800 text-right">
        {mono && typeof value === 'string' ? <MonospaceValue value={value} /> : value}
      </span>
    </div>
  );
}
