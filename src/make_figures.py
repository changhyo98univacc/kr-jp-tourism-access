"""발표용 정적 그림.

앱은 인터랙티브라 화면에만 있다. 슬라이드에는 정지된 그림이 필요하다.
색과 껍데기는 viz.py 를 그대로 쓴다 — 앱과 슬라이드가 다른 색이면 같은 것으로 안 보인다.

  python src/make_figures.py            # outputs/figures/*.png, *.svg
  python src/make_figures.py --only 6   # 하나만 다시

정적 렌더링에서는 화면용 글꼴 스택을 쓸 수 없다(브라우저가 없다).
STATIC_FONT 하나로 못박고, 없으면 실행을 멈춘다 — 한글이 깨진 그림을 조용히 내보내지 않는다.
"""
from __future__ import annotations
import argparse, json, pathlib, sys
import numpy as np, pandas as pd
import plotly.express as px, plotly.graph_objects as go

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import viz  # noqa: E402
import build_data as B  # noqa: E402

D = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

DEPS = ["ICN", "GMP", "PUS", "CJU"]
DEP_NAME = {"ICN": "인천", "GMP": "김포", "PUS": "김해", "CJU": "제주"}
NAME_COLOR = {DEP_NAME[d]: c for d, c in zip(DEPS, viz.CATEGORICAL)}
CENTER, ZOOM = {"lat": 37.2, "lon": 137.0}, 3.55
MONTH = 8                      # 대표로 쓰는 달. 슬라이드 캡션에 반드시 적는다
STATIC_FONT = "Malgun Gothic"  # 화면용 스택은 브라우저가 없으면 못 쓴다


def _check_font():
    from matplotlib import font_manager as fm
    if STATIC_FONT not in {f.name for f in fm.fontManager.ttflist}:
        raise SystemExit(f"글꼴 '{STATIC_FONT}' 이 없다. 한글이 깨진 그림을 내보내지 않는다.")


def save(fig, name: str, w: int = 1500, h: int = 950, tries: int = 3):
    """지도 내보내기는 타일을 받아오므로 산발적으로 실패한다. 조용히 넘기지 않고 재시도한다."""
    fig.update_layout(width=w, height=h, font={"family": STATIC_FONT})
    for ext in ("png", "svg"):
        last = None
        for k in range(tries):
            try:
                fig.write_image(str(OUT / f"{name}.{ext}"), format=ext,
                                scale=2 if ext == "png" else 1)
                last = None
                break
            except Exception as e:                      # noqa: BLE001
                last = e
                print(f"    [재시도 {k + 1}/{tries}] {name}.{ext} — {str(e)[:60]}")
        if last is not None:
            raise last
    print(f"  {name}  {(OUT / (name + '.png')).stat().st_size / 1024:6.0f} KB")


def load():
    panel = pd.read_csv(D / "panel.csv")
    panel["pref_label"] = panel["pref_ko"]
    return (panel, pd.read_csv(D / "annual.csv"), pd.read_csv(D / "routes.csv"),
            pd.read_csv(D / "panel_by_dep.csv"), pd.read_csv(D / "grid_cells.csv"),
            pd.read_csv(D / "grid_by_dep.csv"), pd.read_csv(D / "airports_jp.csv"),
            json.load(open(D / "japan_pref_simple.geojson", encoding="utf-8")),
            json.load(open(D / "grid_cells.geojson", encoding="utf-8")))


def outline_trace(geo):
    lons, lats = [], []
    for ft in geo["features"]:
        g = ft["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            lons += [c[0] for c in poly[0]] + [None]
            lats += [c[1] for c in poly[0]] + [None]
    return go.Scattermap(lon=lons, lat=lats, mode="lines", hoverinfo="skip",
                         line={"width": 0.9, "color": viz.SURFACE},
                         opacity=0.85, name="도도부현 경계")


def label_trace(df, col, k=5, largest=True):
    """지도 위 직접 라벨.

    mode="text" 단독 트레이스는 kaleido 의 지도 렌더러를 깨뜨린다(Error 525).
    점을 아주 작게 두고 markers+text 로 쓴다 — 결과 그림은 사실상 같다.
    """
    d = df.nlargest(k, col) if largest else df.nsmallest(k, col)
    return go.Scattermap(lon=d["lon"], lat=d["lat"], mode="markers+text", text=d["pref_ko"],
                         marker={"size": 5, "color": viz.INK},
                         textfont={"size": 21, "color": viz.INK},
                         textposition="top center", hoverinfo="skip", showlegend=False)


# ───────────────────────────────────────────────────────── 그림들
def fig01_catchment(panel, by_dep, geo, routes, ap):
    """4개 공항의 세력권 — 한국에서 일본이 어떻게 나뉘는가."""
    m = by_dep[by_dep.month == MONTH].copy()
    m["best"] = m[DEPS].idxmin(axis=1).map(DEP_NAME)
    f = px.choropleth_map(m, geojson=geo, locations="pref_code",
                          featureidkey="properties.pref_code", color="best",
                          color_discrete_map=NAME_COLOR,
                          category_orders={"best": [DEP_NAME[d] for d in DEPS]},
                          map_style="carto-positron", center=CENTER, zoom=ZOOM,
                          opacity=viz.MAP_OPACITY, labels={"best": ""})
    f.update_traces(marker={"line": {"width": viz.MAP_EDGE_W, "color": viz.SURFACE}})
    rr = routes[routes.month == MONTH]
    for dep, g in rr.groupby("dep"):
        lons, lats = [], []
        for _, r in g.iterrows():
            lons += [r["dlon"], r["alon"], None]
            lats += [r["dlat"], r["alat"], None]
        f.add_trace(go.Scattermap(lon=lons, lat=lats, mode="lines", opacity=0.5,
                                  hoverinfo="skip", showlegend=False,
                                  line={"width": 1.6,
                                        "color": NAME_COLOR[DEP_NAME[dep]]}))
    f.add_trace(go.Scattermap(lon=ap.lon, lat=ap.lat, mode="markers", showlegend=False,
                              marker={"size": 7, "color": viz.INK}, hoverinfo="skip"))
    viz.style_map(f)
    f.update_layout(legend={"font": {"size": 17}, "y": 0.02, "x": 0.02,
                            "bgcolor": "rgba(252,252,251,0.9)"})
    save(f, "fig-01-세력권")


def fig02_grid(cells, grid_by_dep, gj, geo):
    """10km 격자 접근성 + 행정구역 경계 — 공급은 연속, 수요는 47덩어리."""
    g = grid_by_dep[grid_by_dep.month == MONTH].copy()
    g["min_sel"] = g[DEPS].min(axis=1)
    g = g.merge(cells, on="cell_id")
    hi = float(g.min_sel.quantile(0.99))
    f = px.choropleth_map(g, geojson=gj, locations="cell_id",
                          featureidkey="properties.cell_id", color="min_sel",
                          color_continuous_scale=viz.SEQUENTIAL,
                          range_color=(float(g.min_sel.min()), hi),
                          map_style="carto-positron", center=CENTER, zoom=ZOOM,
                          opacity=viz.MAP_OPACITY, labels={"min_sel": "분"})
    # 칸마다 테두리를 그리면 3,953개가 겹쳐 화면이 검어진다. 격자에는 테두리를 두지 않는다.
    f.update_traces(marker={"line": {"width": 0}})
    f.add_trace(outline_trace(geo))
    viz.style_map(f)
    f.update_layout(showlegend=False,
                    coloraxis_colorbar={"title": {"text": "분", "side": "top"},
                                        "thickness": 16, "len": 0.7,
                                        "tickfont": {"size": 18},
                                        "title_font": {"size": 18}, "outlinewidth": 0})
    save(f, "fig-02-격자")


def fig03_gap(panel, geo):
    """접근성 대비 어긋남 — 이 프로젝트의 산출물."""
    m = panel[panel.month == MONTH].copy()
    m["ratio_log"] = np.log2(m.korea_share_ratio.clip(lower=1e-6))
    f = px.choropleth_map(m, geojson=geo, locations="pref_code",
                          featureidkey="properties.pref_code", color="ratio_log",
                          color_continuous_scale=viz.DIVERGING,
                          color_continuous_midpoint=0.0, range_color=(-2, 2),
                          map_style="carto-positron", center=CENTER, zoom=ZOOM,
                          opacity=viz.MAP_OPACITY, labels={"ratio_log": ""})
    f.update_traces(marker={"line": {"width": viz.MAP_EDGE_W, "color": viz.SURFACE}})
    f.add_trace(label_trace(m, "ratio_log", 3, True))
    f.add_trace(label_trace(m, "ratio_log", 3, False))
    viz.style_map(f)
    f.update_layout(showlegend=False, coloraxis_colorbar={
        "tickvals": [-2, -1, 0, 1, 2],
        "ticktext": ["¼배", "½배", "예측대로", "2배", "4배"],
        "thickness": 16, "len": 0.7, "tickfont": {"size": 18}, "outlinewidth": 0})
    save(f, "fig-03-어긋남")


def fig04_relation(panel):
    """가까울수록 한국인 비중이 높다 — 그리고 선에서 벗어난 곳들."""
    m = panel[panel.month == MONTH].copy()
    ext = set(m.nlargest(4, "korea_share_ratio").pref_ko) | \
          set(m.nsmallest(4, "korea_share_ratio").pref_ko)
    m["tag"] = m.pref_ko.where(m.pref_ko.isin(ext), "")
    f = px.scatter(m, x="min_minutes", y="korea_share", size="korea", text="tag",
                   color="korea_share_ratio", color_continuous_scale=viz.DIVERGING,
                   color_continuous_midpoint=1.0, size_max=52, log_y=True,
                   trendline="ols", trendline_options={"log_y": True},
                   trendline_color_override=viz.MUTED,
                   labels={"min_minutes": "최단 소요시간 (분)",
                           "korea_share": "외국인 중 한국인 비중",
                           "korea_share_ratio": "어긋남"})
    f.update_traces(marker={"line": {"width": 1.4, "color": viz.MUTED},
                            "sizemin": 7},
                    textposition="top center", textfont={"size": 17, "color": viz.INK},
                    selector=lambda t: t.type == "scatter" and "markers" in (t.mode or ""))
    f.update_yaxes(tickformat=".0%")
    viz.style(f, legend=False)
    f.update_layout(coloraxis_showscale=False, font={"size": 18},
                    margin={"l": 90, "r": 30, "t": 20, "b": 70})
    save(f, "fig-04-관계", 1500, 900)


def fig05_season(routes, grid_by_dep):
    """계절 — 연간 합계로는 보이지 않는 것."""
    a = routes.groupby("month")["arr"].nunique().rename("공항").reset_index()
    b = (grid_by_dep.assign(best=grid_by_dep[DEPS].idxmin(axis=1))
         .groupby(["month", "best"]).size().rename("칸").reset_index())
    b["비율"] = b.groupby("month")["칸"].transform(lambda s: s / s.sum() * 100)
    b["출발"] = b["best"].map(DEP_NAME)
    f = go.Figure()
    f.add_bar(x=a.month, y=a.공항, marker_color=viz.SINGLE,
              marker_line={"width": 2, "color": viz.SURFACE}, name="취항 공항 수")
    f.update_layout(yaxis_title="취항 일본 공항 수", xaxis_title="월")
    f.update_yaxes(range=[0, 36])
    for _, r in a.iterrows():
        f.add_annotation(x=r.month, y=r.공항, text=str(int(r.공항)), showarrow=False,
                         yshift=16, font={"size": 17, "color": viz.INK})
    viz.style(f, legend=False)
    f.update_layout(font={"size": 18}, margin={"l": 95, "r": 30, "t": 20, "b": 70})
    f.update_xaxes(dtick=1)
    save(f, "fig-05-계절", 1500, 780)


def fig06_hokkaido(panel):
    """대표점을 무게중심에서 현청으로 바꾼 이유 — 공간 단위가 결과를 만든다."""
    geo = B.load_boundaries(verbose=False)
    ap, routes = B.airports(), B.routes()
    ft = next(x for x in geo["features"] if int(x["properties"]["id"]) == 1)
    rings = B._rings(ft["geometry"])
    stats = [B._area_centroid(r) for r in rings]
    _, cx, cy = max(stats, key=lambda s: s[0])          # 무게중심 = 다이세쓰잔
    cap = pd.read_csv(ROOT / "data" / "reference" / "prefecture_capitals.csv")
    sap = cap[cap.pref_code == 1].iloc[0]               # 현청 = 삿포로

    rt = routes.merge(ap[["lat", "lon"]].rename(columns={"lat": "dlat", "lon": "dlon"}),
                      left_on="dep", right_index=True)
    rt = rt.merge(ap[["lat", "lon"]].rename(columns={"lat": "alat", "lon": "alon"}),
                  left_on="arr", right_index=True)
    rt["air"] = B.gc_km(rt.dlat, rt.dlon, rt.alat, rt.alon) / B.CRUISE_KMH * 60 + B.TAXI_MIN

    def series(lat, lon):
        out = []
        for mo, g in rt.groupby("month"):
            g = g.copy()
            g["tot"] = (B.OVERHEAD_MIN + g["air"]
                        + B.gc_km(g.alat, g.alon, lat, lon) / B.GROUND_KMH * 60)
            i = g["tot"].idxmin()
            out.append({"month": mo, "분": g.loc[i, "tot"], "공항": g.loc[i, "arr"]})
        return pd.DataFrame(out)

    a, b = series(cy, cx), series(float(sap.lat), float(sap.lon))
    f = go.Figure()
    f.add_scatter(x=a.month, y=a["분"], mode="lines+markers", name="무게중심 (산악부)",
                  line={"color": viz.CATEGORICAL[1], "width": 3},
                  marker={"size": 11, "line": {"width": 2, "color": viz.SURFACE}})
    f.add_scatter(x=b.month, y=b["분"], mode="lines+markers", name="현청 소재지 (삿포로)",
                  line={"color": viz.SINGLE, "width": 3},
                  marker={"size": 11, "line": {"width": 2, "color": viz.SURFACE}})
    f.update_layout(xaxis_title="월", yaxis_title="홋카이도 최단 소요시간 (분)")
    f.update_xaxes(dtick=1)
    viz.style(f)
    f.update_layout(font={"size": 18}, legend={"font": {"size": 18}},
                    margin={"l": 100, "r": 30, "t": 60, "b": 70})
    save(f, "fig-06-대표점", 1500, 780)
    print(f"     무게중심 {a['분'].min():.0f}~{a['분'].max():.0f}분 "
          f"(공항 {sorted(a.공항.unique())}) / "
          f"현청 {b['분'].min():.0f}~{b['분'].max():.0f}분 (공항 {sorted(b.공항.unique())})")


def fig07_scale_vs_share(annual):
    """규모 순위와 비중 순위는 다르다 — 이 프로젝트의 출발점."""
    n = 12
    left = annual.nlargest(n, "korea").sort_values("korea")
    right = annual.assign(s=annual.korea / annual.foreign_total).nlargest(n, "s").sort_values("s")
    from plotly.subplots import make_subplots
    f = make_subplots(rows=1, cols=2, horizontal_spacing=0.18,
                      subplot_titles=("한국인 숙박자 수 (인박)", "외국인 중 한국인 비중"))
    f.add_bar(x=left.korea, y=left.pref_ko, orientation="h", marker_color=viz.SINGLE,
              marker_line={"width": 2, "color": viz.SURFACE}, row=1, col=1)
    f.add_bar(x=right.s, y=right.pref_ko, orientation="h", marker_color=viz.CATEGORICAL[2],
              marker_line={"width": 2, "color": viz.SURFACE}, row=1, col=2)
    f.update_xaxes(tickformat=".0%", row=1, col=2)
    viz.style(f, legend=False)
    f.update_xaxes(showgrid=True, gridcolor=viz.GRID)
    f.update_yaxes(showgrid=False, tickfont={"size": 17})
    f.update_layout(font={"size": 17}, margin={"l": 110, "r": 40, "t": 60, "b": 60})
    for ann in f.layout.annotations:
        ann.font.size = 19
        ann.font.color = viz.INK
    save(f, "fig-07-규모대비중", 1600, 800)


FIGS = {1: fig01_catchment, 2: fig02_grid, 3: fig03_gap, 4: fig04_relation,
        5: fig05_season, 6: fig06_hokkaido, 7: fig07_scale_vs_share}


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--only", type=int, nargs="*", help="번호만 다시 만든다")
    args = ap_.parse_args()
    _check_font()
    panel, annual, routes, by_dep, cells, grid_by_dep, apj, geo, gj = load()
    ctx = {
        1: lambda: fig01_catchment(panel, by_dep, geo, routes, apj),
        2: lambda: fig02_grid(cells, grid_by_dep, gj, geo),
        3: lambda: fig03_gap(panel, geo),
        4: lambda: fig04_relation(panel),
        5: lambda: fig05_season(routes, grid_by_dep),
        6: lambda: fig06_hokkaido(panel),
        7: lambda: fig07_scale_vs_share(annual),
    }
    todo = args.only or sorted(ctx)
    print(f"그림 {len(todo)}개 → {OUT}")
    for k in todo:
        ctx[k]()


if __name__ == "__main__":
    main()
