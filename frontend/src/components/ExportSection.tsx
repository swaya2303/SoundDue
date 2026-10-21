import { Download, FileCode, FileSpreadsheet, FileText, ExternalLink } from 'lucide-react';
import { Card, CardBody } from './ui/Card';
import { Callout } from './ui/Callout';
import { API_BASE } from '../api';

interface Props {
  caseId: number;
  caseName: string;
}

export default function ExportSection({ caseId, caseName }: Props) {
  const formats = [
    {
      id: 'html',
      title: 'Interactive HTML Audit Report',
      formatLabel: 'HTML',
      icon: <FileText className="w-6 h-6 text-brand-600" />,
      description:
        'A self-contained, human-readable report complete with the six-part breakdown for every finding, full rule traces, evidence records, side-by-side comparison tables, and formal disclaimer notices.',
      idealFor: 'Sharing with publisher clients, internal legal review, and archiving dispute files.',
      filename: `findings-case-${caseId}.html`,
    },
    {
      id: 'csv',
      title: 'Findings Spreadsheet Table',
      formatLabel: 'CSV',
      icon: <FileSpreadsheet className="w-6 h-6 text-emerald-600" />,
      description:
        'One row per finding containing ID, finding type, severity, rule ID, version, summary text, and current status. Compatible with Excel, Numbers, and Google Sheets.',
      idealFor: 'Bulk operations, batch filtering, accounting spreadsheets, and CMO upload tickets.',
      filename: `findings-case-${caseId}.csv`,
    },
    {
      id: 'json',
      title: 'Structured JSON Payload',
      formatLabel: 'JSON',
      icon: <FileCode className="w-6 h-6 text-indigo-600" />,
      description:
        'The complete structured object hierarchy including normalized record references, ordered rule trace checklists, evaluation timestamps, and review decisions.',
      idealFor: 'Automated ingestion into ERPs, rights administration engines, and CI/CD audit pipelines.',
      filename: `findings-case-${caseId}.json`,
    },
  ];

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h3 className="text-base font-semibold text-slate-800">Export Case Reconciliation Findings</h3>
        <p className="text-xs text-slate-500 mt-1">
          Export verified findings, evidence records, and symbolic rule traces for Case #{caseId}:{' '}
          <strong className="text-slate-700">{caseName}</strong>.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {formats.map((fmt) => {
          const exportUrl = `${API_BASE}/cases/${caseId}/export?format=${fmt.id}`;

          return (
            <Card key={fmt.id} className="flex flex-col justify-between hover:border-slate-300 transition-colors">
              <CardBody className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="p-2 rounded-lg bg-slate-50 border border-slate-200">{fmt.icon}</div>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 font-semibold text-slate-700">
                    .{fmt.formatLabel.toLowerCase()}
                  </span>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-slate-800">{fmt.title}</h4>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed">{fmt.description}</p>
                </div>
                <div className="pt-2 border-t border-slate-100">
                  <span className="text-[11px] font-medium text-slate-400 block mb-0.5">Best used for:</span>
                  <span className="text-xs text-slate-600">{fmt.idealFor}</span>
                </div>
              </CardBody>
              <div className="p-4 bg-slate-50/70 border-t border-slate-100 flex items-center justify-between gap-2">
                <a
                  href={exportUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-brand-600 hover:text-brand-800 font-medium"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Preview</span>
                </a>
                <a
                  href={exportUrl}
                  download={fmt.filename}
                  className="inline-flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-brand-600 text-white hover:bg-brand-700 shadow-subtle focus-ring"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download</span>
                </a>
              </div>
            </Card>
          );
        })}
      </div>

      <Callout type="neutral" title="Compliance & Audit Notice">
        Exported files preserve the full symbolic trace of all evaluated rules and immutable evidence references.
        Findings represent discrepancies flagged for human inspection and should be verified with CMO schedules and
        signed agreements prior to royalty adjustments.
      </Callout>
    </div>
  );
}
