import { useState, useEffect } from 'react';
import { getFinding, reviewFinding } from '../api';
import type { FindingDetail as FD } from '../types';
import { StatusPill } from './FindingsSection';

function sanitise(msg: string) {
  return msg.replace(/\bunclaimed\b/gi, 'missing from the supplied records');
}

function SeverityBadge({ sev }: { sev: string }) {
  const cls =
    sev === 'error' ? 'bg-red-100 text-red-700'
    : sev === 'warning' ? 'bg-amber-100 text-amber-700'
    : 'bg-blue-100 text-blue-700';
  return <span className={`text-xs rounded px-2 py-0.5 font-medium capitalize ${cls}`}>{sev}</span>;
}

interface Props {
  findingId: number;
  caseId: number;
  onBack: () => void;
}

export default function FindingDetail({ findingId, onBack }: Props) {
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
      setReviewMsg(`Decision recorded: ${res.decision} → ${res.new_status}`);
      // Refresh detail
      const updated = await getFinding(findingId);
      setDetail(updated as FD);
      setReviewMode(null);
      setNote('');
      setCorrectedValues({});
    } catch (e) {
      setReviewError(String(e));
    } finally {
      setReviewing(false);
    }
  }

  if (loading) return <p className="text-slate-500">Loading finding…</p>;
  if (error) return <p className="text-red-600">{error}</p>;
  if (!detail) return null;

  const rt = detail.rule_trace;
  const canReview = detail.status === 'open';

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div className="flex items-start gap-4">
        <button onClick={onBack} className="text-indigo-600 hover:underline text-sm mt-0.5">
          ← Back to findings
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-base font-semibold text-slate-800">Finding #{detail.id}</h2>
            <SeverityBadge sev={detail.severity} />
            <StatusPill status={detail.status} />
          </div>
        </div>
      </div>

      {/* ── 1. Issue ── */}
      <Section title="Issue">
        <p className="text-sm text-slate-700">{sanitise(detail.summary)}</p>
        <p className="text-xs text-slate-500 mt-1">Type: <code>{detail.finding_type}</code></p>
      </Section>

      {/* ── 2. Evidence ── */}
      <Section title="Evidence">
        {detail.evidence.length === 0 ? (
          <p className="text-slate-500 text-sm">No evidence records attached.</p>
        ) : (
          detail.evidence.map((ev, i) => (
            <div key={ev.id} className="mb-4 last:mb-0">
              <p className="text-xs font-semibold text-slate-500 mb-1">
                Record {i + 1}
                {ev.source_row != null && ` · row ${ev.source_row}`}
                {ev.source_record_id != null && ` · record ID ${ev.source_record_id}`}
              </p>
              <FieldTable fields={ev.field_values} />
              {ev.note && (
                <p className="text-xs text-amber-700 mt-1">Note: {sanitise(ev.note)}</p>
              )}
            </div>
          ))
        )}

        {/* Side-by-side if 2+ evidence records */}
        {detail.evidence.length >= 2 && (
          <SideBySide evidence={detail.evidence} />
        )}
      </Section>

      {/* ── 3. Rule ── */}
      <Section title="Rule">
        {rt ? (
          <div className="space-y-3">
            <div className="flex gap-4 text-sm flex-wrap">
              <span><span className="text-slate-500">ID:</span> <code className="font-mono">{rt.rule_id}</code></span>
              <span><span className="text-slate-500">Version:</span> <code className="font-mono">{rt.rule_version}</code></span>
              <span className="text-xs text-slate-400">Evaluated {new Date(rt.evaluated_at).toLocaleString()}</span>
            </div>
            {rt.matched_conditions.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 mb-1">Matched conditions</p>
                <ol className="space-y-1">
                  {rt.matched_conditions.map((cond, i) => (
                    <li key={i} className="flex gap-2 text-sm">
                      <span className="text-green-600 shrink-0">✓</span>
                      <span>{sanitise(cond)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {rt.missing_information && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                Missing: {sanitise(rt.missing_information)}
              </p>
            )}
            {rt.conflicting_information && (
              <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2">
                Conflict: {sanitise(rt.conflicting_information)}
              </p>
            )}
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No rule trace available.</p>
        )}
      </Section>

      {/* ── 4. Uncertainty ── */}
      <Section title="Uncertainty">
        <p className="text-sm text-slate-700">{sanitise(detail.uncertainty || '—')}</p>
      </Section>

      {/* ── 5. Next step ── */}
      <Section title="Next step">
        <p className="text-sm text-slate-700">{sanitise(detail.next_step || '—')}</p>
      </Section>

      {/* ── 6. Review history ── */}
      <Section title="Review history">
        {detail.review_decisions.length === 0 ? (
          <p className="text-slate-500 text-sm">No reviews yet.</p>
        ) : (
          <div className="space-y-3">
            {detail.review_decisions.map((rd) => (
              <div key={rd.id} className="border rounded p-3 text-sm space-y-1">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="font-medium capitalize">{rd.decision}</span>
                  <span className="text-slate-500 text-xs">by {rd.actor}</span>
                  <span className="text-slate-400 text-xs">{new Date(rd.decided_at).toLocaleString()}</span>
                </div>
                {rd.note && <p className="text-slate-700 text-xs">Note: {rd.note}</p>}
                {Object.keys(rd.corrected_values || {}).length > 0 && (
                  <div className="text-xs mt-1">
                    <p className="font-semibold text-slate-500 mb-1">Corrections applied:</p>
                    <FieldTable fields={rd.corrected_values} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ── Review actions ── */}
      {canReview && (
        <Section title="Review this finding">
          <p className="text-xs text-slate-500 mb-3">
            Findings are leads for human review, not ownership decisions. Record your
            assessment below.
          </p>

          {reviewMsg && (
            <p className="text-green-700 text-sm mb-3 font-medium">{reviewMsg}</p>
          )}
          {reviewError && (
            <p className="text-red-600 text-sm mb-3">{reviewError}</p>
          )}

          {reviewMode === null ? (
            <div className="flex gap-3 flex-wrap">
              <button
                onClick={() => setReviewMode('accept')}
                className="bg-green-600 text-white px-4 py-1.5 rounded text-sm hover:bg-green-700"
              >
                Accept
              </button>
              <button
                onClick={() => setReviewMode('reject')}
                className="bg-red-600 text-white px-4 py-1.5 rounded text-sm hover:bg-red-700"
              >
                Reject
              </button>
              <button
                onClick={() => setReviewMode('correct')}
                className="bg-amber-500 text-white px-4 py-1.5 rounded text-sm hover:bg-amber-600"
              >
                Correct record
              </button>
            </div>
          ) : (
            <div className="border rounded p-4 space-y-3 max-w-lg">
              <p className="text-sm font-medium capitalize">
                {reviewMode === 'accept' && '✓ Accept — mark as reviewed and resolved'}
                {reviewMode === 'reject' && '✗ Reject — dismiss this finding permanently'}
                {reviewMode === 'correct' && '✎ Correct — create corrected record version'}
              </p>

              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">
                  Note {reviewMode === 'correct' && <span className="text-red-500">*</span>}
                </label>
                {reviewMode === 'correct' && (
                  <p className="text-xs text-slate-500 mb-1">Explain what was incorrect and how it was fixed.</p>
                )}
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                  className="w-full border rounded px-3 py-2 text-sm"
                  placeholder={
                    reviewMode === 'correct'
                      ? 'Explain what was incorrect and how it was fixed…'
                      : 'Optional explanation…'
                  }
                />
              </div>

              {reviewMode === 'correct' && (
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-2">
                    Corrected field values
                    <span className="text-slate-400 ml-1">(applied to all supporting records)</span>
                  </p>
                  {Object.entries(correctedValues).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 mb-1">
                      <code className="text-xs bg-slate-100 rounded px-1 py-0.5">{k}</code>
                      <span className="text-xs text-slate-400">→</span>
                      <code className="text-xs bg-green-50 rounded px-1 py-0.5">{v}</code>
                      <button
                        onClick={() => setCorrectedValues(prev => {
                          const n = { ...prev };
                          delete n[k];
                          return n;
                        })}
                        className="text-red-400 hover:text-red-600 text-xs"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <div className="flex gap-2 mt-2">
                    <input
                      value={correctionKey}
                      onChange={(e) => setCorrectionKey(e.target.value)}
                      placeholder="field name"
                      className="border rounded px-2 py-1 text-xs w-32"
                    />
                    <input
                      value={correctionVal}
                      onChange={(e) => setCorrectionVal(e.target.value)}
                      placeholder="corrected value"
                      className="border rounded px-2 py-1 text-xs flex-1"
                    />
                    <button
                      onClick={() => {
                        if (!correctionKey.trim()) return;
                        setCorrectedValues(prev => ({ ...prev, [correctionKey.trim()]: correctionVal }));
                        setCorrectionKey('');
                        setCorrectionVal('');
                      }}
                      className="bg-slate-200 hover:bg-slate-300 rounded px-2 py-1 text-xs"
                    >
                      Add
                    </button>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={submitReview}
                  disabled={reviewing}
                  className="bg-indigo-600 text-white px-4 py-1.5 rounded text-sm hover:bg-indigo-700 disabled:opacity-50"
                >
                  {reviewing ? 'Saving…' : 'Confirm'}
                </button>
                <button
                  onClick={() => { setReviewMode(null); setNote(''); setCorrectedValues({}); setReviewError(''); }}
                  className="text-slate-500 text-sm hover:underline"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Footer */}
      <p className="text-xs text-slate-400 border-t pt-3 mt-4">
        ⚠ Findings are leads for human review, not ownership decisions.
      </p>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border rounded-lg p-4">
      <h3 className="font-semibold text-slate-700 mb-3 tracking-wide text-xs">{title.toUpperCase()}</h3>
      {children}
    </div>
  );
}

function FieldTable({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields);
  if (entries.length === 0) return <p className="text-xs text-slate-400">No fields.</p>;
  return (
    <table className="text-xs w-full">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-b last:border-0">
            <td className="py-0.5 pr-3 font-mono text-slate-500 whitespace-nowrap w-1/3">{k}</td>
            <td className="py-0.5 text-slate-800">{String(v ?? '—')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SideBySide({ evidence }: { evidence: import('../types').Evidence[] }) {
  // Collect all keys across both records
  const allKeys = [
    ...new Set(evidence.flatMap((ev) => Object.keys(ev.field_values))),
  ];
  const left = evidence[0];
  const right = evidence[1];

  return (
    <div className="mt-4">
      <p className="text-xs font-semibold text-slate-500 mb-2">Side-by-side comparison</p>
      <div className="overflow-x-auto">
        <table className="text-xs w-full">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-2 py-1 border-b text-slate-500 font-medium">Field</th>
              <th className="text-left px-2 py-1 border-b text-slate-500 font-medium">
                Record {left.source_record_id ?? 1}
              </th>
              <th className="text-left px-2 py-1 border-b text-slate-500 font-medium">
                Record {right.source_record_id ?? 2}
              </th>
              <th className="text-left px-2 py-1 border-b text-slate-500 font-medium">Match?</th>
            </tr>
          </thead>
          <tbody>
            {allKeys.map((k) => {
              const lv = String(left.field_values[k] ?? '—');
              const rv = String(right.field_values[k] ?? '—');
              const match = lv === rv;
              return (
                <tr key={k} className="border-b last:border-0">
                  <td className="px-2 py-1 font-mono text-slate-500">{k}</td>
                  <td className="px-2 py-1 text-slate-800">{lv}</td>
                  <td className={`px-2 py-1 ${!match ? 'text-red-700 font-medium' : 'text-slate-800'}`}>{rv}</td>
                  <td className="px-2 py-1">{match ? '✓' : <span className="text-red-500">✗</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
