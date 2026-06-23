import { useEffect, useState } from "react";
import { readPanelCollapsed, writePanelCollapsed } from "../lib/panelLayout";

export interface PanelCollapseState {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  toggleLeft: () => void;
  toggleRight: () => void;
}

export function usePanelCollapse(): PanelCollapseState {
  const [leftCollapsed, setLeft] = useState(() => readPanelCollapsed("left"));
  const [rightCollapsed, setRight] = useState(() => readPanelCollapsed("right"));

  useEffect(() => { writePanelCollapsed("left", leftCollapsed); }, [leftCollapsed]);
  useEffect(() => { writePanelCollapsed("right", rightCollapsed); }, [rightCollapsed]);

  return {
    leftCollapsed,
    rightCollapsed,
    toggleLeft: () => setLeft((v) => !v),
    toggleRight: () => setRight((v) => !v),
  };
}
