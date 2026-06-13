import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, API_BASE } from "./lib/api";
import type {
  AppSettings, CheckStatus, ConditionCheckDetail, SearchResult, Trip,
} from "./types";
import MapView, { type FireDetection, type LayerState } from "./components/MapView";
import SearchBar from "./components/SearchBar";
import ConditionDashboard from "./components/ConditionDashboard";
import TripDetail from "./components/TripDetail";
import SettingsView from "./components/SettingsView";
import AuthScreen from "./components/AuthScreen";
import PlanPanel from "./components/PlanPanel";
import BottomSheet, { type SheetSnap } from "./components/BottomSheet";
import { useAuth } from "./lib/auth";
import { useIsPhone } from "./lib/useIsPhone";

type View = "dashboard" | "detail" | "settings" | "auth";

const Logo = () => (
  <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
    <path d="M2 26 L12 8 L17 17 L21 11 L30 26 Z" fill="#d84a1b" />
    <path d="M2 26 L12 8 L17 17 L21 11 L30 26" fill="none" stroke="#fbfaf6" strokeWidth="0" />
    <circle cx="21" cy="6" r="2.4" fill="#fbfaf6" />
  </svg>
);

// Concern status -> dot color, used on the mobile Conditions tab so risk is
// visible without opening the sheet.
function concernColor(status: string | null | undefined): string {
  switch (status) {
    case "Major concerns found": return "var(--accent)";
    case "Some concerns found": return "var(--amber)";
    case "No major concerns found": return "var(--teal)";
    case "Source check failed": return "var(--red)";
    case "Data incomplete": return "var(--gray)";
    default: return "var(--line-strong)";
  }
}

function LoggedOutConditions({ onLogin }: { onLogin: () => void }) {
  return (
    <div className="section">
      <h2 className="section-title">Condition dashboard</h2>
      <div className="empty-note">Log in to run condition checks and see source results for your trips.</div>
      <button className="btn primary" style={{ marginTop: 8 }} onClick={onLogin}>Log in / Sign up</button>
    </div>
  );
}

function SheetPeek({
  loggedIn, trip, check, running, liveStatus, onRunCheck, onLogin,
}: {
  loggedIn: boolean;
  trip: Trip | null;
  check: ConditionCheckDetail | null;
  running: boolean;
  liveStatus: CheckStatus | null;
  onRunCheck: () => void;
  onLogin: () => void;
}) {
  if (!loggedIn) {
    return (
      <div className="peek-empty">
        <div className="peek-title">Browse the map</div>
        <div className="peek-sub">Log in to save trips and run condition checks.</div>
        <button className="btn primary small peek-run" onClick={onLogin}>Log in / Sign up</button>
      </div>
    );
  }
  if (!trip) {
    return (
      <div className="peek-empty">
        <div className="peek-title">No trip selected</div>
        <div className="peek-sub">Search or tap the map, then save a trip in the Plan tab.</div>
      </div>
    );
  }
  const status = running ? "Check in progress" : (check?.overall_concern_status ?? trip.latest_concern_status);
  const dotColor = running ? "var(--accent)" : concernColor(check?.overall_concern_status ?? trip.latest_concern_status);
  return (
    <div className="peek">
      <div className="peek-trip">{trip.name}</div>
      <div className="peek-risk">
        <span className="peek-dot" style={{ background: dotColor }} />
        <span className="peek-status">{status ?? "Not yet checked"}</span>
      </div>
      {running && liveStatus ? (
        <div className="peek-progress">{liveStatus.connectors_completed}/{liveStatus.connectors_total} sources checked…</div>
      ) : (
        <button className="btn primary peek-run" onClick={onRunCheck} disabled={running}>Run condition check</button>
      )}
    </div>
  );
}

export default function App() {
  const { user, ready, logout } = useAuth();
  const [view, setView] = useState<View>("dashboard");
  const isPhone = useIsPhone();
  const [sheetSnap, setSheetSnap] = useState<SheetSnap>("peek");
  const [mobileTab, setMobileTab] = useState<"conditions" | "plan">("plan");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<Trip | null>(null);
  const [detailTrip, setDetailTrip] = useState<Trip | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<{ lat: number; lon: number } | null>(null);
  const [pointName, setPointName] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<{ lat: number; lon: number; zoom?: number } | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);

  const [check, setCheck] = useState<ConditionCheckDetail | null>(null);
  const [liveStatus, setLiveStatus] = useState<CheckStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [loadingCheck, setLoadingCheck] = useState(false);
  const [dashError, setDashError] = useState<string | null>(null);
  const [regenBusy, setRegenBusy] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const pollRef = useRef<number | null>(null);

  const [layers, setLayers] = useState<LayerState>({
    basemap: "topo",
    selectedPoint: true,
    gpxRoute: true,
    fires: true,
    perimeters: true,
    savedTrips: true,
  });

  // ---- boot ----
  useEffect(() => {
    api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false));
    const iv = window.setInterval(
      () => api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false)),
      20000,
    );
    return () => window.clearInterval(iv);
  }, []);

  // ---- load per-user data when logged in ----
  useEffect(() => {
    if (!user) {
      setTrips([]); setSelectedTrip(null); setCheck(null);
      setView((v) => (v === "settings" || v === "detail" ? "dashboard" : v));
      return;
    }
    api.listTrips().then(setTrips).catch(() => {});
    api.getSettings().then(setSettings).catch(() => {});
  }, [user]);

  // bounce away from the auth view once logged in
  useEffect(() => {
    if (user && view === "auth") setView("dashboard");
  }, [user, view]);

  const refreshTrips = useCallback(async () => {
    try {
      const list = await api.listTrips();
      setTrips(list);
      if (selectedTrip) {
        const updated = list.find((t) => t.id === selectedTrip.id);
        if (updated) setSelectedTrip(updated);
      }
    } catch { /* keep old list */ }
  }, [selectedTrip]);

  // ---- map-extracted data for layers ----
  const fireDetections: FireDetection[] = useMemo(() => {
    const r = check?.connector_results.find((c) => c.connector_name === "nasa_firms");
    const dets = (r?.normalized as any)?.detections;
    return Array.isArray(dets) ? dets : [];
  }, [check]);

  const perimeterGeojson = useMemo(() => {
    const r = check?.connector_results.find((c) => c.connector_name === "nifc_wfigs");
    const fc = (r?.normalized as any)?.geojson;
    return fc && fc.type === "FeatureCollection" ? (fc as GeoJSON.FeatureCollection) : null;
  }, [check]);

  const gpxPoints = useMemo(() => selectedTrip?.gpx_route?.points || null, [selectedTrip]);

  // ---- load latest check when trip selected ----
  async function loadLatestCheck(trip: Trip) {
    stopPolling();
    setRunning(false);
    setLiveStatus(null);
    setCheck(null);
    setDashError(null);
    setLoadingCheck(true);
    try {
      const list = await api.listChecks(trip.id);
      const latest = list.find((c) => c.status === "complete");
      const runningOne = list.find((c) => c.status === "running");
      if (runningOne) {
        beginPolling(runningOne.id, trip);
      }
      if (latest) setCheck(await api.getCheck(latest.id));
    } catch (e) {
      setDashError((e as Error).message);
    } finally {
      setLoadingCheck(false);
    }
  }

  function selectTrip(trip: Trip) {
    setSelectedTrip(trip);
    setSelectedPoint({ lat: trip.latitude, lon: trip.longitude });
    setPointName(trip.location_name);
    setFlyTo({ lat: trip.latitude, lon: trip.longitude, zoom: 10 });
    setMobileTab("conditions");           // surface conditions on phone
    setSheetSnap((s) => (s === "peek" ? "half" : s));
    loadLatestCheck(trip);
  }

  // ---- run condition check + polling ----
  function stopPolling() {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function beginPolling(checkId: number, _trip: Trip) {
    setRunning(true);
    setLiveStatus(null);
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const st = await api.getCheckStatus(checkId);
        setLiveStatus(st);
        if (st.status !== "running") {
          stopPolling();
          setRunning(false);
          setCheck(await api.getCheck(checkId));
          refreshTrips();
          if (st.status === "failed") setDashError("Condition check failed. See connector results for details.");
        }
      } catch (e) {
        stopPolling();
        setRunning(false);
        setDashError((e as Error).message);
      }
    }, 1200);
  }
  useEffect(() => () => stopPolling(), []);

  async function runCheck() {
    if (!selectedTrip) return;
    setDashError(null);
    try {
      const c = await api.runConditionCheck(selectedTrip.id);
      beginPolling(c.id, selectedTrip);
    } catch (e) {
      setDashError((e as Error).message);
    }
  }

  async function regenerateSummary() {
    if (!check) return;
    setRegenBusy(true);
    try {
      await api.generateSummary(check.id);
      setCheck(await api.getCheck(check.id));
    } catch (e) {
      setDashError((e as Error).message);
    } finally {
      setRegenBusy(false);
    }
  }

  async function runAll() {
    setRunningAll(true);
    try {
      await api.runAllSavedTrips();
      setTimeout(refreshTrips, 4000);
      setTimeout(refreshTrips, 15000);
    } catch (e) {
      setDashError((e as Error).message);
    } finally {
      setRunningAll(false);
    }
  }

  function onSearchResult(r: SearchResult) {
    setSelectedPoint({ lat: r.latitude, lon: r.longitude });
    setPointName(r.display_name);
    setFlyTo({ lat: r.latitude, lon: r.longitude, zoom: 11 });
  }

  function onMapSelect(lat: number, lon: number) {
    setSelectedPoint({ lat, lon });
    setPointName(null);
  }

  function onTripCreated(trip: Trip) {
    setTrips((prev) => [trip, ...prev]);
    selectTrip(trip);
  }

  // ---- render ----
  if (!ready) return null;
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Logo />
          <div>
            <div className="brand-name">SummitSignal</div>
            <div className="brand-sub">trip condition dashboard · multi-user</div>
          </div>
        </div>
        <div className="backend-dot" title={backendOk ? "backend connected" : "backend unreachable"}>
          <span className={`dot ${backendOk === null ? "" : backendOk ? "ok" : "bad"}`} />
          <span className="backend-host">{backendOk === false ? "backend offline" : new URL(API_BASE).host}</span>
        </div>
        <nav className="topbar-nav">
          <button
            className={`${view === "dashboard" ? "active hide-on-mobile" : ""}`}
            onClick={() => setView("dashboard")}
          >
            {view === "dashboard" ? "Map" : "← Map"}
          </button>
          {user && <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>Settings</button>}
          {user
            ? <button onClick={() => { logout(); setView("dashboard"); }}>Log out<span className="nav-email"> ({user.email})</span></button>
            : <button onClick={() => setView("auth")}>Log in</button>}
        </nav>
      </header>

      {backendOk === false && (
        <div className="error-note" style={{ margin: 0, borderRadius: 0 }}>
          Backend unreachable - start it with: <code>cd backend && uvicorn app.main:app --reload --port 8000</code>
        </div>
      )}

      {view === "auth" && !user && (
        <div style={{ flex: 1, minHeight: 0 }}>
          <AuthScreen />
        </div>
      )}

      {view === "settings" && user && (
        <div style={{ flex: 1, minHeight: 0 }}>
          <SettingsView onSaved={setSettings} />
        </div>
      )}

      {view === "detail" && detailTrip && (
        <div style={{ flex: 1, minHeight: 0 }}>
          <TripDetail
            trip={detailTrip}
            staleHours={settings?.stale_hours ?? 24}
            onBack={() => { setView("dashboard"); refreshTrips(); }}
            onTripUpdated={(t) => {
              setDetailTrip(t);
              setTrips((prev) => prev.map((x) => (x.id === t.id ? t : x)));
              setSelectedTrip((prev) => (prev && prev.id === t.id ? t : prev));
            }}
            onTripDeleted={(id) => {
              setTrips((prev) => prev.filter((x) => x.id !== id));
              if (selectedTrip?.id === id) {
                setSelectedTrip(null);
                setCheck(null);
                setSelectedPoint(null);
                setPointName(null);
              }
              setView("dashboard");
            }}
          />
        </div>
      )}

      {view === "dashboard" && (
        <div className="dashboard">
          {!isPhone && (
            <aside className="panel-left contour-bg">
              <PlanPanel
                loggedIn={!!user}
                selectedPoint={selectedPoint}
                pointName={pointName}
                trips={trips}
                selectedTripId={selectedTrip?.id ?? null}
                layers={layers}
                runningAll={runningAll}
                onTripCreated={onTripCreated}
                onSelectTrip={selectTrip}
                onOpenDetail={(t) => { setDetailTrip(t); setView("detail"); }}
                onRunAll={runAll}
                onLayersChange={setLayers}
                onLoginClick={() => setView("auth")}
              />
            </aside>
          )}

          <main className="panel-center">
            <MapView
              layers={layers}
              trips={trips}
              selectedTripId={selectedTrip?.id ?? null}
              selectedPoint={selectedPoint}
              flyTo={flyTo}
              gpxPoints={gpxPoints}
              fireDetections={fireDetections}
              perimeterGeojson={perimeterGeojson}
              onSelectPoint={onMapSelect}
              onSelectTrip={(id) => { const t = trips.find((x) => x.id === id); if (t) selectTrip(t); }}
            />
            <div className="map-overlay-tl">
              <SearchBar onResult={onSearchResult} />
            </div>
          </main>

          {!isPhone && (
            <aside className="panel-right">
              {user ? (
                <ConditionDashboard
                  trip={selectedTrip}
                  check={check}
                  liveStatus={liveStatus}
                  running={running}
                  loadingCheck={loadingCheck}
                  error={dashError}
                  staleHours={settings?.stale_hours ?? 24}
                  onRunCheck={runCheck}
                  onRegenerateSummary={regenerateSummary}
                  regenBusy={regenBusy}
                />
              ) : (
                <LoggedOutConditions onLogin={() => setView("auth")} />
              )}
            </aside>
          )}

          {isPhone && (
            <BottomSheet
              snap={sheetSnap}
              onSnapChange={setSheetSnap}
              peek={
                <SheetPeek
                  loggedIn={!!user}
                  trip={selectedTrip}
                  check={check}
                  running={running}
                  liveStatus={liveStatus}
                  onRunCheck={runCheck}
                  onLogin={() => setView("auth")}
                />
              }
            >
              <div className="sheet-segmented" role="tablist" aria-label="Sheet content">
                <button
                  type="button" role="tab" aria-selected={mobileTab === "conditions"}
                  className={mobileTab === "conditions" ? "active" : ""}
                  onClick={() => { setMobileTab("conditions"); setSheetSnap((s) => (s === "peek" ? "half" : s)); }}
                >
                  Conditions
                </button>
                <button
                  type="button" role="tab" aria-selected={mobileTab === "plan"}
                  className={mobileTab === "plan" ? "active" : ""}
                  onClick={() => { setMobileTab("plan"); setSheetSnap((s) => (s === "peek" ? "half" : s)); }}
                >
                  Plan
                </button>
              </div>
              <div className="sheet-tabpanel" role="tabpanel">
                {mobileTab === "conditions" ? (
                  user ? (
                    <ConditionDashboard
                      trip={selectedTrip}
                      check={check}
                      liveStatus={liveStatus}
                      running={running}
                      loadingCheck={loadingCheck}
                      error={dashError}
                      staleHours={settings?.stale_hours ?? 24}
                      onRunCheck={runCheck}
                      onRegenerateSummary={regenerateSummary}
                      regenBusy={regenBusy}
                    />
                  ) : (
                    <LoggedOutConditions onLogin={() => setView("auth")} />
                  )
                ) : (
                  <PlanPanel
                    loggedIn={!!user}
                    selectedPoint={selectedPoint}
                    pointName={pointName}
                    trips={trips}
                    selectedTripId={selectedTrip?.id ?? null}
                    layers={layers}
                    runningAll={runningAll}
                    onTripCreated={onTripCreated}
                    onSelectTrip={selectTrip}
                    onOpenDetail={(t) => { setDetailTrip(t); setView("detail"); }}
                    onRunAll={runAll}
                    onLayersChange={setLayers}
                    onLoginClick={() => setView("auth")}
                  />
                )}
              </div>
            </BottomSheet>
          )}
        </div>
      )}
    </div>
  );
}
