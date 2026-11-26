import type { DiagramComponent } from "@/data/diagramComponents";

type Props = {
  component: DiagramComponent | null;
  onClear: () => void;
};

export default function ComponentInfoPanel({ component, onClear }: Props) {
  return (
    <div
      aria-live="polite"
      className="rounded-2xl border border-slate-200 bg-white p-4 md:p-5"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Selected component
      </h2>

      {component ? (
        <>
          {component.nameZh && (
            <p className="mt-2 text-lg font-semibold text-slate-900">{component.nameZh}</p>
          )}
          <p className={component.nameZh ? "text-base text-slate-700" : "mt-2 text-lg font-semibold text-slate-900"}>
            {component.name}
          </p>
          {component.category && (
            <p className="mt-1 text-sm text-slate-500">{component.category}</p>
          )}
          {/* Future SQL-backed fields (status, sensors, RUL…) go here. */}
          <p className="mt-3 text-sm text-slate-600">
            {component.notes ?? "No notes yet."}
          </p>
          <button
            type="button"
            onClick={onClear}
            className="mt-4 text-sm text-slate-500 underline-offset-2 hover:underline"
          >
            Clear selection
          </button>
        </>
      ) : (
        <p className="mt-2 text-sm text-slate-500">
          Click a component on the diagram to see its name here.
        </p>
      )}
    </div>
  );
}
