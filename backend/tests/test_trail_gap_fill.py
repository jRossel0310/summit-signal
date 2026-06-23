"""Trail gap-fill: offline tracer, ArcGIS trail fetch (mocked), and per-segment
snap orchestration. No live network."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "trailgap.db"))

import pytest  # noqa: E402
from app.services import trail_snap  # noqa: E402


# A trail running roughly west->east along latitude 46.10, every ~0.01 deg lon.
STRAIGHT_TRAIL = [[[46.10, -121.10], [46.10, -121.09], [46.10, -121.08],
                   [46.10, -121.07], [46.10, -121.06], [46.10, -121.05]]]


def test_snap_leg_traces_along_single_trail():
    p1 = (46.1001, -121.0995)   # ~near the west end
    p2 = (46.0998, -121.0505)   # ~near the east end
    traced = trail_snap.snap_leg(p1, p2, STRAIGHT_TRAIL)
    assert traced is not None
    assert traced[0] == [p1[0], p1[1], None]
    assert traced[-1] == [p2[0], p2[1], None]
    assert len(traced) >= 4          # endpoints + interior trail vertices
    assert all(len(pt) == 3 and pt[2] is None for pt in traced)


def test_snap_leg_connects_two_trails_sharing_an_endpoint():
    # Two segments meeting at [46.10, -121.05] (within merge tolerance).
    line_a = [[46.10, -121.10], [46.10, -121.05]]
    line_b = [[46.10, -121.05], [46.10, -121.00]]
    traced = trail_snap.snap_leg((46.10, -121.099), (46.10, -121.001), [line_a, line_b])
    assert traced is not None
    assert traced[-1] == [46.10, -121.001, None]


def test_snap_leg_returns_none_when_endpoint_too_far():
    # p1 is ~1.5 km north of the trail -> beyond the 200 m snap radius.
    traced = trail_snap.snap_leg((46.115, -121.10), (46.10, -121.05), STRAIGHT_TRAIL)
    assert traced is None


def test_snap_leg_returns_none_when_graph_disconnected():
    # Two short trail segments ~3.8 km apart. p1 snaps to the first segment and
    # p2 to the second (both well within 200 m), but the two segments are not
    # connected, so no path exists -> exercises the Dijkstra no-path branch.
    seg_near_p1 = [[46.10, -121.10], [46.10, -121.099]]
    seg_near_p2 = [[46.10, -121.05], [46.10, -121.049]]
    traced = trail_snap.snap_leg((46.10, -121.0995), (46.10, -121.0495),
                                 [seg_near_p1, seg_near_p2])
    assert traced is None


def test_snap_leg_returns_none_on_empty():
    assert trail_snap.snap_leg((46.10, -121.10), (46.10, -121.05), []) is None


from app.services import trail_source  # noqa: E402


def _fake_get_client(payload, status=200):
    class FakeResp:
        status_code = status
        def json(self):
            return payload
    class FakeClient:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, *a, **k):
            return FakeResp()
    return FakeClient


def test_fetch_trail_lines_parses_linestring_and_multiline(monkeypatch):
    payload = {"type": "FeatureCollection", "features": [
        {"geometry": {"type": "LineString",
                      "coordinates": [[-121.10, 46.10], [-121.09, 46.10]]}},
        {"geometry": {"type": "MultiLineString",
                      "coordinates": [[[-121.08, 46.10], [-121.07, 46.10]],
                                      [[-121.06, 46.11], [-121.05, 46.11]]]}},
    ]}
    monkeypatch.setattr(trail_source.httpx, "Client", _fake_get_client(payload))
    lines = trail_source.fetch_trail_lines((-121.2, 46.0, -121.0, 46.2),
                                           urls=["http://example/query"])
    assert len(lines) == 3
    # [lon, lat] in source -> [lat, lon] out
    assert lines[0][0] == [46.10, -121.10]


def test_fetch_trail_lines_empty_on_non_200(monkeypatch):
    monkeypatch.setattr(trail_source.httpx, "Client", _fake_get_client({}, status=500))
    assert trail_source.fetch_trail_lines((-121.2, 46.0, -121.0, 46.2),
                                          urls=["http://example/query"]) == []


def test_fetch_trail_lines_empty_on_exception(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            raise RuntimeError("network down")
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(trail_source.httpx, "Client", Boom)
    assert trail_source.fetch_trail_lines((-121.2, 46.0, -121.0, 46.2),
                                          urls=["http://example/query"]) == []
