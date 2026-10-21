import { useState, useEffect, useCallback, useMemo } from 'react';
import { tableFeatures, createColumnHelper, useTable } from '@tanstack/react-table';
import { getCaseFindings } from '../api';
import type { Finding } from '../types';
import FindingDetail from './FindingDetail';
import RerunPanel from './RerunPanel';

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Finding>();

function sanitise(msg: string): string {
  return msg.replace(/\bunclaimed\b/gi, 'missing from the supplied records');
}

function SeverityBadge({ severity }: { severity: Finding['severity'] }) {
  const cls =
    severity === 'error'
      ? 'bg-red-100 text-red-700'
      : severity === 'warning'
      ? 'bg-amber-100 text-amber-700'
      : 'bg-blue-100 text-blue-700';
  return (
    <span className={`text-xs rounded px-2 py-0.5 font-medium capitalize ${cls}`}>
      {severity}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const cls =
    status === 'resolved'
      ? 'bg-green-100 text-green-700'
      : status === 'accepted'
      ? 'bg-indigo-100 text-indigo-700'
      : status === 'rejected'
      ? 'bg-red-100 text-red-700'
      : 'bg-slate-100 text-slate-600';
  return (
    <span className={`text-xs rounded px-2 py-0.5 capitalize ${cls}`}>{status}</span>
  );
}

interface Props {
  caseId: number;
}

export default function FindingsSection({ caseId }: Props) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showRerun, setShowRerun] = useState(false);

  // Filters
  const [ruleFilter, setRuleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getCaseFindings(caseId)
      .then(setFindings)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [caseId]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    return findings.filter((f) => {
      if (ruleFilter && f.rule_id !== ruleFilter) return false;
      if (statusFilter && f.status !== statusFilter) return false;
      return true;
    });
  }, [findings, ruleFilter, statusFilter]);

  const uniqueRules = useMemo(
    () => [...new Set(findings.map((f) => f.rule_id).filter(Boolean))],
    [findings],
  );
  const uniqueStatuses = useMemo(
    () => [...new Set(findings.map((f) => f.status))],
    [findings],
  );

  const columns = helper.columns([
    helper.accessor('severity', {
      header: 'Severity',
      cell: (ctx) => <SeverityBadge severity={ctx.cell.getValue()} />,
    }),
    helper.accessor('finding_type', {
      header: 'Type',
      cell: (ctx) => (
        <span className="font-mono text-xs text-slate-700">{ctx.cell.getValue()}</span>
      ),
    }),
    helper.accessor('summary', {
      header: 'Summary',
      cell: (ctx) => <span className="text-sm">{sanitise(ctx.cell.getValue())}</span>,
    }),
    helper.accessor('status', {
      header: 'Status',
      cell: (ctx) => <StatusPill status={ctx.cell.getValue()} />,
    }),
    helper.accessor('created_at', {
      header: 'Found',
      cell: (ctx) => (
        <span className="text-xs text-slate-500">
          {new Date(ctx.cell.getValue()).toLocaleString()}
        </span>
      ),
    }),
    helper.display({
      id: 'action',
      header: '',
      cell: (ctx) => (
        <button
          onClick={() => { setSelectedId(ctx.row.original.id); setShowRerun(false); }}
          className="text-indigo-600 hover:underline text-xs"
        >
          View →
        </button>
      ),
    }),
  ]);

  const table = useTable({ features, columns, data: filtered });

  if (selectedId !== null) {
    return (
      <FindingDetail
        findingId={selectedId}
        caseId={caseId}
        onBack={() => { setSelectedId(null); load(); }}
      />
    );
  }

  if (showRerun) {
    return <RerunPanel caseId={caseId} onBack={() => { setShowRerun(false); load(); }} />;
  }

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h3 className="font-semibold text-slate-700">
          Findings{findings.length > 0 ? ` (${findings.length})` : ''}
        </h3>
        <div className="flex gap-2 flex-wrap">
          {/* Rule filter */}
          <select
            value={ruleFilter}
            onChange={(e) => setRuleFilter(e.target.value)}
            className="border rounded px-2 py-1 text-xs"
          >
            <option value="">All rules</option>
            {uniqueRules.map((r) => (
              <option key={r} value={r ?? ''}>{r}</option>
            ))}
          </select>
          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border rounded px-2 py-1 text-xs"
          >
            <option value="">All statuses</option>
            {uniqueStatuses.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button onClick={load} className="text-indigo-600 text-xs hover:underline">
            Refresh
          </button>
          <button
            onClick={() => setShowRerun(true)}
            className="bg-slate-700 text-white px-3 py-1 rounded text-xs hover:bg-slate-900"
          >
            ↻ Rerun
          </button>
        </div>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : filtered.length === 0 ? (
        <p className="text-slate-500">
          {findings.length === 0
            ? 'No findings yet. Upload files, confirm mappings, then click Analyze.'
            : 'No findings match the current filters.'}
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
                <tr
                  key={row.id}
                  className="border-b last:border-0 hover:bg-slate-50 cursor-pointer"
                  onClick={() => { setSelectedId(row.original.id); setShowRerun(false); }}
                >
                  {row.getAllCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2">
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer note */}
      <p className="mt-6 text-xs text-slate-400 border-t pt-3">
        ⚠ Findings are leads for human review, not ownership decisions. Each finding
        must be assessed by a qualified person before any action is taken.
      </p>
    </div>
  );
}
