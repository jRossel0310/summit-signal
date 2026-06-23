interface Props {
  text: string;
}

// A small focusable ⓘ that reveals a themed tooltip on hover or keyboard focus.
// Pure CSS (see .info-tip / .info-tip-bubble in index.css) — no JS state.
export default function InfoTip({ text }: Props) {
  return (
    <span className="info-tip" tabIndex={0} role="img" aria-label={text}>
      <span aria-hidden="true">&#9432;</span>
      <span className="info-tip-bubble" role="tooltip">{text}</span>
    </span>
  );
}
