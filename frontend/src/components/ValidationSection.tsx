import { useMemo, useState } from 'react';
import type { UploadedFile, ValidationIssue } from '../types';
import { Card, CardHeader, CardBody } from './ui/Card';
import { EmptyState } from './ui/EmptyState';
import { CheckCircle2, AlertTriangle, AlertCircle, FileSpreadsheet, Filter } from 'lucide-react';

interface FlatIssue extends ValidationIssue {
  file_name: string;
  file_kind: string;
  severity: 'error' | 'warning';
}

function sanitise(msg: string): string {
  return (msg || '').replace(/\bunclaimed\b/gi, 'missing from the supplied records');
}

interface Props {
  uploadedFiles: UploadedFile[];
}

export default function ValidationSection({ uploadedFiles }: Props) {
  const [filterErrorsOnly, setFilterErrorsOnly] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string>('all');

  const issues = useMemo<FlatIssue[]>(() => {
    return uploadedFiles.flatMap((uf) =>
      (uf.validation?.issues || []).map((issue) => {
        const isErr =
          issue.code === 'missing_required_column' ||
          issue.code === 'invalid_type' ||
          issue.code === 'negative_share' ||
          issue.code === 'share_exceeds_100';

        return {
          ...issue,
          file_name: uf.original_name,
          file_kind: uf.file_kind,
          severity: isErr ? 'error' : 'warning',
        };
      })
    );
  }, [uploadedFiles]);

  const errorCount = useMemo(() => issues.filter((i) => i.severity === 'error').length, [issues]);
  const warningCount = useMemo(() => issues.filter((i) => i.severity === 'warning').length, [issues]);

  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      if (filterErrorsOnly && issue.severity !== 'error') return false;
      if (selectedFile !== 'all' && issue.file_name !== selectedFile) return false;
      return true;
    });
  }, [issues, filterErrorsOnly, selectedFile]);

  // Group filtered issues by file
  const groupedByFile = useMemo(() => {
    const map = new Map<string, FlatIssue[]>();
    for (const issue of filteredIssues) {
      const list = map.get(issue.file_name) || [];
      list.push(issue);
      map.set(issue.file_name, list);
    }
    return map;
  }, [filteredIssues]);

  if (uploadedFiles.length === 0) {
    return (
      <EmptyState
        title="No files ingested yet"
        description="Upload recordings, works, and ownership files to run schema validation."
      />
    );
  }

  const filesLabel = `${uploadedFiles.length} file${uploadedFiles.length > 1 ? 's' : ''}`;

  return (
    <div className="space-y-6">
      {/* Header Summary Banner */}
      <div
        className={`p-4 rounded-xl border flex items-center justify-between gap-4 flex-wrap ${
          issues.length > 0
            ? 'bg-amber-50/70 border-amber-200 text-amber-900'
            : 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
        }`}
      >
        <div className="flex items-center gap-3">
          {issues.length > 0 ? (
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
          ) : (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          )}
          <div>
            <h4 className="text-sm font-semibold">
              {issues.length > 0
                ? `${issues.length} validation issue${issues.length > 1 ? 's' : ''} detected across ${filesLabel}`
                : `All ${filesLabel} passed schema validation cleanly`}
            </h4>
            <p className="text-xs opacity-90 mt-0.5">
              {issues.length > 0
                ? `${errorCount} blocking errors · ${warningCount} advisory warnings`
                : 'No unparseable rows, missing headers, or corrupt data types detected.'}
            </p>
          </div>
        </div>

        {/* Filters */}
        {issues.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilterErrorsOnly(!filterErrorsOnly)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors focus-ring ${
                filterErrorsOnly
                  ? 'bg-rose-600 text-white border-rose-600 shadow-subtle'
                  : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
              }`}
            >
              <Filter className="w-3 h-3" />
              <span>Errors only ({errorCount})</span>
            </button>

            {uploadedFiles.length > 1 && (
              <select
                value={selectedFile}
                onChange={(e) => setSelectedFile(e.target.value)}
                className="border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs bg-white text-slate-700 focus-ring font-medium"
              >
                <option value="all">All files ({issues.length})</option>
                {uploadedFiles.map((uf) => (
                  <option key={uf.file_id} value={uf.original_name}>
                    {uf.original_name}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}
      </div>

      {/* Issues grouped by file */}
      {issues.length === 0 ? (
        <EmptyState
          icon={<CheckCircle2 className="w-8 h-8 text-emerald-600" />}
          title="No validation issues found"
          description="Every row and column in the uploaded spreadsheets matches the canonical SoundDue format."
        />
      ) : filteredIssues.length === 0 ? (
        <EmptyState
          title="No issues match current filter"
          description="Try disabling the 'Errors only' filter to view advisory warnings."
        />
      ) : (
        <div className="space-y-4">
          {Array.from(groupedByFile.entries()).map(([fileName, fileIssues]) => (
            <Card key={fileName} className="bg-white">
              <CardHeader
                title={
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="w-4 h-4 text-brand-600" />
                    <span className="font-semibold text-slate-900 text-sm">{fileName}</span>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
                      {fileIssues[0]?.file_kind}
                    </span>
                  </div>
                }
                action={
                  <span className="text-xs font-mono text-slate-500 font-medium">
                    {fileIssues.length} issue{fileIssues.length > 1 ? 's' : ''}
                  </span>
                }
              />
              <CardBody className="p-0">
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="text-left px-4 py-2 font-semibold text-slate-600">Severity</th>
                        <th className="text-left px-4 py-2 font-semibold text-slate-600">Row</th>
                        <th className="text-left px-4 py-2 font-semibold text-slate-600">Column</th>
                        <th className="text-left px-4 py-2 font-semibold text-slate-600">Code</th>
                        <th className="text-left px-4 py-2 font-semibold text-slate-600">Message</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {fileIssues.map((issue, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                          <td className="px-4 py-2 whitespace-nowrap">
                            {issue.severity === 'error' ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-800 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded">
                                <AlertCircle className="w-3 h-3 text-rose-600" />
                                <span>Error</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                                <AlertTriangle className="w-3 h-3 text-amber-600" />
                                <span>Warning</span>
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2 whitespace-nowrap font-mono text-[11px] text-slate-600">
                            {issue.row != null ? (
                              <code className="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                                L{issue.row}
                              </code>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-4 py-2 whitespace-nowrap font-mono text-[11px] text-slate-600">
                            {issue.column ? (
                              <code className="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                                {issue.column}
                              </code>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-4 py-2 whitespace-nowrap font-mono text-[11px] text-slate-500">
                            {issue.code}
                          </td>
                          <td className="px-4 py-2 text-slate-800 font-medium leading-relaxed">
                            {sanitise(issue.message)}
                            {issue.value && (
                              <span className="ml-2 font-mono text-[11px] text-slate-400">
                                (got: "{issue.value}")
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
