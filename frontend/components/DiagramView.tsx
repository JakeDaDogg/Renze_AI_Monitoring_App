"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import InteractiveDiagram from "@/components/InteractiveDiagram";
import ComponentInfoPanel from "@/components/ComponentInfoPanel";
import { getComponentById, type DiagramComponentId } from "@/data/diagramComponents";
import { logout, useSession } from "@/lib/auth";

const LEGEND = [
  { label: "熱水 Hot water", color: "#ef4444" },
  { label: "蒸汽 Steam", color: "#f472b6" },
  { label: "回注水 Reinjection", color: "#7dd3fc" },
  { label: "工作流體 Working fluid", color: "#facc15" },
];

export default function DiagramView() {
  const router = useRouter();
  const session = useSession();
  const [selectedId, setSelectedId] = useState<DiagramComponentId | null>(null);

  // Mock route guard: send signed-out users back to the login page.
  // TODO(backend): move to proxy.ts (formerly middleware) once auth uses cookies.
  useEffect(() => {
    if (session === null) router.replace("/login");
  }, [session, router]);

  if (!session) {
    return (
      <main className="min-h-dvh flex items-center justify-center text-sm text-slate-500">
        Loading…
      </main>
    );
  }

  const selected = selectedId ? getComponentById(selectedId) ?? null : null;

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <main className="min-h-dvh flex flex-col bg-slate-50">
      <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3 md:px-6">
        <h1 className="text-base font-semibold text-slate-900 md:text-lg">
          Renze plant diagram
        </h1>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-slate-500 md:inline">{session.username}</span>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 transition hover:bg-slate-100"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6 lg:flex-row">
        <section className="h-fit min-w-0 rounded-2xl lg:flex-1 border border-slate-200 bg-white p-2 md:p-4">
          <div className="overflow-x-auto rounded-xl">
            <InteractiveDiagram selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 px-2 text-xs text-slate-500">
            {LEGEND.map((l) => (
              <span key={l.label} className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-5 rounded-full" style={{ background: l.color }} />
                {l.label}
              </span>
            ))}
            <span className="text-slate-400 md:ml-auto">Hover to highlight · click or tap to select</span>
          </div>
        </section>

        <aside className="h-fit lg:w-80 lg:shrink-0">
          <ComponentInfoPanel component={selected} onClear={() => setSelectedId(null)} />
        </aside>
      </div>
    </main>
  );
}
