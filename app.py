"""한국에서 일본은 얼마나 가까운가 — 접근성과 실제 방문의 어긋남.

앱은 계산하지 않는다. src/ 의 스크립트가 만든 결과를 읽어 고르고 그릴 뿐이다.
(출발공항 선택은 미리 구해둔 공항별 표에서 행별 최소값을 취하는 조회에 가깝다.)
색과 차트 껍데기 규격은 viz.py 에 모아 두었다.
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np, pandas as pd
import plotly.express as px, plotly.graph_objects as go
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))          # streamlit run 이 아닌 경로에서도 viz 를 찾게 한다
import viz  # noqa: E402
D = ROOT / "data" / "processed"

DEPS = ["ICN", "GMP", "PUS", "CJU"]
DEP_NAME = {"ICN": "인천", "GMP": "김포", "PUS": "김해", "CJU": "제주"}
# 색은 대상을 따른다 — 필터로 몇 개가 빠져도 남은 것의 색은 바뀌지 않는다.
DEP_COLOR = dict(zip(DEPS, viz.CATEGORICAL))
NAME_COLOR = {DEP_NAME[d]: c for d, c in DEP_COLOR.items()}
MAP_STYLE, CENTER, ZOOM = "carto-positron", {"lat": 37.0, "lon": 137.5}, 3.9

st.set_page_config(page_title="한국–일본 지역 접근성", page_icon="🛫", layout="wide")


def _sig(*names) -> tuple:
    """캐시 키에 파일 지문을 넣는다.

    @st.cache_data 는 함수 코드와 인자로만 키를 만든다. 인자 없이 파일을 읽으면
    데이터가 새로 빌드돼도 옛 값을 그대로 돌려준다 — 배포 후 실제로 앱이 죽었다.
    파일의 크기와 수정시각을 인자로 넘겨 내용이 바뀌면 캐시가 갈리게 한다.
    """
    out = []
    for n in names:
        p = D / n
        st_ = p.stat()
        out.append((n, st_.st_size, st_.st_mtime_ns))
    return tuple(out)


MAIN_FILES = ("panel.csv", "annual.csv", "routes.csv", "airports_jp.csv",
              "panel_by_dep.csv", "airport_pref.csv", "japan_pref_simple.geojson")
GRID_FILES = ("grid_cells.csv", "grid_by_dep.csv", "grid_cells.geojson")


@st.cache_data
def load(sig):
    return (pd.read_csv(D / "panel.csv"), pd.read_csv(D / "annual.csv"),
            pd.read_csv(D / "routes.csv"), pd.read_csv(D / "airports_jp.csv"),
            pd.read_csv(D / "panel_by_dep.csv"), pd.read_csv(D / "airport_pref.csv"),
            json.load(open(D / "japan_pref_simple.geojson", encoding="utf-8")))


@st.cache_data
def load_grid(sig):
    return (pd.read_csv(D / "grid_cells.csv"), pd.read_csv(D / "grid_by_dep.csv"),
            json.load(open(D / "grid_cells.geojson", encoding="utf-8")))


panel, annual, routes, airports, panel_by_dep, ap_pref, geo = load(_sig(*MAIN_FILES))

# build_data.py 를 다시 돌리면 panel.csv 의 잔차 열이 지워진다. 알 수 없는 오류로
# 죽는 대신, 무엇을 해야 하는지 화면에 적고 멈춘다.
_need = ["korea_share_ratio", "korea_share_pred", "min_minutes",
         "best_arr", "best_dep", "pref_ko"]
_missing = [c for c in _need if c not in panel.columns]
if _missing:
    st.error(f"panel.csv 에 {', '.join(_missing)} 열이 없습니다. "
             "`python src/analyze.py` 를 실행해 잔차를 다시 만들어 주세요 "
             "(build_data.py 를 다시 돌리면 이 열들이 지워집니다).")
    st.stop()

# 한국인 청중에게 보여줄 이름. 좁은 축에는 한글만, 표·툴팁에는 한자를 함께 적는다.
for _d in (panel, annual):
    _d["pref_label"] = _d["pref_ko"] + "(" + _d["pref_ja"] + ")"
NAMES = panel[["pref_code", "pref_ja", "pref_ko", "pref_label", "pref_en"]].drop_duplicates()
AP_KO = dict(zip(airports["iata"], airports["name_ko"]))


def pick_best(df: pd.DataFrame, deps: list[str]) -> pd.DataFrame:
    """고른 출발공항들 중 가장 빠른 것. 열 몇 개의 행별 최소값일 뿐이다."""
    out = df.copy()
    out["min_sel"] = df[deps].min(axis=1)
    out["best_dep_name"] = df[deps].idxmin(axis=1).map(DEP_NAME)
    return out


# ── 사이드바 ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🛫 한국–일본 지역 접근성")
    st.caption("2025년 · 국토교통부 항공통계 + 일본 관광청 숙박통계")
    month = st.slider("월", 1, 12, 8, format="%d월")
    st.divider()
    sel = st.multiselect("출발 공항", [DEP_NAME[d] for d in DEPS],
                         default=[DEP_NAME[d] for d in DEPS])
    deps = [d for d in DEPS if DEP_NAME[d] in sel] or DEPS
    if not sel:
        st.warning("하나도 고르지 않아 **4개 공항 전부**를 쓴 결과를 보여줍니다.")
    if len(deps) < 4:
        st.info(f"**{'·'.join(DEP_NAME[d] for d in deps)}**만 있다고 가정한 접근성입니다. "
                "「지도」·「격자」에만 적용되며 「어긋남」·「관계」는 4개 공항 전부를 쓴 "
                "모델 결과 그대로입니다.")
        st.warning("직항이 사라진 섬은 **지상이동으로 계산되어 비현실적으로 커집니다** "
                   "(모델의 지상이동은 바다를 건넙니다). 그 값은 소요시간이 아니라 "
                   "**직항이 없다는 표시**로 읽어주세요.")
    st.divider()
    kanji = st.checkbox("지역명에 한자 병기", value=True,
                        help="축·범례·요약에 「이시카와(石川県)」처럼 함께 적습니다. "
                             "표와 툴팁에는 항상 병기하며, 지도 위 직접 라벨은 글자가 "
                             "겹치므로 한글만 씁니다.")
    st.divider()
    st.caption("접근성이 방문을 **일으킨다**고 주장하지 않습니다. "
               "접근성이 예측하는 것과 실제의 **어긋남**을 보는 도구입니다.")

# 좁은 자리는 토글로 고른다. 툴팁·표는 공간이 있으므로 항상 병기한다.
NC = "pref_label" if kanji else "pref_ko"

m = panel[panel["month"] == month].merge(
    pick_best(panel_by_dep[panel_by_dep["month"] == month], deps).drop(columns=["month"]),
    on="pref_code")
r_m = routes[(routes["month"] == month) & (routes["dep"].isin(deps))]

st.markdown(f"## {month}월의 일본")
c = st.columns(4)
c[0].metric("취항 일본 공항", f"{r_m['arr'].nunique()}곳")
c[1].metric("운항 편수", f"{int(r_m['flights'].sum()):,}편")
c[2].metric("가장 가까운 곳", m.loc[m["min_sel"].idxmin(), NC],
            f"{m['min_sel'].min():.0f}분", delta_color="off")
c[3].metric("가장 먼 곳", m.loc[m["min_sel"].idxmax(), NC],
            f"{m['min_sel'].max():.0f}분", delta_color="off")

LABELS = {"pref_ko": "지역", "pref_label": "지역", "pref_ja": "일본 표기",
          "min_sel": "선택 공항 최단(분)", "min_minutes": "4개 공항 최단(분)",
          "korea": "한국인 숙박(인박)", "korea_share": "한국인 비중",
          "korea_share_ratio": "어긋남(예측 대비)", "pref_en": "로마자",
          "best_dep_name": "가장 빠른 출발지", "best_arr": "도착 공항"}
HOVER = {"pref_code": False, "pref_ja": True, "pref_en": True, "min_sel": ":.0f",
         "korea": ":,", "korea_share": ":.1%", "korea_share_ratio": ":.2f"}
# 어긋남 탭은 4개 공항 모델이므로 툴팁도 그 값을 보여준다 (선택 공항 값과 섞지 않는다).
HOVER_MODEL = {**HOVER, "min_sel": False, "min_minutes": ":.0f"}
# 색 범위는 4개 공항 기준으로 고정한다. 출발공항을 바꿔도 척도가 유지돼야 비교가 된다.
_ref = pick_best(panel_by_dep, DEPS)["min_sel"]
REF_RANGE = (float(_ref.min()), float(_ref.quantile(0.99)))
METRICS = {
    "최단 소요시간": ("min_sel", "seq", "고른 출발공항 중 가장 빨리 닿는 경로의 총 소요시간(분)"),
    "어느 공항에서 가장 빠른가": ("best_dep_name", "cat", "각 지역에 가장 빨리 닿는 출발공항 — 4개 공항의 세력권입니다"),
    "한국인 비중": ("korea_share", "seq", "그 지역 외국인 숙박자 중 한국인이 차지하는 비율"),
    "한국인 숙박자 수": ("korea", "seq", "절대 규모(인박). 도쿄·오사카가 압도하므로 로그 눈금으로 칠합니다"),
    "접근성 대비 어긋남": ("korea_share_ratio", "div", "1 = 접근성이 예측한 그대로. 1보다 작으면 접근성 대비 덜 옵니다"),
}


# 애니메이션은 12개월을 한 그림에 담는다. 색 범위를 프레임마다 다시 잡으면
# 변화가 아니라 착시가 보이므로 전 기간 공통 범위로 못박는다.
ALL = panel.merge(
    pick_best(panel_by_dep, DEPS)[["pref_code", "month", "min_sel", "best_dep_name"]],
    on=["pref_code", "month"])
ALL["korea_log"] = np.log10(ALL["korea"].clip(lower=1))
ALL["ratio_log"] = np.log2(ALL["korea_share_ratio"].clip(lower=1e-6))
FIXED = {"min_sel": REF_RANGE,
         "korea_log": (float(ALL.korea_log.min()), float(ALL.korea_log.max())),
         "korea_share": (0.0, float(ALL.korea_share.quantile(0.99))),
         "ratio_log": (-2.0, 2.0)}


def choropleth(df, col, kind, label, *, gj=geo, loc="pref_code",
               key="properties.pref_code", hover=None, height=620, crange=None,
               animation=None):
    common = dict(geojson=gj, locations=loc, featureidkey=key, map_style=MAP_STYLE,
                  center=CENTER, zoom=ZOOM, opacity=viz.MAP_OPACITY,
                  hover_data=HOVER if hover is None else hover,
                  labels={**LABELS, col: label, "month": "월"})
    if animation:
        common["animation_frame"] = animation
    if loc == "pref_code":
        common["hover_name"] = "pref_label"
    if kind == "cat":
        fig = px.choropleth_map(df, color=col, color_discrete_map=NAME_COLOR, **common)
    else:
        scale = viz.SEQUENTIAL if kind == "seq" else viz.DIVERGING
        fig = px.choropleth_map(df, color=col, color_continuous_scale=scale,
                                range_color=crange,
                                **({"color_continuous_midpoint": 0.0} if kind == "div" else {}),
                                **common)
        fig.update_layout(coloraxis_colorbar={"title": {"text": label, "side": "right"},
                                              "thickness": 11, "len": 0.72,
                                              "outlinewidth": 0, "ticks": "outside",
                                              "tickcolor": viz.AXIS})
    if loc == "pref_code":
        # 47개 덩어리는 표면색 얇은 선으로 나눈다. 격자(수천 칸)에는 넣지 않는다 — 선이 데이터를 덮는다.
        fig.update_traces(marker={"line": {"width": viz.MAP_EDGE_W, "color": viz.SURFACE}})
    return viz.style_map(fig, height)


def label_trace(df, col, k=5, largest=True, color=None):
    """극단 몇 곳만 지도에 직접 이름을 적는다. 모든 점에 값을 붙이지 않는다."""
    d = df.nlargest(k, col) if largest else df.nsmallest(k, col)
    return go.Scattermap(
        lon=d["lon"], lat=d["lat"], mode="text", text=d["pref_ko"],
        textfont={"size": 12, "color": color or viz.INK},
        textposition="top center", hoverinfo="skip", showlegend=False)


def route_traces(rr):
    traces, seen = [], set()
    for dep, g in rr.groupby("dep"):
        lons, lats = [], []
        for _, r in g.iterrows():
            lons += [r["dlon"], r["alon"], None]
            lats += [r["dlat"], r["alat"], None]
        traces.append(go.Scattermap(lon=lons, lat=lats, mode="lines", opacity=0.6,
                                    hoverinfo="skip", name=f"{DEP_NAME[dep]} 출발",
                                    line={"width": 2, "color": DEP_COLOR[dep]}))
        seen.update(g["arr"])
    a = airports[airports["iata"].isin(seen)]
    traces.append(go.Scattermap(lon=a["lon"], lat=a["lat"], mode="markers", name="일본 공항",
                                marker={"size": 8, "color": viz.INK},
                                text=a["iata"] + " " + a["name_ko"],
                                hovertemplate="%{text}<extra></extra>"))
    return traces


tabs = st.tabs(["지도", "격자", "어긋남", "관계", "둘러보기", "공항", "지역 상세"])

# ── 지도 ────────────────────────────────────────────────────────────
with tabs[0]:
    label = st.radio("지도에 표시할 것", list(METRICS), horizontal=True,
                     label_visibility="collapsed")
    col, kind, hint = METRICS[label]
    st.caption(hint)
    cc = st.columns([1, 1])
    anim = cc[0].checkbox("12개월 자동 재생", value=False,
                          help="12개월을 한 그림에 담아 재생합니다. 색 범위는 전 기간 "
                               "공통으로 고정해 프레임끼리 비교가 되게 했습니다.")
    show_routes = cc[1].checkbox("항공 노선 겹쳐 보기", value=True, disabled=anim)

    ACOL = {"korea": "korea_log", "korea_share_ratio": "ratio_log"}
    if anim:
        acol = ACOL.get(col, col)
        fig = choropleth(ALL.sort_values("month"), acol,
                         "seq" if acol == "korea_log" else kind, label,
                         crange=FIXED.get(acol), animation="month")
    elif col == "korea":
        md = m.assign(korea_log=np.log10(m["korea"].clip(lower=1)))
        fig = choropleth(md, "korea_log", "seq", label, crange=FIXED["korea_log"])
    else:
        fig = choropleth(m, col, kind, label,
                         crange=REF_RANGE if col == "min_sel" else None)

    if (anim and ACOL.get(col, col) == "korea_log") or (not anim and col == "korea"):
        tv = [2, 3, 4, 5, 6]
        fig.update_coloraxes(colorbar={"tickvals": tv,
                                       "ticktext": [f"{10**v:,}" for v in tv]})
    if anim and col == "korea_share_ratio":
        fig.update_coloraxes(colorbar={"tickvals": [-2, -1, 0, 1, 2],
                                       "ticktext": ["¼배", "½배", "예측대로", "2배", "4배"]})
    if col == "min_sel":
        st.caption(f"색 범위는 **4개 공항 기준 {REF_RANGE[0]:.0f}~{REF_RANGE[1]:.0f}분으로 "
                   "고정**했습니다. 출발공항을 바꿔도 척도가 유지되어 비교할 수 있습니다. "
                   "그보다 먼 곳은 같은 색으로 보이니 마우스를 올려 확인하세요.")

    if not anim:
        if show_routes:
            for tr in route_traces(r_m):
                fig.add_trace(tr)
        else:
            fig.update_layout(showlegend=kind == "cat")
        if col in ("min_sel", "korea", "korea_share") and st.checkbox(
                "상·하위 지역 이름 표시 (지도 위에는 겹침 때문에 한글만)",
                value=True, key="lbl_map"):
            fig.add_trace(label_trace(m, col, 5, True))
            fig.add_trace(label_trace(m, col, 5, False))
    st.plotly_chart(fig, width="stretch")
    if anim:
        st.caption("▶ 를 누르면 1월부터 12월까지 흐릅니다. **색 범위를 12개월 공통으로 "
                   "고정**했습니다 — 프레임마다 다시 잡으면 없는 변화가 보입니다. "
                   "재생 중에는 노선 겹쳐보기와 지역 이름 표시를 쓰지 않습니다. "
                   "격자는 칸이 3,953개라 12프레임이면 브라우저가 감당하지 못해 넣지 않았습니다.")

# ── 격자 ────────────────────────────────────────────────────────────
with tabs[1]:
    cells, grid_by_dep, gj = load_grid(_sig(*GRID_FILES))
    st.caption(f"도도부현 47덩어리로는 안 보이는 내부 편차를 10km 격자 {len(cells):,}칸으로 "
               "봅니다. **지도를 확대해 보세요.** 접근성은 좌표만 있으면 계산되지만 "
               "방문 데이터는 도도부현이 최소 단위라 여기엔 접근성만 있습니다.")
    g = pick_best(grid_by_dep[grid_by_dep["month"] == month], deps).merge(cells, on="cell_id")
    gmode = st.radio("색으로 볼 것", ["최단 소요시간", "어느 공항에서 가장 빠른가"],
                     horizontal=True, label_visibility="collapsed")
    ghover = {"cell_id": False, "min_sel": ":.0f", "best_dep_name": True}
    if gmode == "최단 소요시간":
        hi = float(g["min_sel"].quantile(0.99))
        f = choropleth(g, "min_sel", "seq", "분", gj=gj, loc="cell_id",
                       key="properties.cell_id", hover=ghover, height=640,
                       crange=(float(g["min_sel"].min()), hi))
        mx = float(g["min_sel"].max())
        note = (f"색 범위는 상위 1%를 잘라 {hi:.0f}분까지입니다. 오가사와라 제도 등 "
                f"항공편이 닿지 않는 외딴 섬이 최대 {mx/60:.0f}시간({mx:.0f}분)까지 나와, "
                "그대로 두면 본토가 전부 같은 색이 됩니다. "
                "실제 값은 칸에 마우스를 올리면 보입니다.")
    else:
        f = choropleth(g, "best_dep_name", "cat", "가장 빠른 출발지", gj=gj, loc="cell_id",
                       key="properties.cell_id", hover=ghover, height=640)
        share = g["best_dep_name"].value_counts(normalize=True) * 100
        note = "**" + "  ·  ".join(f"{k} {v:.0f}%" for k, v in share.items()) + "**"
        miss = [DEP_NAME[d] for d in deps if DEP_NAME[d] not in share.index]
        if miss:
            note += f"  —  {', '.join(miss)}는 이 달에 한 칸도 최적이 아닙니다."
    st.plotly_chart(f, width="stretch")
    st.caption(note)
    q = st.columns(4)
    q[0].metric("격자 칸 수", f"{len(g):,}")
    q[1].metric("가장 빠른 칸", f"{g['min_sel'].min():.0f}분")
    q[2].metric("중앙값", f"{g['min_sel'].median():.0f}분")
    q[3].metric("본토 상위 1% 경계", f"{g['min_sel'].quantile(0.99):.0f}분")

# ── 어긋남 ──────────────────────────────────────────────────────────
with tabs[2]:
    st.caption("접근성이 예측한 한국인 비중과 실제의 비율. **1보다 작으면 접근성 대비 "
               "덜 온다**는 뜻입니다. 이 탭은 항상 4개 공항 전부를 쓴 모델 결과입니다.")
    md = m.assign(ratio_log=np.log2(m["korea_share_ratio"].clip(lower=1e-6)))
    left, right = st.columns([3, 2])
    with left:
        fg = choropleth(md, "ratio_log", "div", "어긋남", hover=HOVER_MODEL)
        fg.update_coloraxes(
            cmin=-2, cmax=2, cmid=0,
            colorbar={"tickvals": [-2, -1, 0, 1, 2],
                      "ticktext": ["¼배", "½배", "예측대로", "2배", "4배"]})
        fg.add_trace(label_trace(md, "ratio_log", 5, True))
        fg.add_trace(label_trace(md, "ratio_log", 5, False))
        st.plotly_chart(fg, width="stretch")
    with right:
        cols = ["pref_label", "min_minutes", "korea", "korea_share_ratio"]
        cfg = {"pref_label": "지역",
               "min_minutes": st.column_config.NumberColumn("소요(분)", format="%.0f"),
               "korea": st.column_config.NumberColumn("한국인", format="localized"),
               "korea_share_ratio": st.column_config.NumberColumn("어긋남", format="%.2f")}
        st.markdown("**접근성 대비 과소방문**")
        st.dataframe(m.nsmallest(8, "korea_share_ratio")[cols], hide_index=True,
                     column_config=cfg, width="stretch")
        st.markdown("**접근성 대비 초과방문**")
        st.dataframe(m.nlargest(8, "korea_share_ratio")[cols], hide_index=True,
                     column_config=cfg, width="stretch")

# ── 관계 ────────────────────────────────────────────────────────────
with tabs[3]:
    st.caption("가까울수록 한국인 비중이 높습니다. 추세선에서 멀리 떨어진 점이 "
               "'어긋난' 지역입니다. 점 크기는 한국인 숙박자 수입니다.")
    k = st.slider("이름을 표시할 극단 지역 수 (위·아래 각각)", 0, 10, 5, key="lbl_rel")
    # 모든 점에 이름을 붙이면 읽히지 않는다. 위아래 끝만 고른다.
    ext = set(m.nlargest(k, "korea_share_ratio")["pref_ko"]) |           set(m.nsmallest(k, "korea_share_ratio")["pref_ko"])
    ms = m.assign(tag=m["pref_ko"].where(m["pref_ko"].isin(ext), ""))
    f = px.scatter(ms, x="min_minutes", y="korea_share", size="korea", hover_name="pref_label",
                   text="tag",
                   color="korea_share_ratio", color_continuous_scale=viz.DIVERGING,
                   color_continuous_midpoint=1.0, size_max=44, log_y=True,
                   trendline="ols", trendline_options={"log_y": True},
                   trendline_color_override=viz.MUTED,
                   labels={**LABELS, "min_minutes": "최단 소요시간 (분)",
                           "korea_share": "한국인 비중", "korea_share_ratio": "어긋남"})
    f.update_traces(marker={"line": {"width": 1.5, "color": viz.SURFACE}},
                    textposition="top center",
                    textfont={"size": 11, "color": viz.INK_2},
                    selector=lambda t: t.type == "scatter" and "markers" in (t.mode or ""))
    f.update_yaxes(tickformat=".0%")
    f.update_layout(coloraxis_colorbar={"title": {"text": "어긋남", "side": "right"},
                                        "thickness": 11, "len": 0.72, "outlinewidth": 0})
    st.plotly_chart(viz.style(f, 560, legend=False), width="stretch")

# ── 둘러보기 ────────────────────────────────────────────────────────
with tabs[4]:
    st.caption("결론과 무관하게, 데이터 자체를 훑어보는 곳입니다.")
    view = st.radio("무엇을 볼까요", ["지역 순위", "월별 추이", "계절 패턴", "지역 비교"],
                    horizontal=True, label_visibility="collapsed")

    if view == "지역 순위":
        base = st.radio("기준", ["연간 합계", f"{month}월"], horizontal=True)
        src = (annual if base == "연간 합계" else m).rename(columns={"korea_share": "share"})
        topn = st.slider("표시 개수", 5, 47, 20)
        cc = st.columns(2)
        for cont, key, title, fmt in ((cc[0], "korea", "한국인 숙박자 수 (인박)", None),
                                      (cc[1], "share", "외국인 중 한국인 비중", ".0%")):
            with cont:
                d = src.nlargest(topn, key).sort_values(key)
                f = px.bar(d, x=key, y=NC, orientation="h",
                           hover_name="pref_label", labels={key: "", NC: ""})
                f.update_traces(marker_color=viz.SINGLE,
                                marker_line={"width": 1.5, "color": viz.SURFACE})
                if fmt:
                    f.update_xaxes(tickformat=fmt)
                f.update_xaxes(showgrid=True, gridcolor=viz.GRID)
                f.update_yaxes(showgrid=False)
                st.plotly_chart(viz.style(f, 26 * topn + 100, title, legend=False),
                                width="stretch")
        st.caption("왼쪽은 **규모**, 오른쪽은 **집중도**입니다. 두 순위가 다르다는 것 자체가 "
                   "이 프로젝트의 출발점입니다 — 도쿄·오사카는 수가 많지만 한국인 비중은 낮습니다.")

    elif view == "월별 추이":
        nat = panel.groupby("month").agg(korea=("korea", "sum"),
                                         foreign=("foreign_total", "sum")).reset_index()
        nat["others"] = nat["foreign"] - nat["korea"]
        nat["share"] = nat["korea"] / nat["foreign"]
        fl = routes.groupby("month")["flights"].sum().reset_index()

        f = go.Figure()
        f.add_bar(x=nat["month"], y=nat["korea"], name="한국인", marker_color=viz.SINGLE,
                  marker_line={"width": 1.5, "color": viz.SURFACE})
        f.add_bar(x=nat["month"], y=nat["others"], name="그 밖의 외국인",
                  marker_color=viz.NEUTRAL, marker_line={"width": 1.5, "color": viz.SURFACE})
        f.update_layout(barmode="stack", xaxis_title="월", yaxis_title="연인원 숙박(인박)")
        st.plotly_chart(viz.style(f, 380, "전국 외국인 숙박자 — 한국인과 그 밖"), width="stretch")

        cc = st.columns(2)
        with cc[0]:
            f = px.line(nat, x="month", y="share", markers=True,
                        labels={"month": "월", "share": ""})
            f.update_traces(line={"color": viz.SINGLE, "width": 2},
                            marker={"size": 8, "line": {"width": 1.5, "color": viz.SURFACE}})
            f.update_yaxes(tickformat=".0%")
            st.plotly_chart(viz.style(f, 320, "외국인 중 한국인 비중", legend=False),
                            width="stretch")
        with cc[1]:
            f = px.bar(fl, x="month", y="flights", labels={"month": "월", "flights": ""})
            f.update_traces(marker_color=viz.SINGLE,
                            marker_line={"width": 1.5, "color": viz.SURFACE})
            st.plotly_chart(viz.style(f, 320, "일본행 운항편수 (4개 공항)", legend=False),
                            width="stretch")
        st.caption("두 그림은 **축이 다르므로 한 그림에 겹치지 않았습니다.** 전국 총량의 계절 "
                   "변동은 크지 않고, 편차는 지역별로 나타납니다 — 「계절 패턴」에서 보세요.")

    elif view == "계절 패턴":
        norm = st.radio("보는 법", ["지역별 계절 패턴", "절대 규모"], horizontal=True)
        piv = panel.pivot(index=NC, columns="month", values="korea")
        piv = piv.loc[[p for p in annual.sort_values("korea", ascending=False)[NC]
                       if p in piv.index]]
        if norm == "지역별 계절 패턴":
            f = px.imshow(piv.div(piv.mean(axis=1), axis=0), aspect="auto",
                          color_continuous_scale=viz.DIVERGING, zmin=0.4, zmax=1.6,
                          labels={"color": "연평균 대비"})
            cap = ("각 지역의 **연평균을 1로 놓은** 상대값입니다. 붉을수록 그 달에 몰립니다. "
                   "규모가 달라도 계절 패턴을 나란히 비교할 수 있습니다.")
        else:
            f = px.imshow(np.log10(piv.clip(lower=1)), aspect="auto",
                          color_continuous_scale=viz.SEQUENTIAL,
                          labels={"color": "log10(인박)"})
            cap = "절대 규모입니다. 상위 몇 개 지역이 전체를 지배하는 것이 보입니다."
        f.update_xaxes(title="월", side="top", tickfont={"color": viz.MUTED})
        f.update_yaxes(title="", tickfont={"size": 11, "color": viz.MUTED})
        f.update_layout(coloraxis_colorbar={"thickness": 11, "len": 0.5, "outlinewidth": 0})
        st.plotly_chart(viz.style(f, 940, legend=False), width="stretch")
        st.caption(cap)

    else:
        picks = st.multiselect("비교할 지역 (최대 4곳)", NAMES["pref_label"].tolist(),
                               default=[p for p in NAMES["pref_label"]
                                        if p.split("(")[0] in ("홋카이도", "후쿠오카", "히로시마", "오이타")],
                               max_selections=4)
        if not picks:
            st.info("비교할 지역을 하나 이상 골라주세요.")
        else:
            what = st.radio("무엇을", ["한국인 숙박자", "한국인 비중", "최단 소요시간"],
                            horizontal=True)
            ycol = {"한국인 숙박자": "korea", "한국인 비중": "korea_share",
                    "최단 소요시간": "min_minutes"}[what]
            d = panel[panel["pref_label"].isin(picks)]
            f = px.line(d, x="month", y=ycol, color=NC, markers=True,
                        color_discrete_sequence=viz.CATEGORICAL,
                        labels={"month": "월", ycol: "", NC: ""})
            f.update_traces(line={"width": 2},
                            marker={"size": 8, "line": {"width": 1.5, "color": viz.SURFACE}})
            if ycol == "korea_share":
                f.update_yaxes(tickformat=".0%")
            st.plotly_chart(viz.style(f, 470, what), width="stretch")
            st.caption("한 번에 4곳까지만 비교합니다. 색이 더 늘면 서로 구분되지 않습니다.")

# ── 공항 ────────────────────────────────────────────────────────────
with tabs[5]:
    have = set(ap_pref["pref_code"])
    st.info("이 탭은 **출발공항 선택과 무관하게 4개 공항 전부**를 쓴 값입니다. "
            "선택한 공항에서 실제로 뜨지 않는 노선을 표에 적지 않기 위해서입니다.")
    st.markdown("#### 한국 취항 공항이 없는 지역의 소요시간은 어떻게 구했나")
    st.markdown(f"""
모델은 **도도부현 안에 공항이 있는지를 따지지 않습니다.** 그 달에 한국에서 운항 중인
**일본 공항 전부**를 후보로 놓고, 각 공항에서 그 지역 대표점까지 걸리는 시간을 더한 뒤
**가장 짧은 것 하나**를 고릅니다. 그래서 공항이 없는 지역은 자연스럽게 **이웃 지역의
공항**을 쓰는 것으로 계산됩니다.

**한국 노선이 있는** 일본 공항 **{len(ap_pref)}개**는 **{len(have)}개** 도도부현에 있고,
나머지 **{47 - len(have)}개** 지역은 이웃 지역의 공항을 이용합니다.
(그 {47 - len(have)}개 지역에도 공항 자체는 있을 수 있습니다. 한국 노선이 없을 뿐입니다.)
""")
    a = (m.merge(ap_pref[["iata", "pref_code"]]
                 .rename(columns={"iata": "best_arr", "pref_code": "arr_pref"}),
                 left_on="best_arr", right_on="best_arr", how="left")
         .merge(NAMES.rename(columns={"pref_code": "arr_pref", "pref_label": "소재지"})[
             ["arr_pref", "소재지"]], on="arr_pref", how="left"))
    a["출발"] = a["best_dep"].map(DEP_NAME)
    a["이용 공항"] = a["best_arr"].map(AP_KO) + " (" + a["best_arr"] + ")"
    tbl = a[~a["pref_code"].isin(have)][
        ["pref_label", "min_minutes", "출발", "이용 공항", "소재지"]].copy()
    tbl.columns = ["한국 취항 공항이 없는 지역", "최단(분)", "출발", "이용 공항", "그 공항 소재지"]
    st.dataframe(tbl.sort_values("최단(분)"), hide_index=True, width="stretch",
                 column_config={"최단(분)": st.column_config.NumberColumn(format="%.0f")})
    yes = m[m["pref_code"].isin(have)]["min_minutes"]
    no = m[~m["pref_code"].isin(have)]["min_minutes"]
    k = st.columns(3)
    k[0].metric("취항 공항 보유 지역 평균", f"{yes.mean():.0f}분")
    k[1].metric("취항 공항 없는 지역 평균", f"{no.mean():.0f}분")
    k[2].metric("차이", f"{no.mean() - yes.mean():.0f}분")

    st.divider()
    st.markdown("#### 출발 공항 하나만 쓴다면")
    solo = panel_by_dep[panel_by_dep["month"] == month]
    rows = [{"출발": DEP_NAME[d], "평균(분)": solo[d].mean(),
             "가장 가까운 곳(분)": solo[d].min(), "가장 먼 곳(분)": solo[d].max(),
             "일본 취항지": routes[(routes["month"] == month) & (routes["dep"] == d)]["arr"].nunique()}
            for d in DEPS]
    rows.append({"출발": "4개 모두", "평균(분)": solo[DEPS].min(axis=1).mean(),
                 "가장 가까운 곳(분)": solo[DEPS].min(axis=1).min(),
                 "가장 먼 곳(분)": solo[DEPS].min(axis=1).max(),
                 "일본 취항지": routes[routes["month"] == month]["arr"].nunique()})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.0f")
                                for c in ("평균(분)", "가장 가까운 곳(분)", "가장 먼 곳(분)")})

    st.divider()
    st.markdown(f"#### {month}월 취항 일본 공항 (4개 공항 전부 기준)")
    ar = (routes[routes["month"] == month].groupby("arr").agg(편=("flights", "sum"), 객=("pax", "sum"),
                                 n=("dep", "nunique")).reset_index()
          .merge(ap_pref[["iata", "pref_code", "name"]].rename(columns={"iata": "arr"}), on="arr")
          .merge(NAMES.rename(columns={"pref_label": "소재지"})[["pref_code", "소재지"]],
                 on="pref_code"))
    ar["공항"] = ar["arr"].map(AP_KO)
    ar = ar[["arr", "공항", "name", "소재지", "n", "편", "객"]].sort_values("객", ascending=False)
    ar.columns = ["IATA", "공항", "정식 명칭", "소재지", "한국 출발지 수", "운항편", "여객"]
    st.dataframe(ar, hide_index=True, width="stretch", height=420,
                 column_config={c: st.column_config.NumberColumn(format="localized")
                                for c in ("운항편", "여객")})

# ── 지역 상세 ───────────────────────────────────────────────────────
with tabs[6]:
    names = annual.sort_values("pref_code")["pref_label"].tolist()
    default = next((i for i, v in enumerate(names) if v.startswith("히로시마")), 0)
    pick = st.selectbox("지역", names, index=default)
    p = panel[panel["pref_label"] == pick].sort_values("month")
    row = annual[annual["pref_label"] == pick].iloc[0]
    k = st.columns(4)
    k[0].metric("연간 한국인 숙박", f"{int(row['korea']):,}")
    k[1].metric("한국인 비중", f"{row['korea_share']:.1%}")
    k[2].metric("평균 최단 소요", f"{row['min_minutes']:.0f}분")
    k[3].metric("어긋남(중앙값)", f"{row['ratio']:.2f}")
    g1, g2 = st.columns(2)
    with g1:
        f = px.line(p, x="month", y="korea", markers=True, labels={"korea": "", "month": "월"})
        f.update_traces(line={"color": viz.SINGLE, "width": 2},
                        marker={"size": 8, "line": {"width": 1.5, "color": viz.SURFACE}})
        st.plotly_chart(viz.style(f, 330, "월별 한국인 숙박자 (인박)", legend=False),
                        width="stretch")
    with g2:
        f = px.bar(p, x="month", y="min_minutes", labels={"min_minutes": "", "month": "월"})
        f.update_traces(marker_color=viz.SINGLE,
                        marker_line={"width": 1.5, "color": viz.SURFACE})
        st.plotly_chart(viz.style(f, 330, "월별 최단 소요시간 (분·4개 공항)", legend=False),
                        width="stretch")
    if row["uncertain"]:
        st.warning(f"이 지역은 12개월 중 {int(row['uncertain'])}개월이 "
                   "표본오차가 커서 참고값(*)으로 공표된 값입니다.")

# ── 방법과 한계 ─────────────────────────────────────────────────────
with st.expander("계산 방법과 한계 — 반드시 함께 읽어주세요"):
    st.markdown("""
**소요시간** = 출입국 수속 165분 + 비행(대권거리 ÷ 800km/h + 이착륙 25분)
+ 지상이동(대권거리 ÷ 60km/h)

그 달에 **실제 운항한 노선**만 후보로 씁니다. 도도부현 안에 공항이 있는지는 따지지
않으며, 일본 취항 공항 전부를 놓고 **가장 빠른 하나**를 고릅니다. 그래서 한국 노선이
있는 공항이 없는 18개 지역은 이웃 지역 공항을 쓰는 것으로 계산됩니다.

**대표점은 현청 소재지**입니다. 기하학적 중심점을 쓰면 홋카이도가 다이세쓰잔 산악지대가
되어 삿포로가 아닌 아사히카와 기준이 되므로, 사람이 가는 곳을 기준으로 삼았습니다.

**어긋남** = 실제 한국인 비중 ÷ 접근성으로 예측한 비중.
로그-선형 회귀에 월 고정효과를 넣었습니다 (R² 0.38).

---

**한계**

- **인과가 아닙니다.** 수요가 있어서 노선이 생긴 것일 수 있습니다(역인과).
  이 앱은 어긋남을 보여줄 뿐, 접근성이 방문을 늘린다고 주장하지 않습니다.
- **한국 안에서 공항까지 가는 시간은 빠져 있습니다.** 출발 4개 공항에 이미 도착해
  있다고 가정한 국가 단위 접근성이며, 개인 기준이 아닙니다. 서울 거주자에게 김해는
  실제로 훨씬 멉니다.
- **격자에는 접근성만 있습니다.** 방문 데이터(국적별 숙박)는 도도부현 47이 최소
  단위라 격자 해상도로 어긋남을 낼 수 없습니다. 공급은 연속인데 수요는 47덩어리라는
  이 비대칭 자체가, 공간 단위 선택이 결과를 좌우한다는 사례입니다.
- **지상이동은 근사값**입니다. 실제 철도·도로가 아니라 직선거리에 60km/h를 가정했습니다.
  산악·도서 지역은 실제보다 가깝게 나옵니다.
- **지상이동이 바다를 건넙니다.** 4개 공항을 모두 쓰면 오키나와·이시가키에 직항이
  있어 문제가 드러나지 않지만, 출발공항을 좁히면 직항이 사라진 섬이 20시간을 넘습니다.
  그 값은 소요시간이 아니라 **직항이 없다는 표시**로 읽어야 합니다.
- **대표점은 현청 소재지 한 점**입니다. 넓은 현의 내부 편차는 담기지 않습니다.
- **경계 원자료가 분쟁 지역을 일본 영역으로 담고 있어 제외했습니다** — 독도(원자료는
  시마네현으로 표기), 센카쿠, 북방영토. 어느 것도 한국 취항 공항이나 숙박통계가 없어
  분석에 기여하지 않습니다. 제외 내역은 파이프라인 실행 시 콘솔에 출력됩니다.
- **숙박자 ≠ 방문자.** 당일치기·크루즈가 빠지고, 숙박지와 관광지가 다를 수 있습니다.
- **해상 노선이 빠져 있습니다.** 부산–쓰시마 등 배편이 반영되지 않아
  나가사키현이 실제보다 멀게 나옵니다.
- 숙박통계는 **종업원 10인 이상 시설** 기준이라 소규모 숙박이 많은 지방이 과소평가됩니다.
- 별표(*)가 붙은 값은 일본 관광청이 **표본오차가 크다고 표시한 참고값**입니다.

**출처** — 국토교통부 항공통계(2025년 월별) · 일본 관광청 숙박여행통계조사(2025년 확정치)
· OurAirports · 일본 도도부현 경계
""")
