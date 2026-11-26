"use client";

import type { KeyboardEvent, ReactNode } from "react";
import {
  DIAGRAM_COMPONENTS,
  type DiagramComponentId,
} from "@/data/diagramComponents";

/**
 * Inline-SVG replica of the Renze site layout (Renze_site_layout.pdf),
 * redrawn with shading and texture. Coordinates follow the PDF rendered at
 * 1334 × 750 px, so shapes can be checked against it directly.
 *
 * Change from the PDF: the settling pond (沉澱池) is drawn as the pressurized
 * buffer vessel.
 *
 * Every interactive part has one element with class `part-shape` (its
 * outline); hover / focus makes that outline glow red (see .diagram-part in
 * app/globals.css). Pipes are drawn first so they pass behind equipment.
 */

const VIEWBOX = "0 60 1334 690";

/* ------------------------------------------------------------------ pipes */

type Fluid = "hot" | "steam" | "reinject" | "orc" | "util";

const FLUID: Record<Fluid, { edge: string; base: string; hi: string }> = {
  hot: { edge: "#b91c1c", base: "#ef4444", hi: "#fecaca" }, // 熱水 brine
  steam: { edge: "#be185d", base: "#f472b6", hi: "#fce7f3" }, // 蒸汽 steam
  reinject: { edge: "#0369a1", base: "#7dd3fc", hi: "#f0f9ff" }, // 回注水
  orc: { edge: "#ca8a04", base: "#fde047", hi: "#fefce8" }, // 工作流體
  util: { edge: "#475569", base: "#94a3b8", hi: "#e2e8f0" },
};

type PipeProps = {
  d: string;
  fluid: Fluid;
  width?: number;
  /** Extra class on the outer (white) stroke, e.g. "part-shape". */
  outerClass?: string;
  flow?: boolean;
};

/** Tube look: white casing, dark edge, body, centre sheen, moving flow dots. */
function Pipe({ d, fluid, width = 18, outerClass, flow = true }: PipeProps) {
  const c = FLUID[fluid];
  const common = { d, fill: "none", strokeLinejoin: "round" as const, strokeLinecap: "butt" as const };
  return (
    <g>
      <path {...common} className={outerClass} stroke="#ffffff" strokeWidth={width + 6} />
      <path {...common} stroke={c.edge} strokeWidth={width} />
      <path {...common} stroke={c.base} strokeWidth={width - 5} />
      <path {...common} stroke={c.hi} strokeWidth={width * 0.22} opacity={0.75} transform="translate(-1.5 -1.5)" />
      {flow && (
        <path
          {...common}
          className="flow"
          stroke="#ffffff"
          strokeOpacity={0.7}
          strokeWidth={width * 0.24}
          strokeLinecap="round"
        />
      )}
    </g>
  );
}

function Valve({ x, y }: { x: number; y: number }) {
  // Bow-tie gate valve, PDF style.
  return (
    <g className="pointer-events-none">
      <polygon points={`${x},${y - 9} ${x + 15},${y} ${x},${y + 9}`} fill="url(#steel-v)" stroke="#334155" strokeWidth={1} />
      <polygon points={`${x + 30},${y - 9} ${x + 15},${y} ${x + 30},${y + 9}`} fill="url(#steel-v)" stroke="#334155" strokeWidth={1} />
    </g>
  );
}

/** Thin vertical lines suggesting shell flanges / end-cap seams. */
function Seams({ xs, y, h }: { xs: number[]; y: number; h: number }) {
  return (
    <g className="pointer-events-none">
      {xs.map((x) => (
        <g key={x}>
          <line x1={x} y1={y} x2={x} y2={y + h} stroke="#ffffff" strokeWidth={3} opacity={0.9} />
          <line x1={x + 2} y1={y} x2={x + 2} y2={y + h} stroke="#0f172a" strokeWidth={1} opacity={0.15} />
        </g>
      ))}
    </g>
  );
}

/** Horizontal heat-exchanger shell with darker end heads. */
function Shell(props: {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  head: number;
  body: string;
  ends: string;
}) {
  const { id, x, y, w, h, head, body, ends } = props;
  const r = h / 2;
  return (
    <>
      <clipPath id={id}>
        <rect x={x} y={y} width={w} height={h} rx={r} />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        <rect x={x} y={y} width={w} height={h} fill={body} />
        <rect x={x} y={y} width={head} height={h} fill={ends} />
        <rect x={x + w - head} y={y} width={head} height={h} fill={ends} />
        <rect x={x} y={y} width={w} height={h} fill="url(#brushed)" />
        <rect x={x} y={y} width={w} height={h} fill="url(#cyl-shade-h)" />
      </g>
      <Seams xs={[x + head, x + w - head]} y={y} h={h} />
      <rect className="part-shape" x={x} y={y} width={w} height={h} rx={r} fill="none" stroke="#ffffff" strokeWidth={2.5} />
    </>
  );
}

/** Vertical two-phase vessel (gas on top, liquid below) on legs. */
function VerticalSeparator(props: {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  split: number;
  topText: string[];
  bottomText: string;
  fontSize: number;
}) {
  const { id, x, y, w, h, split, topText, bottomText, fontSize } = props;
  const cx = x + w / 2;
  const topMid = (y + split) / 2 + 6 - ((topText.length - 1) * fontSize) / 2;
  return (
    <>
      {/* legs */}
      <g stroke="#64748b" strokeWidth={3} strokeLinecap="round" className="pointer-events-none">
        <line x1={x + w * 0.2} y1={y + h - 12} x2={x + w * 0.05} y2={y + h + 26} />
        <line x1={x + w * 0.8} y1={y + h - 12} x2={x + w * 0.95} y2={y + h + 26} />
      </g>
      <clipPath id={id}>
        <rect x={x} y={y} width={w} height={h} rx={w / 2} />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        <rect x={x} y={y} width={w} height={split - y} fill="url(#steam-fill)" />
        <rect x={x} y={split} width={w} height={y + h - split} fill="url(#water-brown)" />
        <path
          d={`M${x} ${split} q${w / 8} -5 ${w / 4} 0 t${w / 4} 0 t${w / 4} 0 t${w / 4} 0`}
          fill="none"
          stroke="#ffffff"
          strokeOpacity={0.55}
          strokeWidth={2}
        />
        <rect x={x} y={y} width={w} height={h} fill="url(#cyl-shade-v)" />
      </g>
      <g className="pointer-events-none" fill="#ffffff" fontWeight={700} fontSize={fontSize} textAnchor="middle">
        {topText.map((t, i) => (
          <text key={t} x={cx} y={topMid + i * (fontSize + 2)} className="vessel-text">
            {t}
          </text>
        ))}
        <text x={cx} y={(split + y + h) / 2 + 6} className="vessel-text">
          {bottomText}
        </text>
      </g>
      <rect className="part-shape" x={x} y={y} width={w} height={h} rx={w / 2} fill="none" stroke="#ffffff" strokeWidth={2.5} />
    </>
  );
}

/** Vertical in-line pump (PDF style: body on a stem with a foot). */
function InlinePump({ x, y, h = 36 }: { x: number; y: number; h?: number }) {
  return (
    <>
      <ellipse cx={x} cy={y + h + 20} rx={24} ry={6} fill="url(#bronze)" />
      <rect x={x - 3} y={y + h - 4} width={6} height={26} fill="#7c5a4a" />
      <rect className="part-shape" x={x - 9} y={y} width={18} height={h} rx={8} fill="url(#bronze)" stroke="#ffffff" strokeWidth={2} />
      <rect x={x - 9} y={y + h * 0.35} width={18} height={3} fill="#ffffff" opacity={0.5} />
    </>
  );
}

function Well({ x }: { x: number }) {
  return (
    <>
      <rect x={x - 11} y={662} width={56} height={13} rx={2} fill="url(#steel-h)" />
      <rect className="part-shape" x={x} y={568} width={35} height={94} rx={2} fill="url(#steel-v)" stroke="#ffffff" strokeWidth={2} />
      <rect x={x} y={590} width={35} height={4} fill="#0f172a" opacity={0.12} />
      <rect x={x} y={630} width={35} height={4} fill="#0f172a" opacity={0.12} />
      <rect x={x + 35} y={631} width={27} height={12} fill="url(#steel-h)" />
    </>
  );
}

/* ----------------------------------------------------------------- shapes */

type Label = { zh: string; en: string; x: number; y: number };

type Shape = {
  label?: Label;
  render: () => ReactNode;
};

const SHAPES: Record<DiagramComponentId, Shape> = {
  "production-well": {
    label: { zh: "四號井 (生產井)", en: "Well 4 · Production", x: 92, y: 702 },
    render: () => (
      <>
        <Well x={73} />
        <Valve x={135} y={637} />
      </>
    ),
  },
  "production-pipeline": {
    render: () => (
      <>
        <path d="M165 637 H195 V300 H302" fill="none" stroke="transparent" strokeWidth={34} />
        <Pipe d="M165 637 H195 V300 H302" fluid="hot" outerClass="part-shape" />
      </>
    ),
  },
  separator: {
    label: { zh: "液汽分離槽", en: "Steam–Water Separator", x: 346, y: 466 },
    render: () => (
      <VerticalSeparator id="clip-sep1" x={300} y={152} w={92} h={260} split={308} topText={["蒸汽"]} bottomText="熱水" fontSize={20} />
    ),
  },
  evaporator: {
    render: () => (
      <>
        <Shell id="clip-evap" x={628} y={185} w={240} h={100} head={52} body="url(#evap-body)" ends="url(#evap-ends)" />
        <text x={748} y={238} textAnchor="middle" className="pointer-events-none part-label fill-slate-700 text-[21px] font-bold">
          蒸發器
        </text>
        <text x={748} y={258} textAnchor="middle" className="pointer-events-none part-label-en fill-slate-500 text-[11px]">
          Evaporator
        </text>
      </>
    ),
  },
  "brine-preheater": {
    render: () => (
      <>
        <Shell id="clip-ph1" x={665} y={323} w={203} h={64} head={52} body="url(#ph-body)" ends="url(#ph-ends)" />
        <text x={766} y={356} textAnchor="middle" className="pointer-events-none part-label fill-slate-700 text-[18px] font-bold">
          預熱器
        </text>
        <text x={766} y={373} textAnchor="middle" className="pointer-events-none part-label-en fill-slate-500 text-[10.5px]">
          Brine Preheater
        </text>
      </>
    ),
  },
  "steam-preheater": {
    render: () => (
      <>
        <Shell id="clip-ph2" x={665} y={418} w={203} h={64} head={52} body="url(#ph-body)" ends="url(#ph-ends)" />
        <text x={766} y={451} textAnchor="middle" className="pointer-events-none part-label fill-slate-700 text-[18px] font-bold">
          預熱器
        </text>
        <text x={766} y={468} textAnchor="middle" className="pointer-events-none part-label-en fill-slate-500 text-[10.5px]">
          Steam Preheater
        </text>
      </>
    ),
  },
  "ncg-separator": {
    label: { zh: "液汽分離槽", en: "NCG Separator", x: 712, y: 712 },
    render: () => (
      <VerticalSeparator id="clip-sep2" x={686} y={528} w={52} h={140} split={615} topText={["不凝", "結氣"]} bottomText="熱水" fontSize={14} />
    ),
  },
  "buffer-vessel": {
    label: { zh: "加壓桶槽", en: "Pressurized Buffer Vessel", x: 550, y: 712 },
    render: () => (
      <>
        {/* saddles */}
        <g className="pointer-events-none" fill="url(#steel-h)">
          <polygon points="500,668 524,668 530,690 494,690" />
          <polygon points="576,668 600,668 606,690 570,690" />
        </g>
        <clipPath id="clip-bv">
          <rect x={470} y={588} width={160} height={92} rx={46} />
        </clipPath>
        <g clipPath="url(#clip-bv)">
          <rect x={470} y={588} width={160} height={92} fill="url(#gas-fill)" />
          <path className="wave" d="M380 624 q15 -6 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 V690 H380 Z" fill="url(#water-blue)" />
          <path className="wave" d="M380 624 q15 -6 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0" fill="none" stroke="#ffffff" strokeOpacity={0.7} strokeWidth={2} />
          <rect x={470} y={588} width={160} height={92} fill="url(#cyl-shade-h)" />
        </g>
        <Seams xs={[516, 584]} y={588} h={92} />
        <rect className="part-shape" x={470} y={588} width={160} height={92} rx={46} fill="none" stroke="#ffffff" strokeWidth={2.5} />
        {/* pressure gauge */}
        <g className="pointer-events-none">
          <line x1={550} y1={588} x2={550} y2={574} stroke="#64748b" strokeWidth={3} />
          <circle cx={550} cy={566} r={9} fill="#f8fafc" stroke="#64748b" strokeWidth={2} />
          <line x1={550} y1={566} x2={555} y2={561} stroke="#dc2626" strokeWidth={1.5} />
        </g>
      </>
    ),
  },
  "reinjection-pump": {
    label: { zh: "回注泵", en: "Reinjection Pump", x: 401, y: 702 },
    render: () => <InlinePump x={401} y={617} />,
  },
  "reinjection-well": {
    label: { zh: "三號井 (回注井)", en: "Well 3 · Reinjection", x: 264, y: 702 },
    render: () => (
      <>
        <Well x={246} />
        <Valve x={308} y={637} />
      </>
    ),
  },
  "orc-turbine": {
    label: { zh: "渦輪", en: "Turbine", x: 1090, y: 228 },
    render: () => (
      <>
        <polygon className="part-shape" points="1000,122 1085,80 1085,200 1000,158" fill="url(#turbine-fill)" stroke="#ffffff" strokeWidth={2.5} />
        {/* blade stages */}
        <g className="pointer-events-none">
          {[0, 1, 2].map((i) => {
            const x0 = 1008 + i * 25;
            const t = (x0 - 1000) / 85;
            const top = 122 - 42 * t + 6;
            const bot = 158 + 42 * t - 6;
            return (
              <g key={i}>
                <polygon points={`${x0},${top} ${x0 + 20},${top - 6} ${x0 + 20},${bot + 6} ${x0},${bot}`} fill="url(#blade)" opacity={0.95} />
                <line x1={x0 + 20} y1={top - 6} x2={x0 + 20} y2={bot + 6} stroke="#ffffff" strokeWidth={1.5} />
              </g>
            );
          })}
          <path d="M1003 122 a12 18 0 0 0 0 36 Z" fill="#334155" />
        </g>
      </>
    ),
  },
  generator: {
    label: { zh: "發電機", en: "Generator", x: 1215, y: 228 },
    render: () => (
      <>
        <rect className="part-shape" x={1145} y={82} width={140} height={113} rx={12} fill="url(#gen-fill)" stroke="#ffffff" strokeWidth={2.5} />
        <g className="pointer-events-none">
          {[92, 112, 160, 178].map((y) => (
            <rect key={y} x={1163} y={y} width={104} height={11} rx={2} fill="url(#slot)" stroke="#334155" strokeWidth={1} />
          ))}
          <rect x={1145} y={82} width={140} height={113} rx={12} fill="url(#brushed)" />
          <line x1={1145} y1={140} x2={1290} y2={140} stroke="#1f2937" strokeWidth={9} strokeLinecap="round" />
        </g>
      </>
    ),
  },
  "air-condenser": {
    label: { zh: "空氣冷凝器", en: "Air-Cooled Condenser", x: 1140, y: 444 },
    render: () => (
      <>
        {/* fan housings, blades, motors */}
        <g className="pointer-events-none">
          {[1015, 1145].map((x) => (
            <g key={x}>
              <polygon points={`${x},360 ${x + 122},360 ${x + 112},380 ${x + 10},380`} fill="url(#green-fill)" stroke="#ffffff" strokeWidth={1.5} />
              <g className="fan-blades" style={{ transformOrigin: `${x + 61}px 371px` }}>
                <rect x={x + 16} y={368} width={42} height={6} rx={3} fill="#dc2626" />
                <rect x={x + 64} y={368} width={42} height={6} rx={3} fill="#dc2626" />
              </g>
              <rect x={x + 54} y={380} width={14} height={32} rx={7} fill="url(#motor-red)" />
            </g>
          ))}
        </g>
        <rect className="part-shape" x={997} y={322} width={285} height={38} fill="url(#green-fill)" stroke="#ffffff" strokeWidth={2.5} />
        <rect x={997} y={322} width={285} height={38} fill="url(#fins)" className="pointer-events-none" />
        <Seams xs={[1013, 1265]} y={322} h={38} />
      </>
    ),
  },
  "feed-pump": {
    label: { zh: "工作流體泵", en: "Working-Fluid Pump", x: 918, y: 638 },
    render: () => <InlinePump x={918} y={543} />,
  },
};

/** Process pipes that are not selectable on their own. */
function ProcessPipes() {
  return (
    <g className="pointer-events-none">
      {/* ORC working fluid (behind the exchangers, as in the PDF) */}
      <Pipe d="M1034 360 V560 H795 V285" fluid="orc" />
      <Pipe d="M795 185 V140 H992" fluid="orc" />
      <Pipe d="M1034 172 V322" fluid="orc" />
      {/* steam path: separator → evaporator → steam preheater → NCG separator → buffer vessel */}
      <Pipe d="M392 215 H632" fluid="steam" />
      <Pipe d="M864 215 H965 V450 H864" fluid="steam" />
      <Pipe d="M712 482 V530" fluid="steam" />
      <Pipe d="M688 637 H628" fluid="steam" />
      {/* hot water path: separator → evaporator → brine preheater → buffer vessel */}
      <Pipe d="M392 355 H450 V250 H632" fluid="hot" />
      <Pipe d="M864 250 H925 V355 H864" fluid="hot" />
      <Pipe d="M669 355 H592 V594" fluid="hot" />
      {/* reinjection: buffer vessel → pump → well 3 */}
      <Pipe d="M472 637 H338" fluid="reinject" />
      {/* shaft turbine → generator */}
      <line x1={1085} y1={140} x2={1290} y2={140} stroke="#1f2937" strokeWidth={9} strokeLinecap="round" />
      <rect x={1100} y={116} width={18} height={48} rx={2} fill="url(#steel-v)" stroke="#334155" />
    </g>
  );
}

function Defs() {
  return (
    <defs>
      {/* background */}
      <radialGradient id="bg" cx="50%" cy="8%" r="85%">
        <stop offset="0" stopColor="#fafafa" />
        <stop offset="0.55" stopColor="#e7e7ea" />
        <stop offset="1" stopColor="#d4d4d8" />
      </radialGradient>
      <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
        <path d="M24 0 H0 V24" fill="none" stroke="#0f172a" strokeOpacity="0.045" strokeWidth="1" />
      </pattern>
      <filter id="noise" x="0" y="0" width="100%" height="100%">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" />
        <feColorMatrix type="saturate" values="0" />
        <feComponentTransfer>
          <feFuncA type="table" tableValues="0 0.5" />
        </feComponentTransfer>
      </filter>
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%">
        <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#0f172a" floodOpacity="0.22" />
      </filter>

      {/* metals */}
      <linearGradient id="steel-v" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#64748b" />
        <stop offset="0.3" stopColor="#cbd5e1" />
        <stop offset="0.55" stopColor="#94a3b8" />
        <stop offset="1" stopColor="#475569" />
      </linearGradient>
      <linearGradient id="steel-h" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#cbd5e1" />
        <stop offset="1" stopColor="#64748b" />
      </linearGradient>
      <linearGradient id="bronze" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#6b4a3c" />
        <stop offset="0.35" stopColor="#b08d7c" />
        <stop offset="1" stopColor="#5b3d31" />
      </linearGradient>
      <pattern id="brushed" width="6" height="3" patternUnits="userSpaceOnUse">
        <line x1="0" y1="1" x2="6" y2="1" stroke="#ffffff" strokeOpacity="0.18" />
      </pattern>
      {/* cylinder shading overlays (light from top-left) */}
      <linearGradient id="cyl-shade-h" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.45" />
        <stop offset="0.28" stopColor="#ffffff" stopOpacity="0.1" />
        <stop offset="0.7" stopColor="#0f172a" stopOpacity="0.05" />
        <stop offset="1" stopColor="#0f172a" stopOpacity="0.28" />
      </linearGradient>
      <linearGradient id="cyl-shade-v" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#0f172a" stopOpacity="0.18" />
        <stop offset="0.3" stopColor="#ffffff" stopOpacity="0.35" />
        <stop offset="0.6" stopColor="#ffffff" stopOpacity="0" />
        <stop offset="1" stopColor="#0f172a" stopOpacity="0.3" />
      </linearGradient>

      {/* vessel contents */}
      <linearGradient id="steam-fill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#fbe3a6" />
        <stop offset="1" stopColor="#ecc56f" />
      </linearGradient>
      <linearGradient id="water-brown" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#c98466" />
        <stop offset="1" stopColor="#9c5a42" />
      </linearGradient>
      <linearGradient id="gas-fill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#e2e8f0" />
        <stop offset="1" stopColor="#cbd5e1" />
      </linearGradient>
      <linearGradient id="water-blue" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#67d4f8" />
        <stop offset="1" stopColor="#1d8fd6" />
      </linearGradient>

      {/* exchangers */}
      <linearGradient id="evap-body" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#e3eaf1" />
        <stop offset="1" stopColor="#bccbd8" />
      </linearGradient>
      <linearGradient id="evap-ends" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#c6d3df" />
        <stop offset="1" stopColor="#9fb2c4" />
      </linearGradient>
      <linearGradient id="ph-body" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#dde4df" />
        <stop offset="1" stopColor="#bcc9c0" />
      </linearGradient>
      <linearGradient id="ph-ends" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#c3cfc7" />
        <stop offset="1" stopColor="#9fb0a5" />
      </linearGradient>

      {/* rotating machines */}
      <linearGradient id="turbine-fill" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#f4b6c6" />
        <stop offset="1" stopColor="#a9c4ea" />
      </linearGradient>
      <linearGradient id="blade" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#f1f5f9" />
        <stop offset="0.5" stopColor="#64748b" />
        <stop offset="1" stopColor="#cbd5e1" />
      </linearGradient>
      <radialGradient id="gen-fill" cx="40%" cy="30%" r="80%">
        <stop offset="0" stopColor="#f1f5f9" />
        <stop offset="0.6" stopColor="#a1a1aa" />
        <stop offset="1" stopColor="#52525b" />
      </radialGradient>
      <linearGradient id="slot" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#d4d4d8" />
        <stop offset="0.5" stopColor="#fafafa" />
        <stop offset="1" stopColor="#a1a1aa" />
      </linearGradient>

      {/* air condenser */}
      <linearGradient id="green-fill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#4ade80" />
        <stop offset="0.45" stopColor="#22a45a" />
        <stop offset="1" stopColor="#15803d" />
      </linearGradient>
      <pattern id="fins" width="5" height="38" patternUnits="userSpaceOnUse">
        <line x1="1" y1="0" x2="1" y2="38" stroke="#052e16" strokeOpacity="0.18" />
      </pattern>
      <linearGradient id="motor-red" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#991b1b" />
        <stop offset="0.4" stopColor="#ef4444" />
        <stop offset="1" stopColor="#7f1d1d" />
      </linearGradient>
    </defs>
  );
}

type Props = {
  selectedId: DiagramComponentId | null;
  onSelect: (id: DiagramComponentId) => void;
};

export default function InteractiveDiagram({ selectedId, onSelect }: Props) {
  function handleKeyDown(e: KeyboardEvent<SVGGElement>, id: DiagramComponentId) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(id);
    }
  }

  // Pipeline is drawn first (behind), the rest of the equipment on top.
  const order: DiagramComponentId[] = [
    "production-pipeline",
    ...DIAGRAM_COMPONENTS.map((c) => c.id).filter((id) => id !== "production-pipeline"),
  ];

  return (
    <svg
      viewBox={VIEWBOX}
      className="plant-diagram h-auto w-full min-w-[760px] select-none md:min-w-0"
      role="group"
      aria-label="Renze plant process diagram"
    >
      <Defs />

      {/* backdrop: soft studio light, blueprint grid, film grain */}
      <rect x={0} y={60} width={1334} height={690} fill="url(#bg)" />
      <rect x={0} y={60} width={1334} height={690} fill="url(#grid)" />
      <rect x={0} y={60} width={1334} height={690} filter="url(#noise)" opacity={0.18} className="pointer-events-none" />

      <ProcessPipes />

      {order.map((id) => {
        const c = DIAGRAM_COMPONENTS.find((d) => d.id === id)!;
        const shape = SHAPES[id];
        const selected = selectedId === id;
        return (
          <g
            key={id}
            role="button"
            tabIndex={0}
            aria-label={`${c.nameZh} ${c.name}`}
            aria-pressed={selected}
            data-selected={selected || undefined}
            className="diagram-part cursor-pointer"
            onClick={() => onSelect(id)}
            onKeyDown={(e) => handleKeyDown(e, id)}
          >
            <title>{`${c.nameZh} · ${c.name}`}</title>
            <g filter={id === "production-pipeline" ? undefined : "url(#shadow)"}>{shape.render()}</g>
            {shape.label && (
              <g className="label-halo">
                <text x={shape.label.x} y={shape.label.y} textAnchor="middle" className="part-label fill-slate-700 text-[19px] font-bold">
                  {shape.label.zh}
                </text>
                <text x={shape.label.x} y={shape.label.y + 18} textAnchor="middle" className="part-label-en fill-slate-500 text-[11.5px]">
                  {shape.label.en}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}
