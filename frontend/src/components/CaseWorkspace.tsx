import { useState } from 'react';
import type { Case, UploadedFile } from '../types';
import { analyzeCase, getMappingSuggestions } from '../api';
import UploadSection from './UploadSection';
import MappingSection from './MappingSection';
import ValidationSection from './ValidationSection';
import FindingsSection from './FindingsSection';
import CandidatesSection from './CandidatesSection';

type WsTab = 'upload' | 'mappings' | 'validation' | 'findings' | 'candidates';

interface Props {
  case_: Case;
}

const TAB_LABELS: { id: WsTab; label: string }[] = [
  { id: 'upload', label: '1. Upload files' },
  { id: 'mappings', label: '2. Map columns' },
  { id: 'validation', label: '3. Validation issues' },
  { id: 'findings', label: '4. Findings' },
  { id: 'candidates', label: '5. Match candidates' },
];

export default function CaseWorkspace({ case_ }: Props) {
  const [tab, setTab] = useState<WsTab>('upload');
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  // fileConfirmed[fileId] = true when mapping confirmed for that file
  const [fileConfirmed, setFileConfirmed] = useState<Record<number, boolean>>({});
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<{
    finding_count: number;
    findings_by_type: Record<string, number>;
  } | null>(null);
  const [analyzeError, setAnalyzeError] = useState('');

  // Analyze is enabled as soon as at least one file is uploaded.
  // (Mapping confirmation is advisory — the backend validates what it needs.)
  const mappingReady = uploadedFiles.length > 0;

  function handleFilesUploaded(files: UploadedFile[]) {
    setUploadedFiles((prev) => {
      const existingIds = new Set(prev.map((f) => f.file_id));
      return [...prev, ...files.filter((f) => !existingIds.has(f.file_id))];
    });
    // After upload, proactively fetch mapping status so the Analyze gate
    // doesn't require the user to visit the Mappings tab first.
    for (const uf of files) {
      getMappingSuggestions(uf.file_id)
        .then((ms) => setFileConfirmed((prev) => ({ ...prev, [uf.file_id]: ms.all_confirmed })))
        .catch(() => { /* non-fatal */ });
    }
  }

  function handleFileConfirmed(fileId: number, confirmed: boolean) {
    setFileConfirmed((prev) => ({ ...prev, [fileId]: confirmed }));
  }

  async function handleAnalyze() {
    setAnalyzing(true);
    setAnalyzeError('');
    setAnalyzeResult(null);
    try {
      const result = await analyzeCase(case_.id);
      setAnalyzeResult(result);
      setTab('findings');
    } catch (err) {
      setAnalyzeError(String(err));
    } finally {
      setAnalyzing(false);
    }
  }

  const analyzeTooltip = !mappingReady
    ? 'Upload at least one file first'
    : analyzing
    ? 'Analysis running…'
    : 'Run analysis';

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl shadow">
        {/* Tab bar + Analyze button */}
        <div className="flex items-center justify-between border-b px-4">
          <div className="flex">
            {TAB_LABELS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  tab === t.id
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 py-2">
            {analyzeError && (
              <span className="text-red-600 text-xs max-w-xs truncate">{analyzeError}</span>
            )}
            {analyzeResult && (
              <span className="text-green-700 text-xs">
                ✓ {analyzeResult.finding_count} findings
              </span>
            )}
            {/* Wrapper div carries the tooltip even when button is disabled */}
            <div title={analyzeTooltip}>
              <button
                onClick={handleAnalyze}
                disabled={!mappingReady || analyzing}
                className="bg-indigo-600 text-white px-4 py-1.5 rounded text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700"
              >
                {analyzing ? 'Analyzing…' : 'Analyze'}
              </button>
            </div>
          </div>
        </div>

        {/* Tab content */}
        <div className="p-6 min-h-[420px]">
          {tab === 'upload' && (
            <UploadSection
              caseId={case_.id}
              uploadedFiles={uploadedFiles}
              onFilesUploaded={handleFilesUploaded}
            />
          )}
          {tab === 'mappings' && (
            <MappingSection
              uploadedFiles={uploadedFiles}
              fileConfirmed={fileConfirmed}
              onFileConfirmed={handleFileConfirmed}
            />
          )}
          {tab === 'validation' && (
            <ValidationSection uploadedFiles={uploadedFiles} />
          )}
          {tab === 'findings' && (
            <FindingsSection caseId={case_.id} />
          )}
          {tab === 'candidates' && (
            <CandidatesSection caseId={case_.id} />
          )}
        </div>
      </div>
    </div>
  );
}
