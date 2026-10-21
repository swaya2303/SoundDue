import React, { useState } from 'react';
import type { UploadedFile } from '../types';
import { uploadFile, getFilePreview } from '../api';
import type { PreviewData } from '../api';
import { Button } from './ui/Button';
import { Card, CardHeader, CardBody } from './ui/Card';
import { Callout } from './ui/Callout';
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  X,
  FileText,
  Layers,
  Database,
} from 'lucide-react';
import { useToast } from './ui/Toast';

const FILE_KINDS = ['recordings', 'works', 'ownership', 'mappings'] as const;
type FileKind = (typeof FILE_KINDS)[number];

const KIND_DETAILS: Record<FileKind, { label: string; icon: React.ReactNode; desc: string }> = {
  recordings: {
    label: 'Recordings (ISRC)',
    icon: <Database className="w-3.5 h-3.5" />,
    desc: 'Audio tracks, ISRCs, artists, and durations',
  },
  works: {
    label: 'Musical Works (ISWC)',
    icon: <Layers className="w-3.5 h-3.5" />,
    desc: 'Compositions, ISWCs, songwriters, publishers',
  },
  ownership: {
    label: 'Ownership Shares',
    icon: <FileSpreadsheet className="w-3.5 h-3.5" />,
    desc: 'Share schedules, territories, rights categories',
  },
  mappings: {
    label: 'Mappings (Link table)',
    icon: <FileText className="w-3.5 h-3.5" />,
    desc: 'Cross-reference links between recordings & works',
  },
};

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
  const [isDragging, setIsDragging] = useState(false);

  const { toast } = useToast();

  function addFiles(files: File[]) {
    if (files.length === 0) return;
    setStaged((prev) => [...prev, ...files.map((f) => ({ file: f, kind: defaultKind }))]);
  }

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    addFiles(files);
    e.target.value = '';
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (f) => f.name.endsWith('.csv') || f.name.endsWith('.xlsx') || f.name.endsWith('.xls')
    );
    addFiles(files);
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
      toast({
        type: 'success',
        title: 'Upload complete',
        message: `Successfully uploaded ${uploaded.length} file(s).`,
      });
    }
    setUploading(false);
  }

  return (
    <div className="space-y-6">
      {/* File Type Selection Chips & Drop Zone */}
      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Select File Kind & Ingest Records</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Select the record type before selecting files. You can adjust the type individually for each file below.
          </p>
        </div>

        {/* File kind selector chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-slate-500 mr-1">Expected format:</span>
          {FILE_KINDS.map((kind) => {
            const isSelected = defaultKind === kind;
            const details = KIND_DETAILS[kind];
            return (
              <button
                key={kind}
                type="button"
                onClick={() => setDefaultKind(kind)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all focus-ring ${
                  isSelected
                    ? 'bg-brand-600 text-white shadow-subtle'
                    : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
                }`}
              >
                {details.icon}
                <span>{details.label}</span>
              </button>
            );
          })}
        </div>

        {/* Drop Zone Card */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${
            isDragging
              ? 'border-brand-500 bg-brand-50/50 scale-[0.99]'
              : 'border-slate-300 bg-white hover:border-slate-400'
          }`}
        >
          <div className="flex flex-col items-center justify-center gap-2">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-brand-600 mb-1">
              <UploadCloud className="w-6 h-6 stroke-[1.8]" />
            </div>
            <p className="text-sm font-semibold text-slate-800">
              Drag & drop spreadsheet files here, or browse
            </p>
            <p className="text-xs text-slate-500 max-w-sm">
              Supports CSV, XLSX, and XLS formats from publishers, CMO schedules, or internal ERP exports.
            </p>

            <div className="mt-3 flex items-center justify-center gap-3">
              {/* Native hidden file input + label for click */}
              <label className="cursor-pointer bg-white border border-slate-300 rounded-lg px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-ring shadow-subtle inline-flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-brand-600" />
                <span>Choose files…</span>
                <input
                  type="file"
                  multiple
                  accept=".csv,.xlsx,.xls"
                  onChange={handleFilePick}
                  className="hidden"
                />
              </label>

              {/* Native select element for Playwright compatibility (test selects option) */}
              <select
                value={defaultKind}
                onChange={(e) => setDefaultKind(e.target.value as FileKind)}
                className="border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 bg-white focus-ring"
                aria-label="File kind selector"
              >
                {FILE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Staged file list ready for upload */}
      {staged.length > 0 && (
        <Card className="bg-white border-brand-200">
          <CardHeader
            title={`${staged.length} file${staged.length > 1 ? 's' : ''} staged for upload`}
            subtitle="Verify assigned file kind for canonical normalization"
          />
          <CardBody className="p-0">
            <div className="divide-y divide-slate-100">
              {staged.map((s, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-3 text-xs">
                  <FileSpreadsheet className="w-4 h-4 text-brand-600 shrink-0" />
                  <span className="flex-1 font-medium text-slate-800 truncate">{s.file.name}</span>
                  <span className="text-slate-400 font-mono text-[11px]">
                    {(s.file.size / 1024).toFixed(1)} KB
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-500 text-[11px]">Type:</span>
                    <select
                      value={s.kind}
                      onChange={(e) => setStagedKind(i, e.target.value as FileKind)}
                      className="border border-slate-300 rounded px-2 py-1 text-xs bg-white focus-ring font-medium text-slate-700"
                    >
                      {FILE_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={() => removeStagedFile(i)}
                    className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 focus-ring"
                    title="Remove"
                    aria-label="Remove"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </CardBody>
          <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              Files will be stored immutably and parsed for column mapping.
            </span>
            <Button
              data-testid="upload-submit-btn"
              onClick={handleUpload}
              disabled={uploading}
              loading={uploading}
              variant="primary"
              size="sm"
            >
              {uploading ? 'Uploading…' : `Upload ${staged.length} file${staged.length > 1 ? 's' : ''}`}
            </Button>
          </div>
        </Card>
      )}

      {error && (
        <Callout type="error" title="Upload Failed">
          {error}
        </Callout>
      )}

      {/* Uploaded file previews */}
      {entries.length > 0 && (
        <div className="space-y-4 pt-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Uploaded Datasets ({entries.length})
            </h4>
            <span className="text-xs text-slate-400">First 5 rows displayed per table</span>
          </div>

          <div className="space-y-4">
            {entries.map((entry) => (
              <FilePreviewCard key={entry.uf.file_id} entry={entry} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FilePreviewCard({ entry }: { entry: UploadedEntry }) {
  const { uf, preview } = entry;
  const issueCount = uf.validation?.issue_count || 0;

  return (
    <Card className="bg-white">
      <CardHeader
        title={
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-brand-600" />
            <span className="font-semibold text-slate-900 text-sm">{uf.original_name}</span>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
              {uf.file_kind}
            </span>
            <span className="text-xs text-slate-500 font-mono">({uf.row_count} rows)</span>
          </div>
        }
        action={
          issueCount > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-800 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>{issueCount} issue{issueCount > 1 ? 's' : ''} detected</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>Validation clean</span>
            </span>
          )
        }
      />

      <CardBody className="p-0">
        {preview && preview.preview_rows.length > 0 ? (
          <div className="overflow-x-auto max-h-56">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 sticky top-0 border-b border-slate-200 z-10">
                <tr>
                  {preview.detected_columns.map((col) => (
                    <th
                      key={col}
                      className="px-3 py-2 text-left font-mono font-semibold text-slate-600 whitespace-nowrap bg-slate-50"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {preview.preview_rows.slice(0, 5).map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50/80">
                    {preview.detected_columns.map((col) => (
                      <td
                        key={col}
                        className="px-3 py-1.5 whitespace-nowrap font-mono text-[11px] text-slate-700"
                      >
                        {row[col] ?? '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-4 text-xs text-slate-400 text-center">No preview rows available.</div>
        )}

        {/* Missing column warnings */}
        {uf.validation?.issues?.some((i) => i.code === 'missing_column') && (
          <div className="p-3 bg-amber-50 border-t border-amber-200 text-xs text-amber-900 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>
                Expected canonical columns are missing from the raw header names. Review mappings in the next step.
              </span>
            </div>
            <span className="text-[11px] font-semibold text-amber-800 uppercase tracking-wide">
              Needs Confirmation
            </span>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
