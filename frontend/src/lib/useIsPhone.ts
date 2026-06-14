import { useEffect, useState } from "react";

// True when the viewport is phone-width (<=699px). Drives the bottom-sheet vs
// side-panel render split without remounting the (expensive) MapLibre map.
const QUERY = "(max-width: 699px)";

export function useIsPhone(): boolean {
  const [isPhone, setIsPhone] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia(QUERY).matches,
  );

  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setIsPhone(e.matches);
    mq.addEventListener("change", onChange);
    setIsPhone(mq.matches); // sync in case it changed before the listener attached
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return isPhone;
}
