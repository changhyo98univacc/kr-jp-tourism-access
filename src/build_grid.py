"""격자 접근성 표면.

도도부현 47덩어리로는 내부 편차가 보이지 않는다. 격자는 좌표만 있으면 계산되므로
접근성(공급)은 원하는 해상도로 낼 수 있다. 다만 방문(수요)은 도도부현이 최소 단위다
— 한국인 숙박은 국적별 분해가 도도부현까지만 공표된다. 그 비대칭이 이 파일의 전제다.
"""
from __future__ import annotations
import json, math, pathlib
import numpy as np, pandas as pd
from matplotlib.path import Path as MplPath

import build_data as B

OUT = B.OUT
STEP_KM = 10.0


def lattice(geo: dict, step_km: float):
    """일본 경계상자를 격자로 덮고, 육지 칸만 남기며 도도부현 코드를 붙인다."""
    rings, meta = [], []
    for ft in geo["features"]:
        code = int(ft["properties"]["id"])
        polys = ([ft["geometry"]["coordinates"]] if ft["geometry"]["type"] == "Polygon"
                 else ft["geometry"]["coordinates"])
        for p in polys:
            r = np.asarray(p[0], dtype=float)
            if len(r) >= 4:
                rings.append(r)
                meta.append(code)

    lo1 = min(r[:, 0].min() for r in rings); lo2 = max(r[:, 0].max() for r in rings)
    la1 = min(r[:, 1].min() for r in rings); la2 = max(r[:, 1].max() for r in rings)
    dlat = step_km / 111.0
    dlon = step_km / (111.0 * math.cos(math.radians((la1 + la2) / 2)))

    lons = np.arange(lo1, lo2 + dlon, dlon)
    lats = np.arange(la1, la2 + dlat, dlat)
    LON, LAT = np.meshgrid(lons, lats)
    pts = np.column_stack([LON.ravel(), LAT.ravel()])
    print(f"  경계상자 격자 {len(lons)}x{len(lats)} = {len(pts):,}칸 ({step_km:.0f}km)")

    pref = np.full(len(pts), -1, dtype=int)
    for r, code in zip(rings, meta):
        box = ((pts[:, 0] >= r[:, 0].min()) & (pts[:, 0] <= r[:, 0].max()) &
               (pts[:, 1] >= r[:, 1].min()) & (pts[:, 1] <= r[:, 1].max()) & (pref < 0))
        idx = np.flatnonzero(box)
        if not len(idx):
            continue
        inside = MplPath(r).contains_points(pts[idx])
        pref[idx[inside]] = code

    keep = pref >= 0
    cells = pd.DataFrame({"lon": pts[keep, 0], "lat": pts[keep, 1], "pref_code": pref[keep]})
    cells.insert(0, "cell_id", np.arange(len(cells)))
    print(f"  육지 칸 {len(cells):,}개 ({len(cells)/len(pts)*100:.1f}%)")
    return cells, dlon, dlat


def accessibility(cells: pd.DataFrame, routes: pd.DataFrame, ap: pd.DataFrame):
    """칸 × 월 최단 소요시간. 그 달 실제 운항한 노선만 후보로 쓴다."""
    arrs = sorted(routes["arr"].unique())
    alat = ap.loc[arrs, "lat"].to_numpy()[:, None]
    alon = ap.loc[arrs, "lon"].to_numpy()[:, None]
    # (공항 × 칸) 지상이동 분
    ground = B.gc_km(alat, alon, cells["lat"].to_numpy()[None, :],
                     cells["lon"].to_numpy()[None, :]) / B.GROUND_KMH * 60

    rt = routes.copy()
    rt["air_min"] = B.gc_km(rt["dlat"], rt["dlon"], rt["alat"], rt["alon"]) / B.CRUISE_KMH * 60 + B.TAXI_MIN
    out = []
    for month, g in rt.groupby("month"):
        best = g.loc[g.groupby("arr")["air_min"].idxmin()].set_index("arr")
        idx = [i for i, a in enumerate(arrs) if a in best.index]
        air = best.loc[[arrs[i] for i in idx], "air_min"].to_numpy()[:, None]
        total = B.OVERHEAD_MIN + air + ground[idx]        # (활성공항 × 칸)
        k = total.argmin(axis=0)
        out.append(pd.DataFrame({
            "cell_id": cells["cell_id"].to_numpy(), "month": month,
            "min_minutes": total.min(axis=0).round(1),
            "best_arr": [arrs[idx[i]] for i in k],
            "best_dep": best.loc[[arrs[idx[i]] for i in k], "dep"].to_numpy(),
        }))
        print(f"    {month:2d}월  활성공항 {len(idx)}개  "
              f"최소 {total.min():.0f}분 / 최대 {total.min(axis=0).max():.0f}분")
    return pd.concat(out, ignore_index=True)


def cell_geojson(cells: pd.DataFrame, dlon: float, dlat: float, path: pathlib.Path):
    hx, hy = dlon / 2, dlat / 2
    feats = []
    for cid, lon, lat in cells[["cell_id", "lon", "lat"]].itertuples(index=False):
        feats.append({"type": "Feature", "properties": {"cell_id": int(cid)},
                      "geometry": {"type": "Polygon", "coordinates": [[
                          [round(lon - hx, 4), round(lat - hy, 4)],
                          [round(lon + hx, 4), round(lat - hy, 4)],
                          [round(lon + hx, 4), round(lat + hy, 4)],
                          [round(lon - hx, 4), round(lat + hy, 4)],
                          [round(lon - hx, 4), round(lat - hy, 4)]]]}})
    json.dump({"type": "FeatureCollection", "features": feats},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return path.stat().st_size


def main():
    geo = json.load(open(B.RAW / "japan_pref.geojson", encoding="utf-8"))
    ap, routes = B.airports(), B.routes()
    routes = routes.merge(ap[["lat", "lon"]].rename(columns={"lat": "dlat", "lon": "dlon"}),
                          left_on="dep", right_index=True)
    routes = routes.merge(ap[["lat", "lon"]].rename(columns={"lat": "alat", "lon": "alon"}),
                          left_on="arr", right_index=True)

    cells, dlon, dlat = lattice(geo, STEP_KM)
    acc = accessibility(cells, routes, ap)

    cells.to_csv(OUT / "grid_cells.csv", index=False, encoding="utf-8")
    acc.to_csv(OUT / "grid_access.csv", index=False, encoding="utf-8")
    size = cell_geojson(cells, dlon, dlat, OUT / "grid_cells.geojson")
    for f in ("grid_cells.csv", "grid_access.csv", "grid_cells.geojson"):
        print(f"  {f:24s} {(OUT / f).stat().st_size/1_048_576:6.2f} MB")


if __name__ == "__main__":
    main()
