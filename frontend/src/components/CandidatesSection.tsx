import { useState, useEffect, useCallback } from 'react';
import { tableFeatures, createColumnHelper, useTable } from '@tanstack/react-table';
import { getCaseCandidates, reviewCandidate } from '../api';
import type { MatchCandidate } from '../types';

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, MatchCandidate>();

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 90 ? 'bg-green-500' : pct >= 75 ? 'bg-amber-500' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono">{pct}%</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'accepted' ? 'bg-green-100 text-green-700'
    : status === 'rejected' ? 'bg-red-100 text-red-700'
    : 'bg-amber-100 text-amber-700';
  return <span className={`text-xs rounded px-2 py-0.5 capitalize ${cls}`}>{status}</span>;
}

interface Props { caseId: number }

export default function CandidatesSection({ caseId }: Props) {
  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [actionState, setActionState] = useState<Record<number, 'working' | 'done' | 'error'>>({});

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getCaseCandidates(caseId)
      .then(setCandidates)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [caseId]);

  useEffect(() => { load(); }, [load]);

  async function doReview(candidateId: number, action: 'accept' | 'reject') {
    setActionState((prev) => ({ ...prev, [candidateId]: 'working' }));
    try {
      await reviewCandidate(caseId, candidateId, action);
      setActionState((prev) => ({ ...prev, [candidateId]: 'done' }));
      load();
    } catch {
      setActionState((prev) => ({ ...prev, [candidateId]: 'error' }));
    }
  }

  const pendingCount = candidates.filter((c) => c.status === 'pending').length;

  const columns = helper.columns([
    helper.accessor('id', { header: 'ID' }),
    helper.accessor('left_record_id', { header: 'Recording ID' }),
    helper.accessor('right_record_id', { header: 'Work ID' }),
    helper.accessor('score', {
      header: 'Score',
      cell: (ctx) => <ScoreBar score={ctx.cell.getValue()} />,
    }),
    helper.accessor('status', {
      header: 'Status',
      cell: (ctx) => <StatusBadge status={ctx.cell.getValue()} />,
    }),
    helper.display({
      id: 'expand',
      header: 'Details',
      cell: (ctx) => (
        <button
          onClick={() => setExpanded(expanded === ctx.row.original.id ? null : ctx.row.original.id)}
          className="text-indigo-600 hover:underline text-xs"
        >
          {expanded === ctx.row.original.id ? 'Hide' : 'Show'}
        </button>
      ),
    }),
    helper.display({
      id: 'actions',
      header: 'Actions',
      cell: (ctx) => {
        const c = ctx.row.original;
        if (c.status !== 'pending') return <span className="text-xs text-slate-400">—</span>;
        const st = actionState[c.id];
        return (
          <div className="flex gap-2">
            <button
              onClick={() => doReview(c.id, 'accept')}
              disabled={st === 'working'}
              className="text-xs bg-green-100 text-green-700 hover:bg-green-200 rounded px-2 py-0.5 disabled:opacity-50"
            >
              Accept
            </button>
            <button
              onClick={() => doReview(c.id, 'reject')}
              disabled={st === 'working'}
              className="text-xs bg-red-100 text-red-700 hover:bg-red-200 rounded px-2 py-0.5 disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        );
      },
    }),
  ]);

  const table = useTable({ features, columns, data: candidates });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-slate-700">
            Match Candidates
            {candidates.length > 0 && (
              <span className="ml-2 text-sm font-normal text-slate-500">
                ({candidates.length} total · {pendingCount} pending)
              </span>
            )}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Fuzzy recording-to-work links proposed by the matcher. Each needs human review.
          </p>
        </div>
        <button onClick={load} className="text-indigo-600 text-xs hover:underline">
          Refresh
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : candidates.length === 0 ? (
        <p className="text-slate-500">
          No candidates yet. Run Analyze to propose matches.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => (
                    <th key={h.id} className="text-left px-3 py-2 border-b text-slate-600 font-medium">
                      {h.isPlaceholder ? null : <table.FlexRender header={h} />}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <>
                  <tr key={row.id} className="border-b hover:bg-slate-50">
                    {row.getAllCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2">
                        <table.FlexRender cell={cell} />
                      </td>
                    ))}
                  </tr>
                  {expanded === row.original.id && (
                    <tr key={`${row.id}-detail`} className="border-b bg-slate-50">
                      <td colSpan={7} className="px-4 py-3">
                        <ScoreBreakdown candidate={row.original} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-6 text-xs text-slate-400 border-t pt-3">
        ⚠ Candidates are fuzzy suggestions for human review, not confirmed links.
        Rejecting a candidate prevents it from being re-proposed on subsequent runs.
      </p>
    </div>
  );
}

function ScoreBreakdown({ candidate }: { candidate: MatchCandidate }) {
  const { field_scores, reasons, reviewed_by, reviewed_at } = candidate;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
      <div>
        <p className="font-semibold text-slate-600 mb-1">Score breakdown</p>
        {field_scores && Object.keys(field_scores).length > 0 ? (
          <table className="w-full">
            <tbody>
              {Object.entries(field_scores).map(([k, v]) => (
                <tr key={k} className="border-b last:border-0">
                  <td className="py-0.5 pr-3 font-mono text-slate-500">{k}</td>
                  <td className="py-0.5"><ScoreBar score={v} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-400">No field scores available.</p>
        )}
      </div>
      <div>
        <p className="font-semibold text-slate-600 mb-1">Reasons</p>
        {reasons && reasons.length > 0 ? (
          <ul className="space-y-0.5">
            {reasons.map((r, i) => (
              <li key={i} className="text-slate-700">· {r}</li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-400">No reasons recorded.</p>
        )}
        {reviewed_by && (
          <p className="mt-2 text-slate-500">
            Reviewed by {reviewed_by} on {new Date(reviewed_at!).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
}
