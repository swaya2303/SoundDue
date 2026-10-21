import { useState, useEffect } from 'react';
import type { Case, UploadedFile } from '../types';
import { analyzeCase, getMappingSuggestions, getCaseFindings } from '../api';
import UploadSection from './UploadSection';
import MappingSection from './MappingSection';
import ValidationSection from './ValidationSection';
import FindingsSection from './FindingsSection';
import CandidatesSection from './CandidatesSection';
import ExportSection from './ExportSection';
import { Stepper, StepItem } from './ui/Stepper';
import { Button } from './ui/Button';
import { Play, AlertCircle, FileCheck2, ArrowLeft } from 'lucide-react';
import { useToast } from './ui/Toast';

export type WsTab = 'upload' | 'mappings' | 'validation' | 'findings' | 'candidates' | 'export';

interface Props {
  case_: Case;
  onCloseCase?: () => void;
}

export default function CaseWorkspace({ case_, onCloseCase }: Props) {
  const [tab, setTab] = useState<WsTab>('upload');
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [fileConfirmed, setFileConfirmed] = useState<Record<number, boolean>>({});
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<{
    finding_count: number;
    findings_by_type: Record<string, number>;
  } | null>(null);
  const [analyzeError, setAnalyzeError] = useState('');
  const [findingCount, setFindingCount] = useState<number | null>(null);

  const { toast } = useToast();

  const hasFiles = uploadedFiles.length > 0 || (case_.file_count ?? 0) > 0;
  const allMappingsConfirmed = hasFiles && (uploadedFiles.length === 0 || uploadedFiles.every((f) => fileConfirmed[f.file_id]));
  const mappingReady = hasFiles; // gate: uploaded files present

  // Fetch initial findings if case was already analyzed
  useEffect(() => {
    getCaseFindings(case_.id)
      .then((f) => {
        setFindingCount(f.length);
        if (f.length > 0 && tab === 'upload' && uploadedFiles.length === 0) {
          // If returning to an already populated case, we can default to findings
          setTab('findings');
        }
      })
      .catch(() => {});
  }, [case_.id]);

  function handleFilesUploaded(files: UploadedFile[]) {
    setUploadedFiles((prev) => {
      const existingIds = new Set(prev.map((f) => f.file_id));
      return [...prev, ...files.filter((f) => !existingIds.has(f.file_id))];
    });

    for (const uf of files) {
      getMappingSuggestions(uf.file_id)
        .then((ms) => setFileConfirmed((prev) => ({ ...prev, [uf.file_id]: ms.all_confirmed })))
        .catch(() => {});
    }

    toast({
      type: 'success',
      title: `${files.length} file(s) staged`,
      message: 'Automatic column mappings applied. Review and confirm columns.',
    });
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
      setFindingCount(result.finding_count);
      setTab('findings');
      toast({
        type: 'success',
        title: 'Analysis complete',
        message: `Identified ${result.finding_count} finding(s) across symbolic rule set.`,
      });
    } catch (err) {
      setAnalyzeError(String(err));
      toast({
        type: 'error',
        title: 'Analysis failed',
        message: String(err),
      });
    } finally {
      setAnalyzing(false);
    }
  }

  // Calculate stepper states
  const steps: StepItem[] = [
    {
      id: 'upload',
      label: '1. Upload files',
      status: hasFiles ? 'done' : 'current',
      badge: hasFiles ? uploadedFiles.length : undefined,
    },
    {
      id: 'mappings',
      label: '2. Map columns',
      status: allMappingsConfirmed
        ? 'done'
        : hasFiles
        ? 'current'
        : 'blocked',
      blockedReason: 'Upload records before mapping columns.',
    },
    {
      id: 'validation',
      label: '3. Validation issues',
      status: hasFiles ? 'done' : 'blocked',
      blockedReason: 'Upload files to check schema validation.',
    },
    {
      id: 'findings',
      label: '4. Findings',
      status: (findingCount !== null && findingCount > 0)
        ? (tab === 'findings' ? 'current' : 'done')
        : hasFiles
        ? 'upcoming'
        : 'blocked',
      blockedReason: 'Run analysis to generate findings.',
      badge: findingCount !== null && findingCount > 0 ? findingCount : undefined,
    },
    {
      id: 'candidates',
      label: '5. Match candidates',
      status: hasFiles ? (tab === 'candidates' ? 'current' : 'done') : 'blocked',
      blockedReason: 'Run analysis to generate fuzzy match candidates.',
    },
    {
      id: 'export',
      label: '6. Export',
      status: tab === 'export' ? 'current' : 'upcoming',
    },
  ];

  const analyzeTooltip = !mappingReady
    ? 'Upload at least one file first'
    : analyzing
    ? 'Analysis running…'
    : 'Run symbolic rule engine across all records';

  return (
    <div className="space-y-4">
      {/* Top Workbench Card */}
      <div className="bg-white rounded-xl shadow-card border border-slate-200/90 overflow-hidden">
        {/* Case Info Header Bar */}
        <div className="px-5 py-3.5 border-b border-slate-200/80 bg-slate-50/50 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            {onCloseCase && (
              <button
                onClick={onCloseCase}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-md hover:bg-slate-200/60 transition-colors focus-ring"
                title="Back to Cases"
                aria-label="Back to Cases"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-900">{case_.name}</h2>
                <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-200/80 text-slate-700 font-medium">
                  ID #{case_.id}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium capitalize">
                  {case_.status}
                </span>
              </div>
              {case_.description && (
                <p className="text-xs text-slate-500 mt-0.5">{case_.description}</p>
              )}
            </div>
          </div>

          {/* Action Trigger Area */}
          <div className="flex items-center gap-3">
            {analyzeError && (
              <span className="text-xs text-rose-600 bg-rose-50 px-2.5 py-1 rounded border border-rose-200 flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5" />
                <span className="truncate max-w-[200px]">{analyzeError}</span>
              </span>
            )}

            {analyzeResult && (
              <span className="text-xs font-medium text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200 flex items-center gap-1.5">
                <FileCheck2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>{analyzeResult.finding_count} findings identified</span>
              </span>
            )}

            <div title={analyzeTooltip}>
              <Button
                variant="primary"
                size="sm"
                onClick={handleAnalyze}
                disabled={!mappingReady || analyzing}
                loading={analyzing}
                icon={<Play className="w-3.5 h-3.5 fill-current" />}
              >
                {analyzing ? 'Analyzing…' : 'Analyze'}
              </Button>
            </div>
          </div>
        </div>

        {/* Stepper Navigation Bar */}
        <div className="px-5 py-2 border-b border-slate-200/80 bg-white">
          <Stepper
            steps={steps}
            currentStepId={tab}
            onStepClick={(id) => setTab(id as WsTab)}
          />
        </div>

        {/* Main Tab Viewport */}
        <div className="p-6 min-h-[460px] bg-slate-50/20">
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

          {tab === 'export' && (
            <ExportSection caseId={case_.id} caseName={case_.name} />
          )}
        </div>
      </div>
    </div>
  );
}
