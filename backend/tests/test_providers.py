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


from app.providers import stubs


def test_stub_is_coming_soon():
    out = stubs.SlopeAspectStub.fetch(ProviderContext(40.0, -105.0))
    assert out.status == "coming_soon"
    assert out.provider_id == "slope_aspect"
