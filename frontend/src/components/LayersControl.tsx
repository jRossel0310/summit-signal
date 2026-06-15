import { useState } from "react";
import type { LayerStateMap } from "../layers/types";
import { BASEMAP_LAYERS, OVERLAY_LAYERS, COMING_SOON_LAYERS } from "../layers/registry";
import { activeBasemapId } from "../layers/layerState";
import Legend from "./Legend";

interface Props {
  layerState: LayerStateMap;
  onSelectBasemap: (id: string) => void;
  onToggle: (id: string, visible: boolean) => void;
  onOpacity: (id: string, opacity: number) => void;
}

export default function LayersControl({ layerState, onSelectBasemap, onToggle, onOpacity }: Props) {
  const [open, setOpen] = useState(false);
  const activeBase = activeBasemapId(layerState);

  return (
    <div className="layers-control">
      <button className="layers-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        ▤ Layers
      </button>
      {open && (
        <div className="layers-panel" role="group" aria-label="Map layers">
          <div className="layers-panel-head">
            <strong>Layers</strong>
            <button className="layers-close" aria-label="Close layers" onClick={() => setOpen(false)}>✕</button>
          </div>

          <div className="layers-group">
            <div className="layers-group-label">Basemap</div>
            {BASEMAP_LAYERS.map((l) => (
              <label key={l.id} className="layers-row">
                <input
                  type="radio"
                  name="basemap"
                  checked={activeBase === l.id}
                  onChange={() => onSelectBasemap(l.id)}
                />
                {l.label}
              </label>
            ))}
          </div>

          <div className="layers-group">
            <div className="layers-group-label">Overlays</div>
            {OVERLAY_LAYERS.map((l) => {
              const st = layerState[l.id];
              return (
                <div key={l.id} className="layers-row-block">
                  <label className="layers-row">
                    <input
                      type="checkbox"
                      checked={!!st?.visible}
                      onChange={(e) => onToggle(l.id, e.target.checked)}
                    />
                    {l.label}
                  </label>
                  {l.legend ? <Legend legend={l.legend} /> : null}
                  {l.supportsOpacity && st?.visible ? (
                    <div className="layers-opacity">
                      <span>opacity</span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={st.opacity}
                        onChange={(e) => onOpacity(l.id, Number(e.target.value))}
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="layers-group layers-group-disabled">
            <div className="layers-group-label">Coming soon</div>
            {COMING_SOON_LAYERS.map((l) => (
              <label key={l.id} className="layers-row" title={`Arrives in Phase ${l.comingSoonPhase}`}>
                <input type="checkbox" disabled />
                {l.label}
                <span className="layers-phase-badge">Phase {l.comingSoonPhase}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
