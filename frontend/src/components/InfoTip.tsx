import { useRef, useState } from "react";

interface Props {
  text: string;
}

// A small focusable ⓘ that reveals a themed tooltip on hover or keyboard focus.
// The bubble is rendered with position: fixed at the icon's viewport coords so it
// escapes the Layers panel's `overflow:auto` clip (an absolutely-positioned
// descendant would be cut off wherever it extends past the scrolling panel).
export default function InfoTip({ text }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  function show() {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + 4, left: r.right });
  }
  function hide() {
    setPos(null);
  }

  return (
    <span
      ref={ref}
      className="info-tip"
      tabIndex={0}
      role="img"
      aria-label={text}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span aria-hidden="true">&#9432;</span>
      {pos && (
        <span className="info-tip-bubble" role="tooltip" style={{ top: pos.top, left: pos.left }}>
          {text}
        </span>
      )}
    </span>
  );
}
