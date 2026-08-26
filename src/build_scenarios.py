"""출발공항별 접근성 — "김해가 없다면?" 같은 반사실 비교를 위한 층.

앱에서 출발공항을 골라도 무거운 계산이 생기지 않도록, 출발공항 **하나씩** 잡았을 때의
최단 소요시간을 미리 구해 넓은 표로 저장한다. 앱은 고른 열들만 골라 행별 최소값을
취하면 되므로 조회에 가깝다 (부분집합 15가지를 다 저장하는 것보다 훨씬 작다).

부산물로 공항 소재지(도도부현)도 낸다. 발표에서 "공항 없는 현은 어떻게 계산했나"에
답하려면 어느 공항이 어느 현에 있는지가 필요하다.
"""
from __future__ import annotations
import json, pathlib
import numpy as np, pandas as pd
from matplotlib.path import Path as MplPath

import build_data as B

OUT = B.OUT
DEPS = ["ICN", "GMP", "PUS", "CJU"]


def airport_prefecture(ap: pd.DataFrame, jp: list[str], geo: dict) -> pd.DataFrame:
    """공항 좌표가 어느 도도부현 폴리곤 안인지. 해상·매립 공항은 최근접 경계로 보정."""
    pts = ap.loc[jp, ["lon", "lat"]].to_numpy()
    assign = np.full(len(jp), -1)
    for ft in geo["features"]:
        code = int(ft["properties"]["id"])
        polys = ([ft["geometry"]["coordinates"]] if ft["geometry"]["type"] == "Polygon"
                 else ft["geometry"]["coordinates"])
        for p in polys:
            r = np.asarray(p[0], float)
            if len(r) < 4:
                continue
            hit = MplPath(r).contains_points(pts)
            assign[hit & (assign < 0)] = code
    for i in np.flatnonzero(assign < 0):
        best, bd = -1, np.inf
        for ft in geo["features"]:
            polys = ([ft["geometry"]["coordinates"]] if ft["geometry"]["type"] == "Polygon"
                     else ft["geometry"]["coordinates"])
            for p in polys:
                r = np.asarray(p[0], float)
                d = float(np.min(B.gc_km(r[:, 1], r[:, 0], pts[i, 1], pts[i, 0])))
                if d < bd:
                    bd, best = d, int(ft["properties"]["id"])
        assign[i] = best
        print(f"    [경계 밖 보정] {jp[i]} → 코드 {best} (경계까지 {bd:.1f}km)")
    return pd.DataFrame({"iata": jp, "pref_code": assign,
                         "name": ap.loc[jp, "name"].to_numpy(),
                         "lat": ap.loc[jp, "lat"].to_numpy(),
                         "lon": ap.loc[jp, "lon"].to_numpy()})


def by_departure(targets: pd.DataFrame, routes: pd.DataFrame, ap: pd.DataFrame,
                 key: str) -> pd.DataFrame:
    """대상점(도도부현 대표점 또는 격자칸) × 월 × 출발공항 최단 소요시간."""
    arrs = sorted(routes["arr"].unique())
    ground = B.gc_km(ap.loc[arrs, "lat"].to_numpy()[:, None],
                     ap.loc[arrs, "lon"].to_numpy()[:, None],
                     targets["lat"].to_numpy()[None, :],
                     targets["lon"].to_numpy()[None, :]) / B.GROUND_KMH * 60
    pos = {a: i for i, a in enumerate(arrs)}
    rt = routes.copy()
    rt["air_min"] = (B.gc_km(rt["dlat"], rt["dlon"], rt["alat"], rt["alon"])
                     / B.CRUISE_KMH * 60 + B.TAXI_MIN)

    out = []
    for month, g in rt.groupby("month"):
        frame = {key: targets[key].to_numpy(), "month": month}
        for dep in DEPS:
            sub = g[g["dep"] == dep]
            if sub.empty:
                frame[dep] = np.full(len(targets), np.nan)
                continue
            rows = [pos[a] for a in sub["arr"]]
            total = B.OVERHEAD_MIN + sub["air_min"].to_numpy()[:, None] + ground[rows]
            frame[dep] = total.min(axis=0).round(1)
        out.append(pd.DataFrame(frame))
    return pd.concat(out, ignore_index=True)


def main():
    geo = json.load(open(B.RAW / "japan_pref.geojson", encoding="utf-8"))
    ap, routes = B.airports(), B.routes()
    routes = routes.merge(ap[["lat", "lon"]].rename(columns={"lat": "dlat", "lon": "dlon"}),
                          left_on="dep", right_index=True)
    routes = routes.merge(ap[["lat", "lon"]].rename(columns={"lat": "alat", "lon": "alon"}),
                          left_on="arr", right_index=True)
    jp = sorted(routes["arr"].unique())

    apf = airport_prefecture(ap, jp, geo)
    apf.to_csv(OUT / "airport_pref.csv", index=False, encoding="utf-8")
    have = apf["pref_code"].nunique()
    print(f"  airport_pref.csv — 취항공항 {len(apf)}개가 {have}개 도도부현에 분포 "
          f"(나머지 {47 - have}개 현은 이웃 현 공항을 이용)")

    pref = B.prefectures()
    p = by_departure(pref, routes, ap, "pref_code")
    p.to_csv(OUT / "panel_by_dep.csv", index=False, encoding="utf-8")
    print(f"  panel_by_dep.csv  {p.shape}")

    cells = pd.read_csv(OUT / "grid_cells.csv")
    gcell = by_departure(cells, routes, ap, "cell_id")
    gcell.to_csv(OUT / "grid_by_dep.csv", index=False, encoding="utf-8")
    print(f"  grid_by_dep.csv   {gcell.shape}")

    for f in ("airport_pref.csv", "panel_by_dep.csv", "grid_by_dep.csv"):
        print(f"    {f:22s} {(OUT / f).stat().st_size/1_048_576:6.2f} MB")

    a = p[p["month"] == 8]
    print("\n  8월 출발공항 단독 접근성 (도도부현 평균 분):")
    for dep in DEPS:
        print(f"    {dep}  {a[dep].mean():6.0f}분   최선 {a[dep].min():.0f} / 최악 {a[dep].max():.0f}")
    print(f"    4개 모두 쓸 때 평균 {a[DEPS].min(axis=1).mean():.0f}분")


if __name__ == "__main__":
    main()
