import type { ConnectorStatus, Severity } from "../types";
import { ageLabel, fmtTime } from "../lib/api";

export function SeverityBadge({ severity }: { severity: Severity }) {
  const label =
    severity === "unknown" ? "Unknown / data gap" : severity.charAt(0).toUpperCase() + severity.slice(1);
  return <span className={`badge ${severity}`}>{label}</span>;
}

const CONN_LABEL: Record<ConnectorStatus, string> = {
  success: "Checked",
  partial: "Partial",
  failed: "Failed",
  skipped: "Skipped",
};

export function ConnStatus({ status }: { status: ConnectorStatus }) {
  const glyph = status === "success" ? "●" : status === "partial" ? "◐" : status === "failed" ? "✕" : "○";
  return (
    <span className={`conn-status ${status}`}>
      {glyph} {CONN_LABEL[status]}
    </span>
  );
}

export function statusBannerClass(status: string | null | undefined): string {
  switch (status) {
    case "Major concerns found":
      return "s-major";
    case "Some concerns found":
      return "s-some";
    case "No major concerns found":
      return "s-none";
    case "Source check failed":
      return "s-failed";
    default:
      return "s-incomplete";
  }
}

export function StatusBanner({ status, sub }: { status: string | null; sub?: string }) {
  return (
    <div className={`status-banner ${statusBannerClass(status)}`}>
      <div className="label">Overall concern status</div>
      <div className="value">{status || "Not yet checked"}</div>
      {sub && <div className="label" style={{ marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

export function Freshness({ retrievedAt, staleHours = 24 }: { retrievedAt: string | null; staleHours?: number }) {
  if (!retrievedAt) return <span className="freshness">retrieved: -</span>;
  const ageH = (Date.now() - new Date(retrievedAt).getTime()) / 3600000;
  const stale = ageH > staleHours;
  return (
    <span className={`freshness${stale ? " stale" : ""}`} title={fmtTime(retrievedAt)}>
      retrieved {ageLabel(retrievedAt)}
      {stale ? " - STALE" : ""}
    </span>
  );
}
