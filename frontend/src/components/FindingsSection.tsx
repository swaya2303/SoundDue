import { useState, useEffect, useCallback, useMemo } from 'react';
import { tableFeatures, createColumnHelper, useTable } from '@tanstack/react-table';
import { getCaseFindings } from '../api';
import type { Finding } from '../types';
import FindingDetail from './FindingDetail';
import RerunPanel from './RerunPanel';
import { SeverityBadge, StatusPill } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHeader, CardBody } from './ui/Card';
import { EmptyState } from './ui/EmptyState';
import {
  Search,
  RefreshCw,
  RotateCcw,
  ArrowRight,
  ShieldAlert,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Finding>();

function sanitise(msg: string): string {
  return (msg || '').replace(/\bunclaimed\b/gi, 'missing from the supplied records');
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

  // Filters & Search
  const [search, setSearch] = useState('');
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

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    return findings.filter((f) => {
      if (ruleFilter && f.rule_id !== ruleFilter) return false;
      if (statusFilter && f.status !== statusFilter) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesSummary = f.summary?.toLowerCase().includes(q);
        const matchesType = f.finding_type?.toLowerCase().includes(q);
        const matchesRule = f.rule_id?.toLowerCase().includes(q);
        if (!matchesSummary && !matchesType && !matchesRule) return false;
      }
      return true;
    });
  }, [findings, ruleFilter, statusFilter, search]);

  const uniqueRules = useMemo(
    () => [...new Set(findings.map((f) => f.rule_id).filter(Boolean))],
    [findings]
  );
  const uniqueStatuses = useMemo(
    () => [...new Set(findings.map((f) => f.status))],
    [findings]
  );

  const metrics = useMemo(() => {
    const total = findings.length;
    const open = findings.filter((f) => f.status === 'open').length;
    const resolved = findings.filter((f) => f.status === 'resolved' || f.status === 'accepted').length;
    const warnings = findings.filter((f) => f.severity === 'warning').length;
    const errors = findings.filter((f) => f.severity === 'error').length;
    return { total, open, resolved, warnings, errors };
  }, [findings]);

  const columns = helper.columns([
    helper.accessor('severity', {
      header: 'Severity',
      cell: (ctx) => <SeverityBadge severity={ctx.cell.getValue()} />,
    }),
    helper.accessor('finding_type', {
      header: 'Finding Type',
      cell: (ctx) => (
        <span className="font-mono text-xs text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
          {ctx.cell.getValue()}
        </span>
      ),
    }),
    helper.accessor('summary', {
      header: 'Summary & Context',
      cell: (ctx) => (
        <span className="text-xs text-slate-800 font-medium leading-relaxed block max-w-xl">
          {sanitise(ctx.cell.getValue())}
        </span>
      ),
    }),
    helper.accessor('rule_id', {
      header: 'Rule',
      cell: (ctx) => {
        const row = ctx.row.original;
        return (
          <div className="font-mono text-xs text-slate-600">
            <span className="font-semibold text-slate-800">{row.rule_id || 'R1'}</span>
            <span className="text-slate-500 ml-1">v{row.rule_version || '1.0'}</span>
          </div>
        );
      },
    }),
    helper.accessor('status', {
      header: 'Status',
      cell: (ctx) => <StatusPill status={ctx.cell.getValue()} />,
    }),
    helper.accessor('created_at', {
      header: 'Detected',
      cell: (ctx) => (
        <span className="text-[11px] text-slate-500 whitespace-nowrap">
          {new Date(ctx.cell.getValue()).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      ),
    }),
    helper.display({
      id: 'action',
      header: '',
      cell: (ctx) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setSelectedId(ctx.row.original.id);
            setShowRerun(false);
          }}
          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-800 p-1 rounded focus-ring whitespace-nowrap"
        >
          <span>View</span>
          <ArrowRight className="w-3 h-3" />
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
        onBack={() => {
          setSelectedId(null);
          load();
        }}
      />
    );
  }

  if (showRerun) {
    return (
      <RerunPanel
        caseId={caseId}
        onBack={() => {
          setShowRerun(false);
          load();
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-slate-600 tracking-wider">Total Findings</span>
            <p className="text-xl font-bold text-slate-900 mt-0.5">{metrics.total}</p>
          </div>
          <ShieldAlert className="w-4 h-4 text-slate-500" />
        </div>

        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-amber-800 tracking-wider">Open for Review</span>
            <p className="text-xl font-bold text-amber-800 mt-0.5">{metrics.open}</p>
          </div>
          <AlertTriangle className="w-4 h-4 text-amber-600" />
        </div>

        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-emerald-800 tracking-wider">Resolved</span>
            <p className="text-xl font-bold text-emerald-800 mt-0.5">{metrics.resolved}</p>
          </div>
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
        </div>

        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-rose-800 tracking-wider">Errors / Discrepancies</span>
            <p className="text-xl font-bold text-rose-800 mt-0.5">{metrics.errors}</p>
          </div>
          <AlertCircle className="w-4 h-4 text-rose-600" />
        </div>
      </div>

      {/* Main Table Card */}
      <Card className="bg-white">
        <CardHeader
          title={
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-900 text-sm">Identified Findings</span>
              <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
                {findings.length}
              </span>
            </div>
          }
          subtitle="Discrepancies flagged by symbolic rules for human review"
          action={
            <div className="flex items-center gap-2 flex-wrap">
              {/* Search input */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter findings…"
                  aria-label="Filter findings by text or ID"
                  className="pl-8 pr-3 py-1 text-xs border border-slate-300 rounded-lg focus-ring w-40"
                />
              </div>

              {/* Rule filter */}
              <select
                value={ruleFilter}
                onChange={(e) => setRuleFilter(e.target.value)}
                aria-label="Filter by rule"
                className="border border-slate-300 rounded-lg px-2.5 py-1 text-xs bg-white text-slate-700 focus-ring font-medium"
              >
                <option value="">All rules</option>
                {uniqueRules.map((r) => (
                  <option key={r} value={r ?? ''}>
                    {r}
                  </option>
                ))}
              </select>

              {/* Status filter */}
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by status"
                className="border border-slate-300 rounded-lg px-2.5 py-1 text-xs bg-white text-slate-700 focus-ring font-medium capitalize"
              >
                <option value="">All statuses</option>
                {uniqueStatuses.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>

              <Button
                variant="outline"
                size="xs"
                onClick={load}
                loading={loading}
                icon={<RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />}
              >
                Refresh
              </Button>

              <Button
                variant="secondary"
                size="xs"
                onClick={() => setShowRerun(true)}
                icon={<RotateCcw className="w-3 h-3" />}
              >
                ↻ Rerun
              </Button>
            </div>
          }
        />

        <CardBody className="p-0">
          {error && (
            <div className="p-3 text-xs text-rose-700 bg-rose-50 border-b border-rose-100">
              {error}
            </div>
          )}

          {loading && findings.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-500">Loading findings…</div>
          ) : filtered.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={<CheckCircle2 className="w-8 h-8 text-slate-400" />}
                title={findings.length === 0 ? 'No findings.' : 'No findings match the current filter.'}
                description={
                  findings.length === 0
                    ? 'No findings. This does not prove the records are correct.'
                    : 'Try clearing your search query or status filter.'
                }
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id}>
                      {hg.headers.map((h) => (
                        <th
                          key={h.id}
                          className="text-left px-4 py-2.5 font-semibold text-slate-600 whitespace-nowrap bg-slate-50"
                        >
                          {h.isPlaceholder ? null : <table.FlexRender header={h} />}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => {
                        setSelectedId(row.original.id);
                        setShowRerun(false);
                      }}
                      className="hover:bg-brand-50/40 cursor-pointer transition-colors"
                    >
                      {row.getAllCells().map((cell) => (
                        <td key={cell.id} className="px-4 py-2.5 text-slate-700">
                          <table.FlexRender cell={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
