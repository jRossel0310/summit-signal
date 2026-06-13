import { useLayoutEffect, useRef, type PointerEvent, type ReactNode } from "react";

export type SheetSnap = "peek" | "half" | "full";
const ORDER: SheetSnap[] = ["peek", "half", "full"];
const TAP_THRESHOLD_PX = 5;

interface Props {
  snap: SheetSnap;
  onSnapChange: (s: SheetSnap) => void;
  peek: ReactNode;     // always-visible header (trip + risk + action)
  children: ReactNode; // expanded content (segmented control + active panel)
  ariaLabel?: string;
}

// Read the rendered translateY (px) from the computed transform matrix. Works
// whether the value came from the data-snap CSS rule (%) or an inline px drag.
function getTranslateY(el: HTMLElement): number {
  const t = getComputedStyle(el).transform;
  if (!t || t === "none") return 0;
  const m3 = t.match(/matrix3d\((.+)\)/);
  if (m3) return parseFloat(m3[1].split(",")[13]);
  const m = t.match(/matrix\((.+)\)/);
  if (m) return parseFloat(m[1].split(",")[5]);
  return 0;
}

function peekHeight(el: HTMLElement): number {
  const grip = el.querySelector<HTMLElement>(".sheet-grip");
  const peek = el.querySelector<HTMLElement>(".sheet-peek");
  return (grip?.offsetHeight ?? 0) + (peek?.offsetHeight ?? 0) || 156;
}

export default function BottomSheet({ snap, onSnapChange, peek, children, ariaLabel = "Trip panel" }: Props) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ startY: number; start: number; max: number; sheetH: number; moved: boolean } | null>(null);

  // Keep the CSS peek height in sync with the actual grip + peek content so the
  // peek resting position never clips the risk banner or leaks the body.
  useLayoutEffect(() => {
    const el = sheetRef.current;
    if (!el) return;
    el.style.setProperty("--sheet-peek", `${peekHeight(el)}px`);
  });

  function onPointerDown(e: PointerEvent) {
    const el = sheetRef.current;
    if (!el) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    const sheetH = el.offsetHeight;
    drag.current = {
      startY: e.clientY,
      start: getTranslateY(el),
      max: sheetH - peekHeight(el),
      sheetH,
      moved: false,
    };
    el.dataset.dragging = "true";
  }

  function onPointerMove(e: PointerEvent) {
    const el = sheetRef.current;
    const d = drag.current;
    if (!el || !d) return;
    const dy = e.clientY - d.startY;
    if (Math.abs(dy) > TAP_THRESHOLD_PX) d.moved = true;
    const next = Math.min(Math.max(d.start + dy, 0), d.max);
    el.style.setProperty("--sheet-translate", `${next}px`);
  }

  function onPointerUp() {
    const el = sheetRef.current;
    const d = drag.current;
    if (!el || !d) return;
    el.dataset.dragging = "false";
    drag.current = null;

    if (!d.moved) {
      // Treat as a tap on the grip: cycle upward.
      const i = ORDER.indexOf(snap);
      el.style.removeProperty("--sheet-translate");
      onSnapChange(ORDER[Math.min(i + 1, ORDER.length - 1)]);
      return;
    }

    const current = getTranslateY(el);
    const targets: Record<SheetSnap, number> = { full: 0, half: d.sheetH * 0.45, peek: d.max };
    let best: SheetSnap = "peek";
    let bestDist = Infinity;
    (Object.keys(targets) as SheetSnap[]).forEach((k) => {
      const dist = Math.abs(targets[k] - current);
      if (dist < bestDist) { bestDist = dist; best = k; }
    });
    el.style.removeProperty("--sheet-translate"); // let the data-snap CSS animate to rest
    onSnapChange(best);
  }

  return (
    <div ref={sheetRef} className="bottom-sheet" data-snap={snap} role="dialog" aria-label={ariaLabel} aria-modal="false">
      <button
        type="button"
        className="sheet-grip"
        aria-label={snap === "full" ? "Collapse panel" : "Expand panel"}
        aria-expanded={snap !== "peek"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="grip-bar" />
      </button>
      <div className="sheet-peek">{peek}</div>
      <div className="sheet-body">{children}</div>
    </div>
  );
}
