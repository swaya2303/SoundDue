import { useState, useEffect } from 'react';
import { getMappingSuggestions, confirmMapping } from '../api';
import type { MappingState, UploadedFile } from '../types';

// All known canonical field names (union of all file kinds)
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
      <p className="text-slate-500">
        No files uploaded yet. Go to "Upload files" first.
      </p>
    );
  }
  return (
    <div className="space-y-8">
      {uploadedFiles.map((uf) => (
        <FileMappingPanel
          key={uf.file_id}
          uf={uf}
          confirmed={fileConfirmed[uf.file_id] ?? false}
          onConfirmed={(c) => onFileConfirmed(uf.file_id, c)}
        />
      ))}
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
  // source_column → chosen canonical
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  useEffect(() => {
    getMappingSuggestions(uf.file_id)
      .then((ms) => {
        setState(ms);
        // Seed selections: confirmed mapping > suggestion > ''
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      setSaveMsg(
        result.all_confirmed
          ? '✓ All required fields mapped'
          : '⚠ Some required fields still need mapping',
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading)
    return <p className="text-slate-500 text-sm">Loading mappings for {uf.original_name}…</p>;
  if (error) return <p className="text-red-600 text-sm">{error}</p>;
  if (!state) return null;

  // Which required fields don't yet have a selection?
  const requiredMissing = state.required_fields.filter(
    (rf) => !Object.values(selections).includes(rf),
  );

  return (
    <div className="border rounded-lg p-4">
      {/* File header */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <h4 className="font-semibold text-sm">{uf.original_name}</h4>
        <span className="text-xs bg-slate-100 text-slate-600 rounded px-2 py-0.5">
          {uf.file_kind}
        </span>
        {confirmed ? (
          <span className="text-xs bg-green-100 text-green-700 rounded px-2 py-0.5">
            ✓ Mappings confirmed
          </span>
        ) : (
          <span className="text-xs bg-amber-100 text-amber-700 rounded px-2 py-0.5">
            Needs confirmation
          </span>
        )}
      </div>

      {/* Missing required fields */}
      {requiredMissing.length > 0 && (
        <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
          Required fields missing from the supplied records:{' '}
          <strong>{requiredMissing.join(', ')}</strong>
        </div>
      )}

      {/* Mapping table */}
      <div className="overflow-x-auto mb-4">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-3 py-2 border-b text-slate-600 font-medium">
                Source column
              </th>
              <th className="text-left px-3 py-2 border-b text-slate-600 font-medium">
                Maps to
              </th>
              <th className="text-left px-3 py-2 border-b text-slate-600 font-medium">
                Suggestion
              </th>
              <th className="text-left px-3 py-2 border-b text-slate-600 font-medium">
                Confidence
              </th>
            </tr>
          </thead>
          <tbody>
            {state.suggestions.map((sg) => {
              const pct = Math.round(sg.score * 100);
              const confColor =
                sg.confidence === 'high'
                  ? 'bg-green-100 text-green-700'
                  : sg.confidence === 'medium'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-red-100 text-red-700';

              return (
                <tr key={sg.source_column} className="border-b last:border-0">
                  <td className="px-3 py-2 font-mono text-xs text-slate-700">
                    {sg.source_column}
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={selections[sg.source_column] ?? ''}
                      onChange={(e) =>
                        setSelections((prev) => ({
                          ...prev,
                          [sg.source_column]: e.target.value,
                        }))
                      }
                      className="border rounded px-2 py-0.5 text-xs w-full min-w-[160px]"
                    >
                      {ALL_CANONICAL.map((c) => (
                        <option key={c} value={c}>
                          {c === '' ? '(skip / ignore)' : c}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {sg.best_canonical ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs rounded px-2 py-0.5 ${confColor}`}>
                      {pct}% · {sg.confidence}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Confirm button */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleConfirm}
          disabled={saving}
          className="bg-indigo-600 text-white px-4 py-1.5 rounded text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Confirm mappings'}
        </button>
        {saveMsg && <span className="text-sm">{saveMsg}</span>}
      </div>
    </div>
  );
}
