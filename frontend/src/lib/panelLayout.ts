// Pure helpers for the collapsible dashboard panels: the wrapper class names and
// localStorage persistence. Storage access is guarded so private mode / disabled
// storage degrades to "not collapsed" instead of throwing.

const KEYS = {
  left: "summitsignal_panel_left",
  right: "summitsignal_panel_right",
} as const;

export function dashboardClasses(leftCollapsed: boolean, rightCollapsed: boolean): string {
  let cls = "dashboard";
  if (leftCollapsed) cls += " is-left-collapsed";
  if (rightCollapsed) cls += " is-right-collapsed";
  return cls;
}

export function readPanelCollapsed(side: "left" | "right"): boolean {
  try {
    return localStorage.getItem(KEYS[side]) === "1";
  } catch {
    return false;
  }
}

export function writePanelCollapsed(side: "left" | "right", value: boolean): void {
  try {
    localStorage.setItem(KEYS[side], value ? "1" : "0");
  } catch {
    /* storage unavailable — ignore */
  }
}
