import { useMemo } from 'react';
import { tableFeatures, createColumnHelper, useTable } from '@tanstack/react-table';
import type { UploadedFile, ValidationIssue } from '../types';

interface FlatIssue extends ValidationIssue {
  file_name: string;
}

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, FlatIssue>();

function sanitise(msg: string): string {
  return msg.replace(/\bunclaimed\b/gi, 'missing from the supplied records');
}

const columns = helper.columns([
  helper.accessor('file_name', { header: 'File' }),
  helper.accessor('row', {
    header: 'Row',
    cell: (ctx) => (ctx.cell.getValue() != null ? String(ctx.cell.getValue()) : '—'),
  }),
  helper.accessor('column', {
    header: 'Column',
    cell: (ctx) => ctx.cell.getValue() ?? '—',
  }),
  helper.accessor('code', { header: 'Code' }),
  helper.accessor('message', {
    header: 'Message',
    cell: (ctx) => sanitise(ctx.cell.getValue()),
  }),
]);

interface Props {
  uploadedFiles: UploadedFile[];
}

export default function ValidationSection({ uploadedFiles }: Props) {
  const issues = useMemo<FlatIssue[]>(
    () =>
      uploadedFiles.flatMap((uf) =>
        uf.validation.issues.map((issue) => ({ ...issue, file_name: uf.original_name })),
      ),
    [uploadedFiles],
  );

  const table = useTable({
    features,
    columns,
    data: issues,
  });

  if (uploadedFiles.length === 0) {
    return <p className="text-slate-500">No files uploaded yet.</p>;
  }

  const filesLabel = `${uploadedFiles.length} file${uploadedFiles.length > 1 ? 's' : ''}`;

  return (
    <div>
      <div
        className={`mb-4 px-4 py-2 rounded text-sm ${
          issues.length > 0
            ? 'bg-amber-50 border border-amber-200 text-amber-800'
            : 'bg-green-50 border border-green-200 text-green-800'
        }`}
      >
        {issues.length > 0
          ? `${issues.length} issue${issues.length > 1 ? 's' : ''} across ${filesLabel}`
          : `No issues found across ${filesLabel}`}
      </div>

      {issues.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => (
                    <th
                      key={h.id}
                      className="text-left px-3 py-2 border-b text-slate-600 font-medium"
                    >
                      {h.isPlaceholder ? null : <table.FlexRender header={h} />}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b last:border-0 hover:bg-slate-50">
                  {row.getAllCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2">
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
