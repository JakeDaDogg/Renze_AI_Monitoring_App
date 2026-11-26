import { DIAGRAM_COMPONENTS, type DiagramComponent } from "@/data/diagramComponents";

/**
 * Data access layer. Every function here is mocked for now; each has the
 * backend call it will become, so pages and components never call fetch
 * directly.
 */

export async function getDiagramComponents(): Promise<DiagramComponent[]> {
  // TODO(backend): GET `${API_BASE_URL}/api/components` (SQL-backed registry,
  // incl. `notes` and future fields).
  return [...DIAGRAM_COMPONENTS];
}

export async function getComponentDetails(id: string): Promise<DiagramComponent | null> {
  // TODO(backend): GET `${API_BASE_URL}/api/components/${id}`.
  return DIAGRAM_COMPONENTS.find((c) => c.id === id) ?? null;
}
