import { useState, useEffect, useCallback, useMemo } from 'react';
import { getCaseCandidates, reviewCandidate } from '../api';
import type { MatchCandidate } from '../types';
import { Card, CardBody } from './ui/Card';
import { Button } from './ui/Button';
import { StatusPill } from './ui/Badge';
import { EmptyState } from './ui/EmptyState';
import { Callout } from './ui/Callout';
import {
  Link2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Clock,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useToast } from './ui/Toast';

function ScoreBar({ score, label }: { score: number; label?: string }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 90
      ? 'bg-emerald-500'
      : pct >= 75
      ? 'bg-brand-500'
      : pct >= 50
      ? 'bg-amber-500'
      : 'bg-rose-400';

  return (
    <div className="flex items-center gap-2">
      {label && <span className="font-mono text-[11px] text-slate-500 w-14 shrink-0">{label}</span>}
      <div className="w-20 sm:w-24 h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-mono font-medium text-slate-700 w-8">{pct}%</span>
    </div>
  );
}

interface Props {
  caseId: number;
}

export default function CandidatesSection({ caseId }: Props) {
  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [actionState, setActionState] = useState<Record<number, 'working' | 'done' | 'error'>>({});

  const { toast } = useToast();

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getCaseCandidates(caseId)
      .then(setCandidates)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  async function doReview(candidateId: number, action: 'accept' | 'reject') {
    setActionState((prev) => ({ ...prev, [candidateId]: 'working' }));
    try {
      await reviewCandidate(caseId, candidateId, action);
      setActionState((prev) => ({ ...prev, [candidateId]: 'done' }));
      toast({
        type: action === 'accept' ? 'success' : 'info',
        title: action === 'accept' ? 'Candidate accepted' : 'Candidate rejected',
        message:
          action === 'reject'
            ? 'Rejected pair is permanently suppressed and will not be re-proposed on reruns.'
            : 'Candidate link accepted.',
      });
      load();
    } catch {
      setActionState((prev) => ({ ...prev, [candidateId]: 'error' }));
      toast({
        type: 'error',
        title: 'Review action failed',
        message: 'Could not record candidate review.',
      });
    }
  }

  const metrics = useMemo(() => {
    const total = candidates.length;
    const pending = candidates.filter((c) => c.status === 'pending').length;
    const accepted = candidates.filter((c) => c.status === 'accepted').length;
    const rejected = candidates.filter((c) => c.status === 'rejected').length;
    return { total, pending, accepted, rejected };
  }, [candidates]);

  return (
    <div className="space-y-6">
      {/* Header & Metrics */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200">
        <div>
          <h3 className="text-base font-semibold text-slate-800">Match Candidates Queue</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Fuzzy recording-to-work links proposed with corroborating metadata (title, performer, duration)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="xs"
            onClick={load}
            loading={loading}
            icon={<RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Total Proposed</span>
            <p className="text-xl font-bold text-slate-900 mt-0.5">{metrics.total}</p>
          </div>
          <Link2 className="w-4 h-4 text-slate-400" />
        </div>

        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-amber-600 tracking-wider">Pending Review</span>
            <p className="text-xl font-bold text-amber-700 mt-0.5">{metrics.pending}</p>
          </div>
          <Clock className="w-4 h-4 text-amber-500" />
        </div>

        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-emerald-600 tracking-wider">Accepted</span>
            <p className="text-xl font-bold text-emerald-700 mt-0.5">{metrics.accepted}</p>
          </div>
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
        </div>

        <div className="p-3 rounded-lg bg-white border border-slate-200/90 shadow-subtle flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider">Rejected</span>
            <p className="text-xl font-bold text-slate-600 mt-0.5">{metrics.rejected}</p>
          </div>
          <XCircle className="w-4 h-4 text-slate-400" />
        </div>
      </div>

      {error && (
        <Callout type="error" title="Failed to load candidates">
          {error}
        </Callout>
      )}

      {loading && candidates.length === 0 ? (
        <div className="py-12 text-center text-xs text-slate-500">Loading candidates…</div>
      ) : candidates.length === 0 ? (
        <EmptyState
          icon={<Link2 className="w-8 h-8 text-slate-400 stroke-1" />}
          title="No fuzzy match candidates proposed"
          description="Candidates are proposed when titles are similar and corroborated by performer name or duration."
        />
      ) : (
        <div className="space-y-4">
          {candidates.map((c) => {
            const isPending = c.status === 'pending';
            const isExpanded = expanded === c.id;
            const st = actionState[c.id];

            return (
              <Card key={c.id} className="bg-white hover:border-slate-300 transition-colors">
                <CardBody className="p-4 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-mono text-xs font-semibold text-slate-500">#{c.id}</span>
                      <div className="flex items-center gap-1.5 font-mono text-xs">
                        <span className="text-slate-500 font-sans">Rec ID:</span>
                        <code className="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 font-bold text-slate-800">
                          {c.left_record_id}
                        </code>
                        <span className="text-slate-400">↔</span>
                        <span className="text-slate-500 font-sans">Work ID:</span>
                        <code className="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 font-bold text-slate-800">
                          {c.right_record_id}
                        </code>
                      </div>
                      <StatusPill status={c.status} />
                    </div>

                    <div className="flex items-center gap-4">
                      {/* Overall Composite Score */}
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500 font-medium">Composite:</span>
                        <ScoreBar score={c.score} />
                      </div>

                      {/* Action buttons */}
                      {isPending ? (
                        <div className="flex items-center gap-2">
                          <Button
                            variant="success"
                            size="xs"
                            onClick={() => doReview(c.id, 'accept')}
                            disabled={st === 'working'}
                            loading={st === 'working'}
                            icon={<CheckCircle2 className="w-3 h-3" />}
                          >
                            Accept
                          </Button>
                          <Button
                            variant="destructive"
                            size="xs"
                            onClick={() => doReview(c.id, 'reject')}
                            disabled={st === 'working'}
                            loading={st === 'working'}
                            icon={<XCircle className="w-3 h-3" />}
                          >
                            Reject
                          </Button>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Reviewed</span>
                      )}

                      <button
                        type="button"
                        onClick={() => setExpanded(isExpanded ? null : c.id)}
                        className="text-slate-400 hover:text-slate-700 p-1 rounded focus-ring"
                        aria-label={isExpanded ? 'Collapse' : 'Expand'}
                      >
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Reasons summary pills */}
                  {c.reasons && c.reasons.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap pt-1">
                      {c.reasons.map((reason, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-slate-50 border border-slate-200 text-slate-700"
                        >
                          <Sparkles className="w-2.5 h-2.5 text-brand-600" />
                          <span>{reason}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Expanded Breakdown */}
                  {isExpanded && (
                    <div className="pt-3 border-t border-slate-100 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs bg-slate-50/60 p-3 rounded-lg">
                      {/* Per-field score bars */}
                      <div className="space-y-2">
                        <p className="font-semibold text-slate-700 text-xs uppercase tracking-wider">
                          Per-Field Score Breakdown
                        </p>
                        {c.field_scores && Object.keys(c.field_scores).length > 0 ? (
                          <div className="space-y-1.5">
                            {Object.entries(c.field_scores).map(([field, score]) => (
                              <div key={field} className="flex items-center justify-between">
                                <ScoreBar score={score} label={field} />
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-slate-400">No field scores recorded.</p>
                        )}
                      </div>

                      {/* Review audit detail */}
                      <div className="space-y-2">
                        <p className="font-semibold text-slate-700 text-xs uppercase tracking-wider">
                          Corroboration & Audit Trail
                        </p>
                        <p className="text-slate-600 leading-relaxed text-[11px]">
                          Title similarity alone does not qualify a match. Proposer requires performer name
                          similarity ≥ 85% OR duration within ±3 seconds.
                        </p>
                        {c.reviewed_by && (
                          <div className="pt-2 border-t border-slate-200/60 text-slate-500 text-[11px]">
                            Reviewed by <strong>{c.reviewed_by}</strong> on{' '}
                            {new Date(c.reviewed_at!).toLocaleString()}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}

      {/* Footer disclaimer */}
      <p className="text-xs text-slate-400 border-t border-slate-200 pt-3">
        ⚠ Candidates are fuzzy suggestions for human review, not confirmed links. Rejecting a candidate
        permanently prevents it from being re-proposed on subsequent runs.
      </p>
    </div>
  );
}
