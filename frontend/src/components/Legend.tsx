import type { Legend as LegendType } from "../layers/types";
import { ASPECT_COLORS } from "../layers/terrainColors";

function AspectWheel() {
  const a = ASPECT_COLORS;
  const bg = `conic-gradient(${a.N} 0 45deg,${a.NE} 45deg 90deg,${a.E} 90deg 135deg,${a.SE} 135deg 180deg,${a.S} 180deg 225deg,${a.SW} 225deg 270deg,${a.W} 270deg 315deg,${a.NW} 315deg 360deg)`;
  return (
    <div className="legend">
      <span className="aspect-wheel" style={{ background: bg }} aria-label="aspect color wheel" />
      <span className="legend-note">N cool · S warm</span>
    </div>
  );
}

export default function Legend({ legend }: { legend: LegendType }) {
  if (!legend || legend.kind === "none") return null;
  if (legend.kind === "wheel") return <AspectWheel />;
  if (!legend.items?.length) return null;
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
