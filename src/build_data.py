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


# ── 경계 원자료 로더 ────────────────────────────────────────────────
# 원자료 geojson 은 영유권 분쟁 지역을 일본 영역으로 담고 있다. 그중 독도는 한국 영토이며,
# 나머지도 실효지배·영유권이 다투어지는 곳이다. 어느 쪽도 이 분석(한국발 항공 접근성)에
# 기여하지 않으므로 — 취항 공항도, 숙박 통계도 없다 — 링 단위로 제외한다.
# 조용히 지우지 않는다. 무엇을 몇 개 뺐는지 반드시 찍는다.
DISPUTED = [
    # 이름,           도도부현코드, lon_min, lon_max, lat_min, lat_max
    ("독도",              32, 131.80, 131.95, 37.20, 37.30),
    ("센카쿠 열도",        47, 123.40, 124.60, 25.65, 26.00),
    ("하보마이 군도",       1, 145.90, 146.30, 43.30, 43.60),
    ("시코탄",             1, 146.50, 147.00, 43.55, 44.00),
    ("쿠나시리",           1, 145.30, 146.50, 43.70, 44.70),
    ("에토로후",           1, 146.80, 149.00, 44.40, 45.60),
]


def load_boundaries(verbose: bool = True) -> dict:
    """도도부현 경계 geojson. 분쟁 지역 링을 제외하고 무엇을 뺐는지 보고한다."""
    g = json.load(open(RAW / "japan_pref.geojson", encoding="utf-8"))
    removed = []
    for ft in g["features"]:
        code = int(ft["properties"]["id"])
        boxes = [d for d in DISPUTED if d[1] == code]
        if not boxes:
            continue
        polys = ([[ft["geometry"]["coordinates"]]] if ft["geometry"]["type"] == "Polygon"
                 else [[p] for p in ft["geometry"]["coordinates"]])
        keep = []
        for wrapped in polys:
            poly = wrapped[0]
            xs = [c[0] for c in poly[0]]
            ys = [c[1] for c in poly[0]]
            hit = next((d for d in boxes
                        if d[2] <= min(xs) and max(xs) <= d[3]
                        and d[4] <= min(ys) and max(ys) <= d[5]), None)
            if hit:
                removed.append((hit[0], len(poly[0])))
            else:
                keep.append(poly)
        if not keep:
            continue
        ft["geometry"] = {"type": "MultiPolygon", "coordinates": keep}
    if verbose:
        if removed:
            from collections import Counter
            c = Counter(n for n, _ in removed)
            print("  [경계] 분쟁 지역 링 제외: "
                  + ", ".join(f"{k} {v}개" for k, v in c.items()))
        else:
            print("  [경계] 제외 대상 없음 — 원자료가 바뀌었는지 확인할 것")
    return g


def capitals() -> pd.DataFrame:
    """대표점은 현청 소재지다.

    기하학적 무게중심을 쓰면 홋카이도의 대표점이 다이세쓰잔 산악지대가 되어,
    삿포로(신치토세, 월 600편대)가 아니라 아사히카와(월 20~30편)가 최적 공항이 된다.
    사람이 가는 곳을 기준으로 삼는다. 좌표가 제 현 안에 있는지 반드시 검증한다.
    """
    from matplotlib.path import Path as MplPath
    d = pd.read_csv(ROOT / "data" / "reference" / "prefecture_capitals.csv")
    geo = load_boundaries(verbose=False)
    pts = d[["lon", "lat"]].to_numpy()
    inside = np.zeros(len(d), dtype=int)
    for ft in geo["features"]:
        code = int(ft["properties"]["id"])
        for ring in _rings(ft["geometry"]):
            r = np.asarray(ring, float)
            if len(r) < 4:
                continue
            hit = MplPath(r).contains_points(pts)
            inside[hit & (d["pref_code"].to_numpy() == code)] = 1
    bad = d[inside == 0]
    if len(bad):
        raise ValueError("현청 좌표가 제 도도부현 안에 없다: "
                         + bad.to_string(index=False))
    print(f"  [대표점] 현청 소재지 {len(d)}곳 — 전부 자기 도도부현 안에 있음 (검증 통과)")
    return d


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
    """도도부현 대표점 = 현청 소재지. 앱용 단순화 경계도 같이 만든다."""
    g = load_boundaries()
    cap = capitals().set_index("pref_code")
    rows, feats = [], []
    for ft in g["features"]:
        rings = _rings(ft["geometry"])
        stats = [_area_centroid(r) for r in rings]
        p = ft["properties"]
        code = int(p["id"])
        rows.append({"pref_code": code, "pref_ja": p["nam_ja"], "pref_en": p["nam"],
                     "capital": cap.loc[code, "capital"],
                     "lat": float(cap.loc[code, "lat"]), "lon": float(cap.loc[code, "lon"])})
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
    print("  ※ panel.csv 를 새로 썼으므로 잔차 열이 없습니다 — "
          "`python src/analyze.py` 를 반드시 이어서 실행하세요.")
    return d


if __name__ == "__main__":
    build()
