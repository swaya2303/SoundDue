import { useState } from 'react';
import type { UploadedFile } from '../types';
import { uploadFile, getFilePreview } from '../api';
import type { PreviewData } from '../api';

const FILE_KINDS = ['recordings', 'works', 'ownership', 'mappings'] as const;
type FileKind = (typeof FILE_KINDS)[number];

interface StagedFile {
  file: File;
  kind: FileKind;
}

interface UploadedEntry {
  uf: UploadedFile;
  preview: PreviewData | null;
}

interface Props {
  caseId: number;
  uploadedFiles: UploadedFile[];
  onFilesUploaded: (files: UploadedFile[]) => void;
}

export default function UploadSection({ caseId, onFilesUploaded }: Props) {
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [defaultKind, setDefaultKind] = useState<FileKind>('recordings');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [entries, setEntries] = useState<UploadedEntry[]>([]);

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    setStaged(files.map((f) => ({ file: f, kind: defaultKind })));
    // reset input so same file can be re-selected
    e.target.value = '';
  }

  function setStagedKind(idx: number, kind: FileKind) {
    setStaged((prev) => prev.map((s, i) => (i === idx ? { ...s, kind } : s)));
  }

  function removeStagedFile(idx: number) {
    setStaged((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleUpload() {
    setUploading(true);
    setError('');
    const uploaded: UploadedFile[] = [];
    for (const s of staged) {
      try {
        const uf = await uploadFile(caseId, s.file, s.kind);
        uploaded.push(uf);
        const preview = await getFilePreview(uf.file_id).catch(() => null);
        setEntries((prev) => [...prev, { uf, preview }]);
      } catch (err) {
        setError(`Failed to upload "${s.file.name}": ${String(err)}`);
      }
    }
    if (uploaded.length > 0) {
      onFilesUploaded(uploaded);
      setStaged([]);
    }
    setUploading(false);
  }

  return (
    <div className="space-y-6">
      {/* Drop zone */}
      <div>
        <h3 className="font-semibold text-slate-700 mb-3">Upload files</h3>
        <div className="border-2 border-dashed border-slate-300 rounded-lg p-6 text-center space-y-3">
          <p className="text-slate-500 text-sm">Select one or more CSV or XLSX files</p>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <label className="text-sm text-slate-600">Default type:</label>
            <select
              value={defaultKind}
              onChange={(e) => setDefaultKind(e.target.value as FileKind)}
              className="border rounded px-2 py-1 text-sm"
            >
              {FILE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <label className="cursor-pointer bg-white border border-slate-300 rounded px-3 py-1.5 text-sm hover:bg-slate-50">
              Choose files…
              <input
                type="file"
                multiple
                accept=".csv,.xlsx,.xls"
                onChange={handleFilePick}
                className="hidden"
              />
            </label>
          </div>
        </div>

        {/* Staged file list */}
        {staged.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-sm font-medium text-slate-700">
              {staged.length} file{staged.length > 1 ? 's' : ''} ready to upload:
            </p>
            {staged.map((s, i) => (
              <div
                key={i}
                className="flex items-center gap-3 border rounded px-3 py-2 text-sm"
              >
                <span className="flex-1 truncate">{s.file.name}</span>
                <span className="text-slate-400 text-xs">
                  {(s.file.size / 1024).toFixed(1)} KB
                </span>
                <select
                  value={s.kind}
                  onChange={(e) => setStagedKind(i, e.target.value as FileKind)}
                  className="border rounded px-2 py-0.5 text-xs"
                >
                  {FILE_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => removeStagedFile(i)}
                  className="text-slate-400 hover:text-red-500 text-xs"
                  title="Remove"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              data-testid="upload-submit-btn"
              onClick={handleUpload}
              disabled={uploading}
              className="mt-2 bg-indigo-600 text-white px-4 py-1.5 rounded text-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              {uploading
                ? 'Uploading…'
                : `Upload ${staged.length} file${staged.length > 1 ? 's' : ''}`}
            </button>
          </div>
        )}

        {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
      </div>

      {/* Uploaded file previews */}
      {entries.map((entry) => (
        <FilePreviewCard key={entry.uf.file_id} entry={entry} />
      ))}
    </div>
  );
}

function FilePreviewCard({ entry }: { entry: UploadedEntry }) {
  const { uf, preview } = entry;
  const issueCount = uf.validation.issue_count;

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-medium text-sm">{uf.original_name}</span>
        <span className="text-xs bg-slate-100 text-slate-600 rounded px-2 py-0.5">
          {uf.file_kind}
        </span>
        <span className="text-xs text-slate-500">{uf.row_count} rows</span>
        {issueCount > 0 ? (
          <span className="text-xs bg-amber-100 text-amber-700 rounded px-2 py-0.5">
            ⚠ {issueCount} issue{issueCount > 1 ? 's' : ''} found
          </span>
        ) : (
          <span className="text-xs bg-green-100 text-green-700 rounded px-2 py-0.5">
            ✓ No issues
          </span>
        )}
      </div>

      {preview && preview.preview_rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="text-xs min-w-max">
            <thead className="bg-slate-50">
              <tr>
                {preview.detected_columns.map((col) => (
                  <th
                    key={col}
                    className="px-2 py-1 text-left text-slate-600 border-b whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.preview_rows.slice(0, 5).map((row, i) => (
                <tr key={i} className="border-b last:border-0">
                  {preview.detected_columns.map((col) => (
                    <td key={col} className="px-2 py-1 whitespace-nowrap text-slate-700">
                      {row[col] ?? ''}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {preview.row_count > 5 && (
            <p className="text-xs text-slate-400 mt-1">
              Showing 5 of {preview.row_count} rows
            </p>
          )}
        </div>
      )}

      {/* Missing column warnings */}
      {uf.validation.issues.some((i) => i.code === 'missing_column') && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
          Some expected columns were not found in this file. Go to{' '}
          <strong>Map columns</strong> to confirm the mapping.
        </div>
      )}
    </div>
  );
}
