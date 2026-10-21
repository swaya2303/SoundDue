import { useState, useEffect, useCallback, useMemo } from 'react';
import { tableFeatures, createColumnHelper, useTable } from '@tanstack/react-table';
import { listCases, createCase } from '../api';
import type { Case } from '../types';
import { Card, CardHeader, CardBody } from './ui/Card';
import { Button } from './ui/Button';
import { EmptyState } from './ui/EmptyState';
import { StatusPill } from './ui/Badge';
import { FolderPlus, Search, RefreshCw, FolderArchive, FileSpreadsheet, ArrowRight, Sparkles } from 'lucide-react';
import { useToast } from './ui/Toast';

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Case>();

interface Props {
  onSelect: (c: Case) => void;
}

export default function CasesScreen({ onSelect }: Props) {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  const { toast } = useToast();

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
      const created = await createCase(name.trim(), desc.trim());
      setName('');
      setDesc('');
      toast({
        type: 'success',
        title: 'Case created',
        message: `Case "${created.name}" is ready for record ingestion.`,
      });
      load();
    } catch (err) {
      setCreateError(String(err));
      toast({
        type: 'error',
        title: 'Failed to create case',
        message: String(err),
      });
    } finally {
      setCreating(false);
    }
  }

  const filteredCases = useMemo(() => {
    if (!search.trim()) return cases;
    const q = search.toLowerCase();
    return cases.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.description && c.description.toLowerCase().includes(q)) ||
        String(c.id).includes(q)
    );
  }, [cases, search]);

  const totalFiles = useMemo(() => cases.reduce((acc, c) => acc + (c.file_count || 0), 0), [cases]);

  const columns = helper.columns([
    helper.accessor('id', {
      header: 'ID',
      cell: (ctx) => <span className="font-mono text-xs text-slate-500">#{ctx.cell.getValue()}</span>,
    }),
    helper.accessor('name', {
      header: 'Case Name',
      cell: (ctx) => (
        <div className="flex items-center gap-2">
          <FolderArchive className="w-4 h-4 text-brand-600 shrink-0" />
          <span className="font-semibold text-slate-800 text-sm">{ctx.cell.getValue()}</span>
        </div>
      ),
    }),
    helper.accessor('description', {
      header: 'Description',
      cell: (ctx) => (
        <span className="text-slate-500 text-xs truncate max-w-xs block">
          {ctx.cell.getValue() || '—'}
        </span>
      ),
    }),
    helper.accessor('status', {
      header: 'Status',
      cell: (ctx) => <StatusPill status={ctx.cell.getValue()} />,
    }),
    helper.accessor('file_count', {
      header: 'Files',
      cell: (ctx) => (
        <span className="inline-flex items-center gap-1 font-mono text-xs text-slate-600">
          <FileSpreadsheet className="w-3.5 h-3.5 text-slate-400" />
          <span>{ctx.cell.getValue()}</span>
        </span>
      ),
    }),
    helper.accessor('created_at', {
      header: 'Created',
      cell: (ctx) => (
        <span className="text-xs text-slate-500">
          {new Date(ctx.cell.getValue()).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      ),
    }),
    helper.display({
      id: 'actions',
      header: '',
      cell: (ctx) => (
        <button
          onClick={() => onSelect(ctx.row.original)}
          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-800 p-1 rounded focus-ring"
        >
          <span>Open</span>
          <ArrowRight className="w-3 h-3" />
        </button>
      ),
    }),
  ]);

  const table = useTable({
    features,
    columns,
    data: filteredCases,
  });

  return (
    <div className="space-y-6">
      {/* Top Banner / Summary metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-white">
          <CardBody className="py-3 px-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Total Cases</p>
              <p className="text-2xl font-bold text-slate-900 mt-0.5">{cases.length}</p>
            </div>
            <div className="p-2.5 rounded-lg bg-brand-50 text-brand-600">
              <FolderArchive className="w-5 h-5" />
            </div>
          </CardBody>
        </Card>
        <Card className="bg-white">
          <CardBody className="py-3 px-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Active Workspaces</p>
              <p className="text-2xl font-bold text-slate-900 mt-0.5">
                {cases.filter((c) => c.status === 'active').length}
              </p>
            </div>
            <div className="p-2.5 rounded-lg bg-emerald-50 text-emerald-600">
              <Sparkles className="w-5 h-5" />
            </div>
          </CardBody>
        </Card>
        <Card className="bg-white">
          <CardBody className="py-3 px-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Total Datasets</p>
              <p className="text-2xl font-bold text-slate-900 mt-0.5">{totalFiles}</p>
            </div>
            <div className="p-2.5 rounded-lg bg-sky-50 text-sky-600">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Cases List (2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          <Card className="bg-white">
            <CardHeader
              title="Reconciliation Cases"
              subtitle="Select an active audit case or review historical discrepancies"
              action={
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search cases…"
                      className="pl-8 pr-3 py-1 text-xs border border-slate-300 rounded-lg focus-ring w-44"
                    />
                  </div>
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={load}
                    loading={loading}
                    icon={<RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />}
                  >
                    Refresh
                  </Button>
                </div>
              }
            />

            <CardBody className="p-0">
              {error && (
                <div className="p-4 text-xs text-rose-700 bg-rose-50 border-b border-rose-100">
                  {error}
                </div>
              )}

              {loading && cases.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-500">Loading cases…</div>
              ) : filteredCases.length === 0 ? (
                <div className="p-6">
                  <EmptyState
                    title="No reconciliation cases found"
                    description={
                      search
                        ? 'No cases match your search query.'
                        : 'No reconciliation cases have been opened yet. Create one on the right to start.'
                    }
                  />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead className="bg-slate-50/80 border-b border-slate-200">
                      {table.getHeaderGroups().map((hg) => (
                        <tr key={hg.id}>
                          {hg.headers.map((h) => (
                            <th
                              key={h.id}
                              className="text-left px-4 py-2.5 font-semibold text-slate-600 whitespace-nowrap"
                            >
                              {h.isPlaceholder ? null : <table.FlexRender header={h} />}
                            </th>
                          ))}
                        </tr>
                      ))}
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {table.getRowModel().rows.map((row) => (
                        <tr
                          key={row.id}
                          onClick={() => onSelect(row.original)}
                          className="hover:bg-brand-50/40 cursor-pointer transition-colors"
                        >
                          {row.getAllCells().map((cell) => (
                            <td key={cell.id} className="px-4 py-2.5 text-slate-700 whitespace-nowrap">
                              <table.FlexRender cell={cell} />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Right: Create Case Card (1 col) */}
        <div>
          <Card className="bg-white sticky top-20">
            <CardHeader
              title="Create New Case"
              subtitle="Open an audit workspace for a new reconciliation batch"
              action={<FolderPlus className="w-4 h-4 text-brand-600" />}
            />
            <CardBody>
              <form onSubmit={handleCreate} className="space-y-4">
                {createError && (
                  <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                    {createError}
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Case Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus-ring text-slate-800 placeholder:text-slate-400"
                    placeholder="e.g. Midnight Train Q4 Reconcile"
                    required
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    A distinct label identifying the catalog, artist, or royalty quarter.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Description & Notes
                  </label>
                  <textarea
                    value={desc}
                    onChange={(e) => setDesc(e.target.value)}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-xs focus-ring text-slate-800 placeholder:text-slate-400"
                    rows={3}
                    placeholder="Optional details, CMO source schedules, period dates, or tracking IDs…"
                  />
                </div>

                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  className="w-full"
                  disabled={creating || !name.trim()}
                  loading={creating}
                  icon={<FolderPlus className="w-3.5 h-3.5" />}
                >
                  {creating ? 'Creating…' : 'Create Case'}
                </Button>
              </form>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
