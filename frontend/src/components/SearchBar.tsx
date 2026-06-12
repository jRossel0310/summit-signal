import { useRef, useState } from "react";
import { api } from "../lib/api";
import type { SearchResult } from "../types";

interface Props {
  onResult: (r: SearchResult) => void;
}

export default function SearchBar({ onResult }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  async function runSearch() {
    const q = query.trim();
    if (!q) return;
    const mySeq = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const { results } = await api.searchLocation(q);
      if (seq.current !== mySeq) return;
      setResults(results);
      if (results.length === 0) setError("No matches found. Try a different name or paste coordinates (lat, lon).");
    } catch (e) {
      if (seq.current === mySeq) setError((e as Error).message);
    } finally {
      if (seq.current === mySeq) setLoading(false);
    }
  }

  return (
    <div className="search-box">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
        placeholder={loading ? "Searching…" : "Search mountain, trailhead, park, or \"lat, lon\"…"}
        aria-label="Search location"
      />
      {error && <div className="error-note" style={{ marginTop: 6 }}>{error}</div>}
      {results.length > 0 && (
        <div className="search-results" style={{ marginTop: 6 }}>
          {results.map((r, i) => (
            <div
              key={i}
              className="res"
              onClick={() => { onResult(r); setResults([]); setQuery(""); }}
            >
              <div>{r.display_name}</div>
              <div className="kind">
                {r.kind || "place"} · {r.latitude.toFixed(4)}, {r.longitude.toFixed(4)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
