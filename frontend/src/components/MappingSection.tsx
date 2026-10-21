import { useState, useEffect } from 'react';
import { getMappingSuggestions, confirmMapping } from '../api';
import type { MappingState, UploadedFile } from '../types';
import { Card, CardHeader, CardBody } from './ui/Card';
import { Button } from './ui/Button';
import { Callout } from './ui/Callout';
import { EmptyState } from './ui/EmptyState';
import { CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { useToast } from './ui/Toast';

// All known canonical field names across reconciliation schemas
const ALL_CANONICAL = [
  '',
  'recording_id',
  'title',
  'performer',
  'version',
  'duration_seconds',
  'isrc',
  'work_id',
  'writers',
  'publisher',
  'rights_category',
  'territory',
  'period_start',
  'period_end',
  'share_percentage',
  'contributor_name',
  'recording_work_id',
  'source_label',
  'status',
];

interface Props {
  uploadedFiles: UploadedFile[];
  fileConfirmed: Record<number, boolean>;
  onFileConfirmed: (fileId: number, confirmed: boolean) => void;
}

export default function MappingSection({
  uploadedFiles,
  fileConfirmed,
  onFileConfirmed,
}: Props) {
  if (uploadedFiles.length === 0) {
    return (
      <EmptyState
        title="No files ready for column mapping"
        description="Upload recordings, works, or ownership schedules in the Upload step first."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-slate-800">Review & Confirm Column Mappings</h3>
        <p className="text-xs text-slate-500 mt-0.5">
          Verify how source columns align with SoundDue canonical fields. Exact matches are auto-confirmed.
        </p>
      </div>

      <div className="space-y-6">
        {uploadedFiles.map((uf) => (
          <FileMappingPanel
            key={uf.file_id}
            uf={uf}
            confirmed={fileConfirmed[uf.file_id] ?? false}
            onConfirmed={(c) => onFileConfirmed(uf.file_id, c)}
          />
        ))}
      </div>
    </div>
  );
}

interface PanelProps {
  uf: UploadedFile;
  confirmed: boolean;
  onConfirmed: (c: boolean) => void;
}

function FileMappingPanel({ uf, confirmed, onConfirmed }: PanelProps) {
  const [state, setState] = useState<MappingState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const { toast } = useToast();

  useEffect(() => {
    getMappingSuggestions(uf.file_id)
      .then((ms) => {
        setState(ms);
        const confirmedMap: Record<string, string> = {};
        for (const cm of ms.confirmed_mappings) {
          confirmedMap[cm.source_column] = cm.canonical_field;
        }
        const init: Record<string, string> = {};
        for (const sg of ms.suggestions) {
          init[sg.source_column] =
            confirmedMap[sg.source_column] ?? sg.best_canonical ?? '';
        }
        setSelections(init);
        onConfirmed(ms.all_confirmed);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [uf.file_id]);

  async function handleConfirm() {
    setSaving(true);
    setSaveMsg('');
    const mappings = Object.entries(selections)
      .filter(([, v]) => v !== '')
      .map(([source_column, canonical_field]) => ({ source_column, canonical_field }));

    try {
      const result = await confirmMapping(uf.file_id, mappings);
      onConfirmed(result.all_confirmed);
      const msg = result.all_confirmed
        ? '✓ All required fields mapped and confirmed'
        : '⚠ Mappings saved (some optional fields unmapped)';
      setSaveMsg(msg);
      toast({
        type: 'success',
        title: 'Mappings saved',
        message: `${uf.original_name}: mappings persisted to catalog schema.`,
      });
    } catch (err) {
      setError(String(err));
      toast({
        type: 'error',
        title: 'Failed to confirm mappings',
        message: String(err),
      });
    } finally {
      setSaving(false);
    }
  }

  if (loading)
    return (
      <Card className="bg-white p-6 text-center text-xs text-slate-500">
        Loading schema suggestions for {uf.original_name}…
      </Card>
    );

  if (error)
    return (
      <Callout type="error" title={`Mapping error: ${uf.original_name}`}>
        {error}
      </Callout>
    );

  if (!state) return null;

  // Check required missing fields
  const requiredMissing = state.required_fields.filter(
    (rf) => !Object.values(selections).includes(rf)
  );

  return (
    <Card className="bg-white">
      <CardHeader
        title={
          <div className="flex items-center gap-2.5">
            <span className="font-semibold text-slate-900 text-sm">{uf.original_name}</span>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
              {uf.file_kind}
            </span>
          </div>
        }
        action={
          confirmed ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>✓ Mappings confirmed</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-800 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>Needs confirmation</span>
            </span>
          )
        }
      />

      <CardBody className="p-0">
        {/* Missing required fields warning banner */}
        {requiredMissing.length > 0 && (
          <div className="p-3 bg-amber-50 border-b border-amber-200 text-xs text-amber-900 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              Required fields missing from the supplied records:{' '}
              <strong className="font-semibold underline decoration-amber-400">
                {requiredMissing.join(', ')}
              </strong>
            </span>
          </div>
        )}

        {/* Mapping table */}
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-semibold text-slate-600">Source Column</th>
                <th className="text-left px-4 py-2.5 font-semibold text-slate-600">Maps to Canonical Field</th>
                <th className="text-left px-4 py-2.5 font-semibold text-slate-600">Method</th>
                <th className="text-left px-4 py-2.5 font-semibold text-slate-600">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {state.suggestions.map((sg) => {
                const pct = Math.round(sg.score * 100);
                const isAmbiguous = sg.confidence === 'low' || (sg.alternatives && sg.alternatives.length > 1);

                return (
                  <tr key={sg.source_column} className="hover:bg-slate-50/80 transition-colors">
                    {/* Source column */}
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">
                        {sg.source_column}
                      </code>
                    </td>

                    {/* Maps to dropdown */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <select
                          value={selections[sg.source_column] ?? ''}
                          onChange={(e) =>
                            setSelections((prev) => ({
                              ...prev,
                              [sg.source_column]: e.target.value,
                            }))
                          }
                          className="border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs bg-white text-slate-800 focus-ring font-medium min-w-[180px]"
                        >
                          {ALL_CANONICAL.map((c) => (
                            <option key={c} value={c}>
                              {c === '' ? '(skip / ignore)' : c}
                            </option>
                          ))}
                        </select>
                        {isAmbiguous && (
                          <span
                            title="Multiple possible fields match or confidence is low"
                            className="text-amber-500 hover:text-amber-700 cursor-help"
                          >
                            <AlertTriangle className="w-3.5 h-3.5" />
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Method / Source */}
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 font-mono text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200 capitalize">
                        <Sparkles className="w-2.5 h-2.5 text-brand-500" />
                        <span>{sg.method || 'rule'}</span>
                      </span>
                    </td>

                    {/* Confidence bar */}
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              pct >= 90 ? 'bg-emerald-500' : pct >= 60 ? 'bg-amber-500' : 'bg-rose-400'
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="font-mono text-[11px] text-slate-600">{pct}%</span>
                        <span
                          className={`text-[10px] uppercase font-semibold px-1.5 py-0.2 rounded ${
                            sg.confidence === 'high'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : sg.confidence === 'medium'
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}
                        >
                          {sg.confidence}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardBody>

      {/* Footer & Confirm Button */}
      <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between gap-4 flex-wrap">
        <div>
          {saveMsg && (
            <span className="text-xs font-semibold text-emerald-700 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{saveMsg}</span>
            </span>
          )}
        </div>

        <Button
          onClick={handleConfirm}
          disabled={saving}
          loading={saving}
          variant={confirmed ? 'outline' : 'primary'}
          size="sm"
          icon={<CheckCircle2 className="w-3.5 h-3.5" />}
        >
          {saving ? 'Saving…' : 'Confirm mappings'}
        </Button>
      </div>
    </Card>
  );
}
