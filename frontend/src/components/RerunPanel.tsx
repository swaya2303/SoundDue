import { useState } from 'react';
import { rerunCase } from '../api';
import type { RerunResult, RerunDiffEntry } from '../api';

interface Props {
  caseId: number;
  onBack: () => void;
}

const CATEGORY_META: Record<
  keyof RerunResult['diff'],
  { label: string; color: string; icon: string }
> = {
  new:       { label: 'New',       color: 'bg-red-50 border-red-200 text-red-800',     icon: '🆕' },
  unchanged: { label: 'Unchanged', color: 'bg-slate-50 border-slate-200 text-slate-700', icon: '·' },
  changed:   { label: 'Changed',   color: 'bg-amber-50 border-amber-200 text-amber-800', icon: '~' },
  resolved:  { label: 'Resolved',  color: 'bg-green-50 border-green-200 text-green-800', icon: '✓' },
  rejected:  { label: 'Rejected',  color: 'bg-slate-100 border-slate-300 text-slate-500', icon: '✗' },
};

export default function RerunPanel({ caseId, onBack }: Props) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RerunResult | null>(null);
  const [error, setError] = useState('');

  async function handleRerun() {
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const r = await rerunCase(caseId);
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-4">
        <button onClick={onBack} className="text-indigo-600 hover:underline text-sm">
          ← Back to findings
        </button>
        <h2 className="font-semibold text-slate-800">Rerun analysis</h2>
      </div>

      <p className="text-sm text-slate-600">
        Re-runs the full rule engine over the uploaded records. Shows which findings
        are new, unchanged, changed, resolved, or permanently rejected.
      </p>

      {!result && (
        <button
          onClick={handleRerun}
          disabled={running}
          className="bg-slate-700 text-white px-5 py-2 rounded text-sm hover:bg-slate-900 disabled:opacity-50"
        >
          {running ? 'Running…' : '↻ Run now'}
        </button>
      )}

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {result && (
        <div className="space-y-5">
          {/* Summary pills */}
          <div className="flex flex-wrap gap-3">
            {(Object.keys(CATEGORY_META) as (keyof RerunResult['diff'])[]).map((cat) => (
              <div
                key={cat}
                className={`border rounded px-3 py-2 text-sm font-medium ${CATEGORY_META[cat].color}`}
              >
                {CATEGORY_META[cat].icon} {CATEGORY_META[cat].label}: {result.summary[cat]}
              </div>
            ))}
          </div>

          {/* Per-category diff tables */}
          {(Object.keys(CATEGORY_META) as (keyof RerunResult['diff'])[]).map((cat) => {
            const entries = result.diff[cat];
            if (entries.length === 0) return null;
            const meta = CATEGORY_META[cat];
            return (
              <div key={cat} className={`border rounded-lg ${meta.color}`}>
                <div className="px-4 py-2 border-b font-semibold text-sm">
                  {meta.icon} {meta.label} ({entries.length})
                </div>
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left px-3 py-1.5 font-medium">ID</th>
                      <th className="text-left px-3 py-1.5 font-medium">Type</th>
                      <th className="text-left px-3 py-1.5 font-medium">Summary</th>
                      {cat === 'changed' && (
                        <th className="text-left px-3 py-1.5 font-medium">Previous summary</th>
                      )}
                      {cat === 'resolved' && (
                        <th className="text-left px-3 py-1.5 font-medium">Note</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((e: RerunDiffEntry) => (
                      <tr key={e.finding_id} className="border-b last:border-0">
                        <td className="px-3 py-1.5">#{e.finding_id}</td>
                        <td className="px-3 py-1.5 font-mono">{e.finding_type}</td>
                        <td className="px-3 py-1.5">{e.summary}</td>
                        {cat === 'changed' && (
                          <td className="px-3 py-1.5 line-through text-slate-400">
                            {e.prev_summary}
                          </td>
                        )}
                        {cat === 'resolved' && (
                          <td className="px-3 py-1.5 text-green-700">{e.note}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}

          <div className="flex gap-3">
            <button
              onClick={handleRerun}
              disabled={running}
              className="bg-slate-700 text-white px-4 py-1.5 rounded text-sm hover:bg-slate-900 disabled:opacity-50"
            >
              {running ? 'Running…' : '↻ Run again'}
            </button>
            <button onClick={onBack} className="text-indigo-600 hover:underline text-sm">
              ← Back to findings
            </button>
          </div>

          <p className="text-xs text-slate-400 border-t pt-3">
            ⚠ Findings are leads for human review, not ownership decisions.
          </p>
        </div>
      )}
    </div>
  );
}
