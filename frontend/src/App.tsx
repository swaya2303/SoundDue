import { useState } from 'react';
import CasesScreen from './components/CasesScreen';
import CaseWorkspace from './components/CaseWorkspace';
import type { Case } from './types';

export default function App() {
  const [activeCase, setActiveCase] = useState<Case | null>(null);

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-indigo-700 text-white px-6 py-3 shadow flex items-center gap-4">
        <span className="text-xl select-none">🎵</span>
        <div>
          <h1 className="font-bold text-lg leading-none">SoundDue</h1>
          <p className="text-indigo-300 text-xs">Music record reconciliation · Prototype</p>
        </div>
        {activeCase && (
          <div className="ml-4 flex items-center gap-2 bg-indigo-600 rounded px-3 py-1">
            <span className="text-sm">
              Case: <strong>{activeCase.name}</strong>
            </span>
            <button
              onClick={() => setActiveCase(null)}
              className="text-indigo-300 hover:text-white ml-2 text-xs leading-none"
              title="Close case"
            >
              ✕
            </button>
          </div>
        )}
      </header>

      <main className="max-w-6xl mx-auto mt-6 px-4 pb-10">
        {activeCase == null ? (
          <CasesScreen onSelect={setActiveCase} />
        ) : (
          <CaseWorkspace case_={activeCase} />
        )}
      </main>

      <footer className="text-center text-xs text-slate-400 py-4">
        SoundDue © {new Date().getFullYear()} — Prototype · Not for production use
      </footer>
    </div>
  );
}
