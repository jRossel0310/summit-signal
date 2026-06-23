"""Offline trail-network tracing for gap-filling route snapping. Given a leg's
two endpoints and nearby trail polylines (from trail_source), build a small local
graph and trace the shortest path along the trails between the endpoints.

Pure: no network, no DB. Never raises — returns None when it can't trace."""
from __future__ import annotations
import heapq

from .gpx_parser import _haversine_miles

_M_PER_DEG = 111_000.0  # ~meters per degree latitude (good enough locally)


def _node_key(lat: float, lon: float, step_deg: float) -> tuple:
    return (round(lat / step_deg), round(lon / step_deg))


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    return _haversine_miles(lat1, lon1, lat2, lon2) * 1609.344


def snap_leg(p1, p2, trail_lines, snap_radius_m: float = 200.0,
             merge_tol_m: float = 15.0):
    """p1, p2: (lat, lon). trail_lines: list of polylines [[lat, lon], ...].
    Returns [[lat, lon, None], ...] from p1 to p2 traced along trails, or None."""
    if not trail_lines:
        return None
    step = max(merge_tol_m, 1.0) / _M_PER_DEG
    coords: dict = {}   # key -> (lat, lon) representative
    adj: dict = {}      # key -> {neighbor_key: weight_miles}

    def add_node(lat, lon):
        k = _node_key(lat, lon, step)
        if k not in coords:
            coords[k] = (lat, lon)
            adj[k] = {}
        return k

    def add_edge(a, b):
        (la, lo) = coords[a]
        (lb, lob) = coords[b]
        w = _haversine_miles(la, lo, lb, lob)
        if b not in adj[a] or w < adj[a][b]:
            adj[a][b] = w
            adj[b][a] = w

    for line in trail_lines:
        prev = None
        for pt in line:
            if pt is None or len(pt) < 2 or pt[0] is None or pt[1] is None:
                continue
            k = add_node(pt[0], pt[1])
            if prev is not None and prev != k:
                add_edge(prev, k)
            prev = k

    if not coords:
        return None

    def nearest(lat, lon):
        best_k, best_d = None, None
        for k, (clat, clon) in coords.items():
            d = _dist_m(lat, lon, clat, clon)
            if best_d is None or d < best_d:
                best_k, best_d = k, d
        return best_k, best_d

    s_key, s_d = nearest(p1[0], p1[1])
    g_key, g_d = nearest(p2[0], p2[1])
    if s_key is None or g_key is None or s_d > snap_radius_m or g_d > snap_radius_m:
        return None

    path = _dijkstra(adj, s_key, g_key)
    if path is None:
        return None

    out = [[p1[0], p1[1], None]]
    for k in path:
        lat, lon = coords[k]
        if out[-1][0] != lat or out[-1][1] != lon:
            out.append([lat, lon, None])
    if out[-1][0] != p2[0] or out[-1][1] != p2[1]:
        out.append([p2[0], p2[1], None])
    return out


def _dijkstra(adj, start, goal):
    if start == goal:
        return [start]
    dist = {start: 0.0}
    prev: dict = {}
    pq = [(0.0, start)]
    visited = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, w in adj.get(u, {}).items():
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path
