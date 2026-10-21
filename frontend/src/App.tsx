import { useState } from 'react';
import CasesScreen from './components/CasesScreen';
import CaseWorkspace from './components/CaseWorkspace';
import { ToastProvider } from './components/ui/Toast';
import type { Case } from './types';
import { Music2, Sparkles, FolderArchive } from 'lucide-react';

export default function App() {
  const [activeCase, setActiveCase] = useState<Case | null>(null);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-slate-100 text-slate-800 flex flex-col font-sans">
        {/* Top App Shell Navigation */}
        <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30 shadow-subtle">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
            {/* Logo + Product Name */}
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white shadow-subtle">
                <Music2 className="w-4 h-4 stroke-[2.2]" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-bold text-sm tracking-tight text-white leading-none">SoundDue</h1>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                    Audit Workbench
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-none mt-1">
                  Explainable Music-Record Reconciliation
                </p>
              </div>
            </div>

            {/* Middle: Active Case or Demo Notice */}
            <div className="flex items-center gap-3">
              {/* Visible "Fictional demo data" badge */}
              <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/30">
                <Sparkles className="w-3 h-3 text-amber-400" />
                <span>Fictional demo data</span>
              </span>

              {activeCase && (
                <div className="flex items-center gap-2 pl-3 border-l border-slate-700 text-xs">
                  <span className="text-slate-400">Active Case:</span>
                  <span className="font-medium text-white bg-slate-800 px-2.5 py-1 rounded border border-slate-700 flex items-center gap-2">
                    <FolderArchive className="w-3.5 h-3.5 text-brand-400" />
                    <span className="truncate max-w-[200px]">{activeCase.name}</span>
                    <button
                      onClick={() => setActiveCase(null)}
                      className="text-slate-400 hover:text-white ml-1 p-0.5 rounded hover:bg-slate-700 focus-ring"
                      title="Close case"
                      aria-label="Close case"
                    >
                      ✕
                    </button>
                  </span>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 flex-1">
          {activeCase == null ? (
            <CasesScreen onSelect={setActiveCase} />
          ) : (
            <CaseWorkspace case_={activeCase} onCloseCase={() => setActiveCase(null)} />
          )}
        </main>

        {/* Persistent Audit Disclaimer Footer */}
        <footer className="border-t border-slate-200 bg-white py-4 mt-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500">
            <p className="font-medium text-slate-600">
              Findings are leads for human review, not ownership determinations.
            </p>
            <div className="flex items-center gap-4 text-slate-600">
              <span>SoundDue © {new Date().getFullYear()}</span>
              <span>·</span>
              <span className="font-mono text-[11px]">Symbolic Reasoner v1.0</span>
            </div>
          </div>
        </footer>
      </div>
    </ToastProvider>
  );
}
