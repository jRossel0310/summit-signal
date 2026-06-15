import type { Legend as LegendType } from "../layers/types";

export default function Legend({ legend }: { legend: LegendType }) {
  if (!legend || legend.kind === "none" || !legend.items?.length) return null;
  return (
    <div className="legend">
      {legend.items.map((it) => (
        <span key={it.label} className="legend-item">
          <span className="legend-swatch" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
      {legend.note ? <span className="legend-note">{legend.note}</span> : null}
    </div>
  );
}
