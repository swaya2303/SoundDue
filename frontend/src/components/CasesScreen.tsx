import { useState, useEffect, useCallback } from 'react';
import { tableFeatures, createColumnHelper, useTable } from '@tanstack/react-table';
import { listCases, createCase } from '../api';
import type { Case } from '../types';

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Case>();

interface Props {
  onSelect: (c: Case) => void;
}

export default function CasesScreen({ onSelect }: Props) {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listCases()
      .then(setCases)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setCreateError('');
    try {
      await createCase(name.trim(), desc.trim());
      setName('');
      setDesc('');
      load();
    } catch (err) {
      setCreateError(String(err));
    } finally {
      setCreating(false);
    }
  }

  const columns = helper.columns([
    helper.accessor('id', { header: 'ID' }),
    helper.accessor('name', {
      header: 'Name',
      cell: (ctx) => <span className="font-medium">{ctx.cell.getValue()}</span>,
    }),
    helper.accessor('description', {
      header: 'Description',
      cell: (ctx) => <span className="text-slate-500">{ctx.cell.getValue() || '—'}</span>,
    }),
    helper.accessor('status', {
      header: 'Status',
      cell: (ctx) => <span className="capitalize">{ctx.cell.getValue()}</span>,
    }),
    helper.accessor('file_count', { header: 'Files' }),
    helper.accessor('created_at', {
      header: 'Created',
      cell: (ctx) => new Date(ctx.cell.getValue()).toLocaleString(),
    }),
    helper.display({
      id: 'actions',
      header: 'Actions',
      cell: (ctx) => (
        <button
          onClick={() => onSelect(ctx.row.original)}
          className="text-indigo-600 hover:underline text-sm"
        >
          Open →
        </button>
      ),
    }),
  ]);

  const table = useTable({
    features,
    columns,
    data: cases,
  });

  return (
    <div className="space-y-6">
      {/* Case list */}
      <div className="bg-white rounded-xl shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Cases</h2>
          <button onClick={load} className="text-indigo-600 text-sm hover:underline">
            Refresh
          </button>
        </div>
        {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
        {loading ? (
          <p className="text-slate-500">Loading…</p>
        ) : cases.length === 0 ? (
          <p className="text-slate-500">No cases yet. Create one below.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((h) => (
                      <th
                        key={h.id}
                        className="text-left px-3 py-2 text-slate-600 font-medium border-b"
                      >
                        {h.isPlaceholder ? null : <table.FlexRender header={h} />}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-50 border-b last:border-0">
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

      {/* Create form */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Create a new case</h2>
        {createError && <p className="text-red-600 text-sm mb-3">{createError}</p>}
        <form onSubmit={handleCreate} className="space-y-3 max-w-md">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
              placeholder="e.g. Midnight Train Q4"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Description
            </label>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
              rows={2}
              placeholder="Optional notes"
            />
          </div>
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="bg-indigo-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-indigo-700"
          >
            {creating ? 'Creating…' : 'Create Case'}
          </button>
        </form>
      </div>
    </div>
  );
}
