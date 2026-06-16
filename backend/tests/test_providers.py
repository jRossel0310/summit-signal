"""Provider unit tests: result factories, each provider, registry, aggregator.
All offline — http_client is monkeypatched per module, exactly like
tests/test_connectors.py."""
from app.providers import base
from app.providers.base import ProviderContext


def test_result_factories_set_status():
    assert base.ok("x", "X", {"v": 1}).status == "ok"
    assert base.empty("x", "X", "none").status == "empty"
    nk = base.needs_key("x", "X", "FOO_KEY")
    assert nk.status == "needs_key" and "FOO_KEY" in nk.message
    assert base.error("x", "X", "boom").status == "error"
    assert base.coming_soon("x", "X", 2).status == "coming_soon"


from app.providers import elevation as elevation_mod


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self._p


class _ElevClient:
    """EPQS returns a value unless fail_epqs; Open-Meteo returns om_payload."""
    def __init__(self, epqs_payload=None, fail_epqs=False, om_payload=None):
        self.epqs_payload = epqs_payload
        self.fail_epqs = fail_epqs
        self.om_payload = om_payload
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        if "epqs" in url:
            if self.fail_epqs:
                raise RuntimeError("EPQS down")
            return _Resp(self.epqs_payload)
        return _Resp(self.om_payload or {"elevation": []})


def test_elevation_ok(monkeypatch):
    monkeypatch.setattr(elevation_mod, "http_client",
                        lambda: _ElevClient(epqs_payload={"value": 3186.0}))
    out = elevation_mod.ElevationProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["elevation_ft"] == round(3186.0 * 3.28084)
    assert "USGS" in out.source_name


def test_elevation_uses_fallback(monkeypatch):
    monkeypatch.setattr(elevation_mod, "http_client",
                        lambda: _ElevClient(fail_epqs=True, om_payload={"elevation": [1000.0]}))
    out = elevation_mod.ElevationProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert "Open-Meteo" in out.source_name


def test_elevation_never_raises(monkeypatch):
    class _Boom:
        def __enter__(self):
            raise RuntimeError("network gone")
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(elevation_mod, "http_client", lambda: _Boom())
    out = elevation_mod.ElevationProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "error"


from app.providers import placename as placename_mod


def test_placename_ok(monkeypatch):
    class _C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, url, params=None):
            return _Resp({"display_name": "Near Pingora, WY"})
    monkeypatch.setattr(placename_mod, "http_client", lambda: _C())
    out = placename_mod.PlaceNameProvider().fetch(ProviderContext(42.0, -109.0))
    assert out.status == "ok" and "Pingora" in out.data["name"]


def test_placename_failure_is_empty(monkeypatch):
    class _C:
        def __enter__(self):
            raise RuntimeError("down")
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(placename_mod, "http_client", lambda: _C())
    out = placename_mod.PlaceNameProvider().fetch(ProviderContext(42.0, -109.0))
    assert out.status == "empty"


from app.providers import registry


def test_select_includes_always_on_by_default():
    ids = [p.id for p in registry.select_providers(None)]
    assert "elevation" in ids and "placename" in ids


def test_select_includes_requested():
    ids = [p.id for p in registry.select_providers(["aqi"])]
    assert "aqi" in ids and "elevation" in ids


def test_unknown_id_ignored():
    ids = [p.id for p in registry.select_providers(["nope"])]
    assert "nope" not in ids and "elevation" in ids


from app.providers import aggregator
from app.providers.base import ok as _ok, coming_soon as _coming_soon


def test_point_context_hoists_placename_and_lists_sections(monkeypatch):
    aggregator.clear_cache()

    class _Place:
        id = "placename"; title = "Place"; requires_key = None; always_on = True
        def fetch(self, ctx):
            return _ok(self.id, self.title, {"name": "Near Pingora, WY"})

    class _Elev:
        id = "elevation"; title = "Elevation"; requires_key = None; always_on = True
        def fetch(self, ctx):
            return _ok(self.id, self.title, {"elevation_ft": 10450})

    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [_Place(), _Elev()])
    out = aggregator.point_context(40.0, -105.0)
    assert out["place_name"] == "Near Pingora, WY"
    ids = [s["layer_id"] for s in out["sections"]]
    assert ids == ["elevation"]   # placename hoisted to top level, not a section


def test_cache_prevents_refetch(monkeypatch):
    aggregator.clear_cache()

    class _Counter:
        id = "elevation"; title = "Elevation"; requires_key = None; always_on = True
        calls = 0
        def fetch(self, ctx):
            type(self).calls += 1
            return _ok(self.id, self.title, {"elevation_ft": 1000})

    counter = _Counter()
    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [counter])
    aggregator.point_context(40.0, -105.0)
    aggregator.point_context(40.0, -105.0)
    assert _Counter.calls == 1   # second call served from cache


def test_status_mapped_to_kebab_wire(monkeypatch):
    aggregator.clear_cache()

    class _W:
        id = "weather"; title = "Current weather"; requires_key = None; always_on = False
        def fetch(self, ctx):
            return _coming_soon(self.id, self.title, 3)

    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [_W()])
    out = aggregator.point_context(40.0, -105.0, ["weather"])
    assert out["sections"][0]["status"] == "coming-soon"


def test_aggregator_runs_providers_concurrently_in_order(monkeypatch):
    import time as _t
    from app.providers import aggregator as agg
    from app.providers.base import ok as _ok
    agg.clear_cache()

    class _Slow:
        def __init__(self, pid): self.id = pid; self.title = pid; self.always_on = True; self.requires_key = None
        def fetch(self, ctx):
            _t.sleep(0.2)
            return _ok(self.id, self.title, {"v": self.id})

    provs = [_Slow("a"), _Slow("b"), _Slow("c")]
    monkeypatch.setattr(agg, "select_providers", lambda ids: provs)
    start = _t.monotonic()
    out = agg.point_context(40.0, -105.0)
    elapsed = _t.monotonic() - start
    assert [s["layer_id"] for s in out["sections"]] == ["a", "b", "c"]   # order preserved
    assert elapsed < 0.5   # 3x0.2s concurrent, not 0.6s sequential


def test_error_results_use_short_ttl(monkeypatch):
    aggregator.clear_cache()
    clock = {"t": 1000.0}
    calls = {"n": 0}
    monkeypatch.setattr(aggregator, "_now", lambda: clock["t"])

    class _Err:
        id = "x"; title = "X"; requires_key = None; always_on = True
        def fetch(self, ctx):
            calls["n"] += 1
            return base.error(self.id, self.title, "boom")

    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [_Err()])
    aggregator.point_context(40.0, -105.0)         # fetch #1 (error -> short TTL)
    clock["t"] += 30
    aggregator.point_context(40.0, -105.0)         # within 60s error TTL -> served from cache
    assert calls["n"] == 1
    clock["t"] += 60                                # now past the 60s error TTL
    aggregator.point_context(40.0, -105.0)         # refetched
    assert calls["n"] == 2
