/**
 * Typed registry of the interactive regions on the plant diagram.
 *
 * Each `id` must have a matching shape in `components/InteractiveDiagram.tsx`
 * (the `SHAPES` map there is typed against `DiagramComponentId`, so a missing
 * or extra shape is a compile error).
 *
 * Layout source: Renze_site_layout.pdf, with the settling pond (沉澱池)
 * replaced by the pressurized buffer vessel. Later this list will come from
 * the backend (see lib/api.ts).
 */

export type DiagramComponent = {
  id: string;
  name: string;
  nameZh?: string;
  category?: string;
  notes?: string; // Placeholder for future SQL database fields
};

export const DIAGRAM_COMPONENTS = [
  { id: "production-well", name: "Production Well (Well 4)", nameZh: "四號井（生產井）", category: "Geofluid" },
  { id: "production-pipeline", name: "Production Pipeline", nameZh: "生產管線", category: "Geofluid" },
  { id: "separator", name: "Steam–Water Separator", nameZh: "汽液分離槽", category: "Geofluid" },
  { id: "evaporator", name: "Evaporator", nameZh: "蒸發器", category: "Heat exchanger" },
  { id: "brine-preheater", name: "Brine Preheater", nameZh: "預熱器（熱水）", category: "Heat exchanger" },
  { id: "steam-preheater", name: "Steam Preheater", nameZh: "預熱器（蒸汽）", category: "Heat exchanger" },
  { id: "ncg-separator", name: "NCG Separator", nameZh: "汽液分離槽（不凝結氣）", category: "Geofluid" },
  { id: "buffer-vessel", name: "Pressurized Buffer Vessel", nameZh: "加壓緩衝槽", category: "Geofluid" },
  { id: "reinjection-pump", name: "Reinjection Pump", nameZh: "回注泵", category: "Geofluid" },
  { id: "reinjection-well", name: "Reinjection Well (Well 3)", nameZh: "三號井（回注井）", category: "Geofluid" },
  { id: "orc-turbine", name: "ORC Turbine", nameZh: "渦輪", category: "ORC loop" },
  { id: "generator", name: "Generator", nameZh: "發電機", category: "Electrical" },
  { id: "air-condenser", name: "Air-Cooled Condenser", nameZh: "空氣冷凝器", category: "ORC loop" },
  { id: "feed-pump", name: "Working-Fluid Pump", nameZh: "工作流體泵", category: "ORC loop" },
] as const satisfies readonly DiagramComponent[];

export type DiagramComponentId = (typeof DIAGRAM_COMPONENTS)[number]["id"];

export function getComponentById(id: string): DiagramComponent | undefined {
  return DIAGRAM_COMPONENTS.find((c) => c.id === id);
}
