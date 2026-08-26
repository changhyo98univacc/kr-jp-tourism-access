"""원자료 → 분석용 테이블. 로컬에서 한 번 돌리고 결과만 커밋한다."""
from __future__ import annotations
import re, csv, json, math, pathlib
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
DEP = {"인천": "ICN", "김포": "GMP", "김해": "PUS", "제주": "CJU"}
_code = lambda s: (re.search(r"\(([A-Z]{3})\)$", str(s).strip()) or [None, None])[1]


def airports() -> pd.DataFrame:
    rows = [r for r in csv.DictReader(open(RAW / "airports.csv", encoding="utf-8")) if r["iata_code"]]
    d = pd.DataFrame([{"iata": r["iata_code"], "name": r["name"], "country": r["iso_country"],
                       "lat": float(r["latitude_deg"]), "lon": float(r["longitude_deg"])} for r in rows])
    return d.drop_duplicates("iata").set_index("iata")


def routes() -> pd.DataFrame:
    """48개 엑셀 → (dep, arr, month, flights, pax) 롱 테이블. 일본행만."""
    ap, out = airports(), []
    for f in sorted(RAW.glob("[[]*[]]2025-*.xlsx")):
        m = re.match(r"\[(.+?)\]2025-(\d{2})\.xlsx", f.name)
        df = pd.read_excel(f, sheet_name="Data", header=0)
        df.columns = ["from_raw", "to_raw", "flights", "pax", "cargo"]
        df = df[df["from_raw"] != "전체 합계"].copy()
        df["dep"], df["arr"] = DEP[m.group(1)], df["to_raw"].map(_code)
        df["month"] = int(m.group(2))
        out.append(df[["dep", "arr", "month", "flights", "pax"]])
    r = pd.concat(out, ignore_index=True)
    r = r[r["arr"].isin(ap.index[ap["country"] == "JP"])]
    for c in ("flights", "pax"):
        r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0).astype(int)
    return r[r["flights"] > 0].reset_index(drop=True)


def _num(v):
    """'*1,790' → (1790.0, True). 별표는 표본오차가 커서 참고값이라는 표시다."""
    if pd.isna(v):
        return float("nan"), False
    s = str(v).strip()
    flag = s.startswith("*")
    s = s.lstrip("*").replace(",", "").replace("　", "").strip()
    if s in ("", "-", "－", "…", "x", "X"):
        return float("nan"), flag
    try:
        return float(s), flag
    except ValueError:
        return float("nan"), flag


def lodging(path: pathlib.Path) -> pd.DataFrame:
    """参考第1表(N月) → (pref_code, month, foreign_total, korea, korea_uncertain)."""
    out = []
    for mo in range(1, 13):
        df = pd.read_excel(path, sheet_name=f"参考第1表({mo}月)", header=None)
        for _, row in df.iterrows():
            m = re.match(r"^\s*(\d{2})(\D.*)$", str(row[0]).strip())
            if not m or not (1 <= int(m.group(1)) <= 47):
                continue
            tot, _ = _num(row[1])
            kr, flag = _num(row[2])
            out.append({"pref_code": int(m.group(1)), "pref_ja": m.group(2).strip(), "month": mo,
                        "foreign_total": tot, "korea": kr, "korea_uncertain": flag})
    d = pd.DataFrame(out)
    n_bad = int(d["korea"].isna().sum())
    if n_bad:
        print(f"  [주의] 해석 불가 셀 {n_bad}개 — 해당 행 제외")
    d = d.dropna(subset=["korea", "foreign_total"])
    print(f"  숙박: {d['pref_code'].nunique()}개 도도부현, 참고값(*) {int(d['korea_uncertain'].sum())}칸")
    return d.reset_index(drop=True)


def _rings(geom):
    """Polygon/MultiPolygon → 외곽 링 목록."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def _area_centroid(ring):
    """신발끈 공식으로 링의 부호면적과 무게중심."""
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-12:
        xs, ys = zip(*ring)
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return abs(a), cx / (6 * a), cy / (6 * a)


def _dp(pts, eps):
    """Douglas-Peucker 단순화 (순수 파이썬)."""
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    den = math.hypot(dx, dy)
    dmax, idx = -1.0, 0
    for i, (x, y) in enumerate(pts[1:-1], 1):
        d = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / den if den else math.hypot(x - x0, y - y0)
        if d > dmax:
            dmax, idx = d, i
    if dmax <= eps:
        return [pts[0], pts[-1]]
    return _dp(pts[:idx + 1], eps)[:-1] + _dp(pts[idx:], eps)


def prefectures(eps: float = 0.01, min_area: float = 5e-4) -> pd.DataFrame:
    """도도부현 대표점 = 최대 링의 무게중심. 앱용 단순화 경계도 같이 만든다."""
    g = json.load(open(RAW / "japan_pref.geojson", encoding="utf-8"))
    rows, feats = [], []
    for ft in g["features"]:
        rings = _rings(ft["geometry"])
        stats = [_area_centroid(r) for r in rings]
        area, cx, cy = max(stats, key=lambda s: s[0])
        p = ft["properties"]
        rows.append({"pref_code": int(p["id"]), "pref_ja": p["nam_ja"], "pref_en": p["nam"],
                     "lat": cy, "lon": cx})
        keep = [_dp(r, eps) for r, s in zip(rings, stats) if s[0] >= min_area]
        keep = [k for k in keep if len(k) >= 4] or [_dp(rings[stats.index(max(stats))], eps)]
        feats.append({"type": "Feature",
                      "properties": {"pref_code": int(p["id"]), "pref_ja": p["nam_ja"], "pref_en": p["nam"]},
                      "geometry": {"type": "MultiPolygon", "coordinates": [[k] for k in keep]}})
    json.dump({"type": "FeatureCollection", "features": feats},
              open(OUT / "japan_pref_simple.geojson", "w", encoding="utf-8"), ensure_ascii=False)
    return pd.DataFrame(rows)


def gc_km(lat1, lon1, lat2, lon2):
    """대권거리(km). 위경도에서 직접 유클리드 계산하지 않는다."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


# ── 모델 상수 (모두 근사값. 앱에 명시한다) ───────────────────────────
OVERHEAD_MIN = 165   # 출국 수속 120 + 입국 수속 45
TAXI_MIN     = 25    # 이착륙·유도
CRUISE_KMH   = 800   # 순항속도
GROUND_KMH   = 60    # 공항→목적지 지상이동 (ad-hoc 근사)
TAU_MIN      = 60    # 중력모형 감쇠 척도 (스윕 결과 180분은 변별력 소실)
REACH_MIN    = 360   # '접근 가능'으로 볼 총소요시간 상한


def build():
    ap, rt, pref = airports(), routes(), prefectures()
    lod = lodging(RAW / "estat_shukuhaku_2025_pref.xlsx")

    # 공항 × 도도부현 지상이동
    jp = sorted(rt["arr"].unique())
    grid = pd.MultiIndex.from_product([jp, pref["pref_code"]], names=["arr", "pref_code"]).to_frame(index=False)
    grid = grid.merge(pref, on="pref_code").merge(
        ap.loc[jp, ["lat", "lon"]].rename(columns={"lat": "alat", "lon": "alon"}), left_on="arr", right_index=True)
    grid["ground_min"] = gc_km(grid["alat"], grid["alon"], grid["lat"], grid["lon"]) / GROUND_KMH * 60

    # 출발 × 도착 비행시간
    rt = rt.merge(ap[["lat", "lon"]].rename(columns={"lat": "dlat", "lon": "dlon"}), left_on="dep", right_index=True)
    rt = rt.merge(ap[["lat", "lon"]].rename(columns={"lat": "alat", "lon": "alon"}), left_on="arr", right_index=True)
    rt["air_km"] = gc_km(rt["dlat"], rt["dlon"], rt["alat"], rt["alon"])
    rt["air_min"] = rt["air_km"] / CRUISE_KMH * 60 + TAXI_MIN

    # 노선 × 도도부현 총소요시간
    x = rt.merge(grid[["arr", "pref_code", "ground_min"]], on="arr")
    x["total_min"] = OVERHEAD_MIN + x["air_min"] + x["ground_min"]

    acc = (x.groupby(["pref_code", "month"])
             .apply(lambda g: pd.Series({
                 "min_minutes": g["total_min"].min(),
                 "best_dep": g.loc[g["total_min"].idxmin(), "dep"],
                 "best_arr": g.loc[g["total_min"].idxmin(), "arr"],
                 "n_reachable": int(g.loc[g["total_min"] <= REACH_MIN, "arr"].nunique()),
                 "gravity": float((g["flights"] * np.exp(-g["total_min"] / TAU_MIN)).sum()),
             }), include_groups=False).reset_index())

    d = (acc.merge(lod.drop(columns=["pref_ja"]), on=["pref_code", "month"])
            .merge(pref, on="pref_code"))
    d["korea_share"] = d["korea"] / d["foreign_total"]
    d.to_csv(OUT / "panel.csv", index=False, encoding="utf-8")
    rt.to_csv(OUT / "routes.csv", index=False, encoding="utf-8")  # 앱에서 노선을 그리려면 좌표가 필요하다
    ap.loc[jp].reset_index().to_csv(OUT / "airports_jp.csv", index=False, encoding="utf-8")
    print(f"panel.csv  {d.shape}  ({d['pref_code'].nunique()}개 도도부현 × {d['month'].nunique()}개월)")
    print(f"routes.csv {rt.shape} | airports_jp.csv {len(jp)}개")
    return d


if __name__ == "__main__":
    build()
