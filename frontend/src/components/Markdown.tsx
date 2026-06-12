// Minimal markdown renderer for the summarizer's constrained output:
// #/## headings, bullets, checklist "- [ ]", bold, italics-disclaimer line.
import { Fragment } from "react";

function inline(text: string, key: number) {
  // bold then links
  const parts: (string | JSX.Element)[] = [];
  let rest = text;
  let i = 0;
  const pattern = /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/;
  while (rest.length) {
    const m = rest.match(pattern);
    if (!m || m.index === undefined) { parts.push(rest); break; }
    if (m.index > 0) parts.push(rest.slice(0, m.index));
    if (m[1] !== undefined) parts.push(<strong key={`${key}-${i++}`}>{m[1]}</strong>);
    else parts.push(<a key={`${key}-${i++}`} href={m[3]} target="_blank" rel="noreferrer">{m[2]}</a>);
    rest = rest.slice(m.index + m[0].length);
  }
  return parts;
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: JSX.Element[] = [];
  let list: JSX.Element[] = [];
  let k = 0;

  const flushList = () => {
    if (list.length) { out.push(<ul key={`ul-${k++}`}>{list}</ul>); list = []; }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { flushList(); continue; }
    if (line.startsWith("## ")) { flushList(); out.push(<h2 key={k++}>{inline(line.slice(3), k)}</h2>); }
    else if (line.startsWith("# ")) { flushList(); out.push(<h1 key={k++}>{inline(line.slice(2), k)}</h1>); }
    else if (/^- \[ \]\s/.test(line)) { list.push(<li key={k++} className="checklist-item">{inline(line.replace(/^- \[ \]\s*/, ""), k)}</li>); }
    else if (line.startsWith("- ")) { list.push(<li key={k++}>{inline(line.slice(2), k)}</li>); }
    else if (line.startsWith("_") && line.endsWith("_")) {
      flushList();
      out.push(<em key={k++} className="disclaimer">{line.slice(1, -1)}</em>);
    } else { flushList(); out.push(<p key={k++}>{inline(line, k)}</p>); }
  }
  flushList();
  return <div className="summary-md"><Fragment>{out}</Fragment></div>;
}
