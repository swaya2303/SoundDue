import { useState, useEffect, useRef } from 'react';
import { getFinding, reviewFinding } from '../api';
import type { FindingDetail as FD, Evidence } from '../types';
import { SeverityBadge, StatusPill } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHeader, CardBody } from './ui/Card';
import { Callout } from './ui/Callout';
import { MonospaceValue } from './ui/KeyValue';
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Edit3,
  FileSpreadsheet,
  Split,
  ArrowRight,
} from 'lucide-react';
import { useToast } from './ui/Toast';

function sanitise(msg: unknown): string {
  if (Array.isArray(msg)) return msg.map(sanitise).join(', ');
  if (typeof msg !== 'string') return String(msg ?? '');
  return msg.replace(/\bunclaimed\b/gi, 'missing from the supplied records');
}

interface Props {
  findingId: number;
  caseId: number;
  onBack: () => void;
}

export default function FindingDetail({ findingId, caseId: _caseId, onBack }: Props) {
  const [detail, setDetail] = useState<FD | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Review form state
  const [reviewMode, setReviewMode] = useState<'accept' | 'reject' | 'correct' | null>(null);
  const [note, setNote] = useState('');
  const [correctedValues, setCorrectedValues] = useState<Record<string, string>>({});
  const [correctionKey, setCorrectionKey] = useState('');
  const [correctionVal, setCorrectionVal] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [reviewMsg, setReviewMsg] = useState('');
  const [reviewError, setReviewError] = useState('');

  const evidenceRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const { toast } = useToast();

  useEffect(() => {
    setLoading(true);
    getFinding(findingId)
      .then((d) => setDetail(d as FD))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [findingId]);

  async function submitReview() {
    if (!detail || !reviewMode) return;
    if (reviewMode === 'correct' && !note.trim()) {
      setReviewError('A note is required for corrections.');
      return;
    }
    setReviewing(true);
    setReviewError('');
    try {
      const res = await reviewFinding(findingId, {
        decision: reviewMode,
        note: note.trim(),
        corrected_values: reviewMode === 'correct' ? correctedValues : {},
      });
      const msg = `Decision recorded: ${res.decision} → ${res.new_status}`;
      setReviewMsg(msg);
      toast({
        type: 'success',
        title: 'Review saved',
        message: `Auditor verdict ${res.decision} applied (${res.new_status}).`,
      });
      // Refresh detail
      const updated = await getFinding(findingId);
      setDetail(updated as FD);
      setReviewMode(null);
      setNote('');
      setCorrectedValues({});
    } catch (e) {
      setReviewError(String(e));
      toast({
        type: 'error',
        title: 'Review failed',
        message: String(e),
      });
    } finally {
      setReviewing(false);
    }
  }

  function scrollToEvidence(recId: number) {
    const el = evidenceRefs.current[recId];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('ring-2', 'ring-brand-500', 'bg-brand-50/50');
      setTimeout(() => {
        el.classList.remove('ring-2', 'ring-brand-500', 'bg-brand-50/50');
      }, 2000);
    }
  }

  if (loading) {
    return (
      <Card className="bg-white p-12 text-center text-xs text-slate-500">
        <div className="flex flex-col items-center justify-center gap-2">
          <div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
          <span>Loading finding #{findingId} audit trace…</span>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Callout type="error" title="Failed to load finding">
        {error}
      </Callout>
    );
  }

  if (!detail) return null;

  const rt = detail.rule_trace;

  return (
    <div className="space-y-6">
      {/* Top Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-brand-600 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors focus-ring"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>← Back to findings</span>
          </button>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-base font-bold text-slate-900">Finding #{detail.id}</h2>
              <SeverityBadge severity={detail.severity} />
              <StatusPill status={detail.status} />
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                {detail.rule_id || rt?.rule_id || 'R1'} v{detail.rule_version || rt?.rule_version || '1.0'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Single review notification banner */}
      {reviewMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs font-medium text-emerald-800 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{reviewMsg}</span>
        </div>
      )}

      {/* 2-Column Audit Workbench Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Glass-Box Reasoning (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          <div className="flex items-center justify-between pb-1 border-b border-slate-200/80">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Why this was flagged
            </h3>
            <span className="text-[11px] font-medium text-slate-500">Glass-Box Reasoning (6 Parts)</span>
          </div>

          {/* 1. ISSUE */}
          <Section title="Issue">
            <p className="text-sm text-slate-800 font-medium leading-relaxed">
              {sanitise(detail.summary)}
            </p>
            <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center gap-2 text-xs text-slate-500">
              <span className="font-medium text-slate-600">Finding Type:</span>
              <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                {detail.finding_type}
              </code>
            </div>
          </Section>

          {/* 2. EVIDENCE */}
          <Section title="Evidence">
            <div className="space-y-4">
              {detail.evidence.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No evidence records attached to this finding.</p>
              ) : (
                detail.evidence.map((ev, i) => (
                  <div
                    key={ev.id || i}
                    ref={(el) => {
                      if (ev.source_record_id != null) {
                        evidenceRefs.current[ev.source_record_id] = el;
                      }
                    }}
                    className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/60 transition-all space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2 font-semibold text-slate-700">
                        <FileSpreadsheet className="w-3.5 h-3.5 text-brand-600" />
                        <span>Record {i + 1}</span>
                        {ev.source_row != null && (
                          <span className="font-mono font-normal text-slate-500 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                            Row {ev.source_row}
                          </span>
                        )}
                        {ev.source_record_id != null && (
                          <span className="font-mono font-normal text-slate-500 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                            Record ID #{ev.source_record_id}
                          </span>
                        )}
                      </div>
                    </div>

                    <EvidenceFieldTable fields={ev.field_values} />

                    {ev.note && (
                      <p className="text-xs text-amber-800 bg-amber-50 p-2 rounded border border-amber-200/80 leading-relaxed">
                        <strong>Source Note:</strong> {sanitise(ev.note)}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </Section>

          {/* 3. RULE */}
          <Section title="Rule">
            {rt ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-xs flex-wrap">
                  <span className="font-medium text-slate-600">
                    Rule ID: <code className="font-mono font-semibold text-slate-800">{rt.rule_id}</code>
                  </span>
                  <span className="text-slate-400">·</span>
                  <span className="font-medium text-slate-600">
                    Version: <code className="font-mono font-semibold text-slate-800">{rt.rule_version}</code>
                  </span>
                  <span className="text-slate-400">·</span>
                  <span className="text-slate-600">
                    Evaluated {new Date(rt.evaluated_at).toLocaleString()}
                  </span>
                </div>

                {rt.matched_conditions && rt.matched_conditions.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Matched Symbolic Conditions
                    </p>
                    <ol className="space-y-1.5">
                      {rt.matched_conditions.map((cond, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2.5 p-2 rounded bg-emerald-50/70 border border-emerald-200 text-xs text-emerald-950 font-mono"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                          <span className="leading-relaxed">{sanitise(cond)}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {rt.supporting_record_ids && rt.supporting_record_ids.length > 0 && (
                  <div className="pt-1">
                    <p className="text-xs font-semibold text-slate-600 mb-1">Supporting Records:</p>
                    <div className="flex gap-2 flex-wrap">
                      {rt.supporting_record_ids.map((id) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => scrollToEvidence(id)}
                          className="font-mono text-xs px-2 py-0.5 rounded bg-brand-50 text-brand-700 hover:bg-brand-100 border border-brand-200 transition-colors focus-ring"
                        >
                          Record #{id} ↗
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {rt.missing_information && (
                  <Callout type="warning" title="Missing Information">
                    {sanitise(rt.missing_information)}
                  </Callout>
                )}

                {rt.conflicting_information && (
                  <Callout type="error" title="Conflicting Information">
                    {sanitise(rt.conflicting_information)}
                  </Callout>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No symbolic rule trace recorded for this finding.</p>
            )}
          </Section>

          {/* 4. UNCERTAINTY (Distinct Callout so it is never overlooked) */}
          <Section title="Uncertainty">
            <Callout type="warning" title="Uncertainty & Ambiguity Disclosure">
              <p className="text-xs leading-relaxed text-amber-950">
                {sanitise(detail.uncertainty || 'No uncertainty note provided by the rule generator.')}
              </p>
            </Callout>
          </Section>

          {/* 5. NEXT STEP */}
          <Section title="Next step">
            <div className="p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-950 text-xs leading-relaxed flex items-start gap-2.5">
              <ArrowRight className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
              <span>
                {sanitise(
                  detail.next_step ||
                    'Verify the ownership agreement and registration status before requesting a correction.'
                )}
              </span>
            </div>
          </Section>

          {/* 6. REVIEW HISTORY */}
          <Section title="Review history">
            {detail.review_decisions.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No review actions recorded yet.</p>
            ) : (
              <div className="space-y-3 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-slate-200">
                {detail.review_decisions.map((rd) => (
                  <div key={rd.id} className="relative flex items-start gap-3 pl-8 text-xs">
                    <span className="absolute left-2 top-1.5 w-3 h-3 rounded-full bg-white border-2 border-brand-600" />
                    <div className="flex-1 p-3 rounded-lg bg-white border border-slate-200 shadow-subtle space-y-1.5">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <StatusPill status={rd.decision} size="sm" />
                          <span className="font-semibold text-slate-700">by {rd.actor}</span>
                        </div>
                        <span className="text-slate-500 text-[11px]">
                          {new Date(rd.decided_at).toLocaleString()}
                        </span>
                      </div>

                      {rd.note && (
                        <p className="text-slate-700 bg-slate-50 p-2 rounded border border-slate-100 italic">
                          "{rd.note}"
                        </p>
                      )}

                      {rd.corrected_values && Object.keys(rd.corrected_values).length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-100">
                          <p className="text-[11px] font-semibold text-slate-500 mb-1">
                            Applied Field Corrections:
                          </p>
                          <EvidenceFieldTable fields={rd.corrected_values} />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        {/* Right Column: Comparison & Action Workbench (5 cols, sticky) */}
        <div className="lg:col-span-5 space-y-5 lg:sticky lg:top-20">
          {/* Side-by-side comparison (when 2+ records) */}
          {detail.evidence.length >= 2 && (
            <Card className="bg-white">
              <CardHeader
                title="Conflicting Records Comparison"
                subtitle="Source A vs Source B — Discrepancies highlighted"
                action={<Split className="w-4 h-4 text-brand-600" />}
              />
              <CardBody className="p-0">
                <SideBySideComparison evidence={detail.evidence} />
              </CardBody>
            </Card>
          )}

          {/* Review & Resolution Action Card */}
          <Card className="bg-white border-brand-200 shadow-card">
            <CardHeader
              title="Review this finding"
              subtitle="Record a human decision. Findings are leads for review."
            />
            <CardBody className="space-y-4">
              <p className="text-xs text-slate-500">
                Record your assessment below. The review decision and any corrected values are
                stored in an immutable append-only audit trail.
              </p>

              {reviewError && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                  {reviewError}
                </div>
              )}

              {reviewMode === null ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-2">
                    <Button
                      variant="success"
                      size="sm"
                      onClick={() => setReviewMode('accept')}
                      icon={<CheckCircle2 className="w-3.5 h-3.5" />}
                    >
                      Accept
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => setReviewMode('reject')}
                      icon={<XCircle className="w-3.5 h-3.5" />}
                    >
                      Reject
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setReviewMode('correct')}
                      icon={<Edit3 className="w-3.5 h-3.5" />}
                    >
                      Correct record
                    </Button>
                  </div>
                  <p className="text-[11px] text-slate-600 text-center">
                    {detail.status !== 'open'
                      ? `Currently marked as ${detail.status}. You may record a subsequent decision.`
                      : 'Choose an action to record your audit verdict.'}
                  </p>
                </div>
              ) : (
                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-700">
                      {reviewMode === 'accept' && 'Accept Finding'}
                      {reviewMode === 'reject' && 'Reject Discrepancy'}
                      {reviewMode === 'correct' && 'Correct Record Values'}
                    </span>
                    <button
                      onClick={() => setReviewMode(null)}
                      className="text-xs text-slate-500 hover:text-slate-700"
                    >
                      Cancel
                    </button>
                  </div>

                  {/* Impact Notice */}
                  <p className="text-[11px] text-slate-600 leading-relaxed bg-white p-2 rounded border border-slate-200/80">
                    {reviewMode === 'accept' &&
                      'Marks this discrepancy as verified. The finding transitions to resolved.'}
                    {reviewMode === 'reject' &&
                      'This rejection will persist across reruns. The candidate pair or rule will not re-trigger.'}
                    {reviewMode === 'correct' &&
                      'Creates a new immutable record version with your corrections and resolves the finding.'}
                  </p>

                  {/* Note input */}
                  <div>
                    <label className="text-xs font-semibold text-slate-700 block mb-1">
                      Reviewer Note <span className="text-rose-500">*</span>
                    </label>
                    {reviewMode === 'correct' && (
                      <p className="text-[11px] text-slate-500 mb-1">
                        Explain what was incorrect and the document or contract confirming the correction.
                      </p>
                    )}
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      rows={3}
                      className="w-full border border-slate-300 rounded-lg p-2 text-xs focus-ring bg-white"
                      placeholder={
                        reviewMode === 'correct'
                          ? 'Explain what was incorrect and how it was fixed…'
                          : 'Reason for accepting or rejecting this finding…'
                      }
                      required
                    />
                  </div>

                  {/* Corrected values form */}
                  {reviewMode === 'correct' && (
                    <div className="space-y-2 pt-2 border-t border-slate-200">
                      <p className="text-xs font-semibold text-slate-700">
                        Field-level Corrections
                        <span className="text-slate-500 font-normal ml-1">(applied to record)</span>
                      </p>

                      {/* Display added corrections */}
                      {Object.entries(correctedValues).map(([k, v]) => (
                        <div
                          key={k}
                          className="flex items-center justify-between gap-2 p-1.5 rounded bg-white border border-slate-200 text-xs"
                        >
                          <div className="flex items-center gap-1.5 font-mono text-[11px]">
                            <span className="font-semibold text-slate-700">{k}</span>
                            <span className="text-slate-500">→</span>
                            <span className="text-emerald-700 font-bold">{v}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              setCorrectedValues((prev) => {
                                const next = { ...prev };
                                delete next[k];
                                return next;
                              })
                            }
                            className="text-slate-500 hover:text-rose-600 p-0.5"
                          >
                            ✕
                          </button>
                        </div>
                      ))}

                      {/* Form to add field */}
                      <div className="flex gap-2">
                        <input
                          value={correctionKey}
                          onChange={(e) => setCorrectionKey(e.target.value)}
                          placeholder="field name"
                          className="border border-slate-300 rounded px-2 py-1 text-xs w-1/3 bg-white focus-ring"
                        />
                        <input
                          value={correctionVal}
                          onChange={(e) => setCorrectionVal(e.target.value)}
                          placeholder="corrected value"
                          className="border border-slate-300 rounded px-2 py-1 text-xs flex-1 bg-white focus-ring"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="xs"
                          onClick={() => {
                            if (!correctionKey.trim()) return;
                            setCorrectedValues((prev) => ({
                              ...prev,
                              [correctionKey.trim()]: correctionVal,
                            }));
                            setCorrectionKey('');
                            setCorrectionVal('');
                          }}
                        >
                          Add
                        </Button>
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2 pt-2">
                    <Button
                      variant="primary"
                      size="sm"
                      className="flex-1"
                      onClick={submitReview}
                      disabled={reviewing || (reviewMode === 'correct' && !note.trim())}
                      loading={reviewing}
                    >
                      {reviewing ? 'Saving…' : 'Confirm'}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setReviewMode(null);
                        setNote('');
                        setCorrectedValues({});
                        setReviewError('');
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="bg-white">
      <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
        <h3 className="font-bold text-slate-700 tracking-wider text-xs">
          {title.toUpperCase()}
        </h3>
      </div>
      <div className="p-5">{children}</div>
    </Card>
  );
}

function EvidenceFieldTable({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields || {}).filter(([k]) => k !== 'row_data');
  if (entries.length === 0) return <p className="text-xs text-slate-500">No field values recorded.</p>;

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="text-xs w-full">
        <tbody className="divide-y divide-slate-100">
          {entries.map(([k, v]) => (
            <tr key={k} className="hover:bg-slate-50/60">
              <td className="py-1 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap w-1/3 bg-slate-50/30">
                {k}
              </td>
              <td className="py-1 px-3 text-slate-800">
                <MonospaceValue value={typeof v === 'object' ? JSON.stringify(v) : String(v ?? '—')} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SideBySideComparison({ evidence }: { evidence: Evidence[] }) {
  const allKeys = [...new Set(evidence.flatMap((ev) => Object.keys(ev.field_values || {})))].filter(
    (k) => k !== 'row_data'
  );

  const left = evidence[0];
  const right = evidence[1];

  return (
    <div className="overflow-x-auto">
      <table className="text-xs min-w-full">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            <th className="text-left px-3 py-2 font-semibold text-slate-600">Field</th>
            <th className="text-left px-3 py-2 font-semibold text-slate-600">
              Source A {left.source_record_id ? `(#${left.source_record_id})` : ''}
            </th>
            <th className="text-left px-3 py-2 font-semibold text-slate-600">
              Source B {right.source_record_id ? `(#${right.source_record_id})` : ''}
            </th>
            <th className="text-center px-2 py-2 font-semibold text-slate-600">Match</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {allKeys.map((k) => {
            const lv = String(left.field_values[k] ?? '—');
            const rv = String(right.field_values[k] ?? '—');
            const match = lv === rv;

            return (
              <tr
                key={k}
                className={match ? 'hover:bg-slate-50' : 'bg-rose-50/40 hover:bg-rose-50/70'}
              >
                <td className="px-3 py-1.5 font-mono text-[11px] text-slate-500 font-medium">
                  {k}
                </td>
                <td className="px-3 py-1.5 text-slate-800 font-mono text-[11px]">{lv}</td>
                <td
                  className={`px-3 py-1.5 font-mono text-[11px] ${
                    !match ? 'text-rose-700 font-bold' : 'text-slate-800'
                  }`}
                >
                  {rv}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {match ? (
                    <span className="text-emerald-600 font-bold text-xs" title="Match">
                      ✓
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-rose-100 text-rose-700 font-bold text-[10px]"
                      title="Discrepancy"
                    >
                      ≠
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
