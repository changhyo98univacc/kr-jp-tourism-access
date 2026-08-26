"""한국에서 일본은 얼마나 가까운가 — 접근성과 실제 방문의 어긋남.

앱은 계산하지 않는다. src/build_data.py + src/analyze.py 가 만든 결과만 읽는다.
"""
from __future__ import annotations
import json, pathlib
import pandas as pd
import plotly.express as px, plotly.graph_objects as go
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent
D = ROOT / "data" / "processed"
DEP_NAME = {"ICN": "인천", "GMP": "김포", "PUS": "김해", "CJU": "제주"}
DEP_COLOR = {"ICN": "#C8102E", "GMP": "#0B6E4F", "PUS": "#1D4E89", "CJU": "#E08A00"}
MAP_STYLE, CENTER, ZOOM = "carto-positron", {"lat": 37.0, "lon": 137.5}, 3.9

st.set_page_config(page_title="한국–일본 지역 접근성", page_icon="🛫", layout="wide")


@st.cache_data
def load():
    panel = pd.read_csv(D / "panel.csv")
    annual = pd.read_csv(D / "annual.csv")
    routes = pd.read_csv(D / "routes.csv")
    airports = pd.read_csv(D / "airports_jp.csv")
    geo = json.load(open(D / "japan_pref_simple.geojson", encoding="utf-8"))
    return panel, annual, routes, airports, geo


@st.cache_data
def load_grid():
    """격자는 무거우니 격자 탭을 열 때만 읽는다."""
    cells = pd.read_csv(D / "grid_cells.csv")
    acc = pd.read_csv(D / "grid_access.csv")
    gj = json.load(open(D / "grid_cells.geojson", encoding="utf-8"))
    return cells, acc, gj


panel, annual, routes, airports, geo = load()

METRICS = {
    "최단 소요시간": ("min_minutes", "Turbo_r", None,
                 "출발 4개 공항 중 가장 빨리 닿는 경로의 총 소요시간(분)"),
    "한국인 비중": ("korea_share", "Reds", None,
                "그 지역 외국인 숙박자 중 한국인이 차지하는 비율"),
    "접근성 대비 어긋남": ("korea_share_ratio", "RdBu", 1.0,
                    "1 = 접근성이 예측한 그대로. 1보다 작으면 접근성 대비 덜 옵니다"),
    "접근 가능 공항 수": ("n_reachable", "Greens", None,
                   "총 소요 6시간 이내로 닿는 일본 공항 수"),
}

HOVER = {"pref_code": False, "pref_en": True, "min_minutes": ":.0f",
         "korea": ":,", "korea_share": ":.1%", "korea_share_ratio": ":.2f"}

with st.sidebar:
    st.markdown("### 🛫 한국–일본 지역 접근성")
    st.caption("2025년 · 인천·김포·김해·제주 출발")
    month = st.slider("월", 1, 12, 8, format="%d월")
    metric_label = st.radio("지도에 표시할 것", list(METRICS), index=0)
    show_routes = st.checkbox("항공 노선 겹쳐 보기", value=True)
    st.divider()
    st.caption("접근성이 방문을 **일으킨다**고 주장하지 않습니다. "
               "접근성이 예측하는 것과 실제의 **어긋남**을 보는 도구입니다.")

col, scale, mid, hint = METRICS[metric_label]
m = panel[panel["month"] == month].copy()

st.markdown(f"## {month}월의 일본")
r_m = routes[routes["month"] == month]
c = st.columns(4)
c[0].metric("취항 일본 공항", f"{r_m['arr'].nunique()}곳")
c[1].metric("운항 편수", f"{int(r_m['flights'].sum()):,}편")
c[2].metric("가장 가까운 곳", m.loc[m["min_minutes"].idxmin(), "pref_ja"],
            f"{m['min_minutes'].min():.0f}분")
c[3].metric("가장 먼 곳", m.loc[m["min_minutes"].idxmax(), "pref_ja"],
            f"{m['min_minutes'].max():.0f}분")


def choropleth(df, col, scale, mid, label):
    kw = {"color_continuous_midpoint": mid} if mid is not None else {}
    fig = px.choropleth_map(
        df, geojson=geo, locations="pref_code", featureidkey="properties.pref_code",
        color=col, color_continuous_scale=scale, map_style=MAP_STYLE,
        center=CENTER, zoom=ZOOM, opacity=0.78, hover_name="pref_ja",
        hover_data=HOVER, labels={col: label}, **kw)
    fig.update_layout(height=620, margin={"l": 0, "r": 0, "t": 0, "b": 0},
                      coloraxis_colorbar={"title": label, "thickness": 12})
    return fig


def route_traces(month):
    rr = routes[routes["month"] == month]
    traces, seen = [], set()
    for dep, g in rr.groupby("dep"):
        lons, lats = [], []
        for _, r in g.iterrows():
            lons += [r["dlon"], r["alon"], None]
            lats += [r["dlat"], r["alat"], None]
        traces.append(go.Scattermap(
            lon=lons, lat=lats, mode="lines", opacity=0.55, hoverinfo="skip",
            line={"width": 1.1, "color": DEP_COLOR[dep]}, name=f"{DEP_NAME[dep]} 출발"))
        seen.update(g["arr"])
    a = airports[airports["iata"].isin(seen)]
    traces.append(go.Scattermap(
        lon=a["lon"], lat=a["lat"], mode="markers", name="일본 공항",
        marker={"size": 7, "color": "#1A2430"},
        text=a["iata"] + " " + a["name"], hovertemplate="%{text}<extra></extra>"))
    return traces


tab_map, tab_grid, tab_gap, tab_rel, tab_pref = st.tabs(
    ["지도", "격자", "어긋남", "관계", "지역 상세"])

with tab_map:
    st.caption(hint)
    fig = choropleth(m, col, scale, mid, metric_label)
    if show_routes:
        for t in route_traces(month):
            fig.add_trace(t)
        fig.update_layout(legend={"orientation": "h", "y": 0.02, "x": 0.02,
                                  "bgcolor": "rgba(255,255,255,0.75)"})
    st.plotly_chart(fig, width="stretch")

with tab_grid:
    st.caption("도도부현 47덩어리로는 안 보이는 내부 편차를 10km 격자로 봅니다. "
               "**지도를 확대해 보세요.** 접근성은 좌표만 있으면 계산되지만, "
               "방문 데이터는 도도부현이 최소 단위라 여기엔 접근성만 있습니다.")
    cells, gacc, gj = load_grid()
    g = gacc[gacc["month"] == month].merge(cells, on="cell_id")
    g["best_dep_name"] = g["best_dep"].map(DEP_NAME)

    mode = st.radio("색으로 볼 것", ["최단 소요시간", "어느 공항에서 가장 빠른가"],
                    horizontal=True, label_visibility="collapsed")
    if mode == "최단 소요시간":
        hi = float(g["min_minutes"].quantile(0.99))
        f = px.choropleth_map(
            g, geojson=gj, locations="cell_id", featureidkey="properties.cell_id",
            color="min_minutes", color_continuous_scale="Turbo_r",
            range_color=(float(g["min_minutes"].min()), hi),
            map_style=MAP_STYLE, center=CENTER, zoom=ZOOM, opacity=0.72,
            hover_data={"cell_id": False, "min_minutes": ":.0f",
                        "best_dep_name": True, "best_arr": True},
            labels={"min_minutes": "분", "best_dep_name": "출발", "best_arr": "도착공항"})
        f.update_layout(coloraxis_colorbar={"title": "분", "thickness": 12})
        note = (f"색 범위는 상위 1%를 잘라 {hi:.0f}분까지입니다. "
                "오가사와라 제도 등 항공편이 닿지 않는 외딴 섬이 최대 21시간까지 나와 "
                "그대로 두면 본토가 전부 같은 색이 됩니다. 실제 값은 칸에 마우스를 올리면 보입니다.")
    else:
        f = px.choropleth_map(
            g, geojson=gj, locations="cell_id", featureidkey="properties.cell_id",
            color="best_dep_name", color_discrete_map={v: DEP_COLOR[k] for k, v in DEP_NAME.items()},
            map_style=MAP_STYLE, center=CENTER, zoom=ZOOM, opacity=0.72,
            hover_data={"cell_id": False, "min_minutes": ":.0f", "best_arr": True},
            labels={"best_dep_name": "가장 빠른 출발지", "min_minutes": "분", "best_arr": "도착공항"})
        share = g["best_dep_name"].value_counts()
        got = "  ·  ".join(f"{k} {v/len(g)*100:.0f}%" for k, v in share.items())
        note = (f"**{got}**  —  제주는 한 칸도 최적이 아닙니다. "
                "일본 대부분에서 김해가 더 가깝기 때문입니다.")
    f.update_layout(height=640, margin={"l": 0, "r": 0, "t": 0, "b": 0})
    st.plotly_chart(f, width="stretch")
    st.caption(note)

    q = st.columns(4)
    q[0].metric("격자 칸 수", f"{len(g):,}")
    q[1].metric("가장 빠른 칸", f"{g['min_minutes'].min():.0f}분")
    q[2].metric("중앙값", f"{g['min_minutes'].median():.0f}분")
    q[3].metric("본토 상위 1% 경계", f"{g['min_minutes'].quantile(0.99):.0f}분")

with tab_gap:
    st.caption("접근성이 예측한 한국인 비중과 실제의 비율. "
               "**1보다 작으면 접근성 대비 덜 온다**는 뜻입니다.")
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(choropleth(m, "korea_share_ratio", "RdBu", 1.0, "어긋남"),
                        width="stretch")
    with right:
        cols = ["pref_ja", "min_minutes", "korea", "korea_share_ratio"]
        cfg = {"pref_ja": "지역",
               "min_minutes": st.column_config.NumberColumn("소요(분)", format="%.0f"),
               "korea": st.column_config.NumberColumn("한국인", format="localized"),
               "korea_share_ratio": st.column_config.NumberColumn("어긋남", format="%.2f")}
        st.markdown("**접근성 대비 과소방문**")
        st.dataframe(m.nsmallest(8, "korea_share_ratio")[cols], hide_index=True,
                     column_config=cfg, width="stretch")
        st.markdown("**접근성 대비 초과방문**")
        st.dataframe(m.nlargest(8, "korea_share_ratio")[cols], hide_index=True,
                     column_config=cfg, width="stretch")

with tab_rel:
    st.caption("가까울수록 한국인 비중이 높습니다. 추세선에서 멀리 떨어진 점이 '어긋난' 지역입니다.")
    f = px.scatter(m, x="min_minutes", y="korea_share", size="korea", hover_name="pref_ja",
                   color="korea_share_ratio", color_continuous_scale="RdBu",
                   color_continuous_midpoint=1.0, size_max=45, log_y=True,
                   trendline="ols", trendline_color_override="#8A8A8A",
                   labels={"min_minutes": "최단 소요시간 (분)", "korea_share": "한국인 비중",
                           "korea_share_ratio": "어긋남"})
    f.update_layout(height=560, margin={"l": 0, "r": 0, "t": 10, "b": 0})
    st.plotly_chart(f, width="stretch")

with tab_pref:
    names = annual.sort_values("pref_code")["pref_ja"].tolist()
    default = names.index("広島県") if "広島県" in names else 0
    pick = st.selectbox("지역", names, index=default)
    p = panel[panel["pref_ja"] == pick].sort_values("month")
    row = annual[annual["pref_ja"] == pick].iloc[0]
    k = st.columns(4)
    k[0].metric("연간 한국인 숙박", f"{int(row['korea']):,}")
    k[1].metric("한국인 비중", f"{row['korea_share']:.1%}")
    k[2].metric("평균 최단 소요", f"{row['min_minutes']:.0f}분")
    k[3].metric("어긋남(중앙값)", f"{row['ratio']:.2f}")
    g1, g2 = st.columns(2)
    with g1:
        f = px.line(p, x="month", y="korea", markers=True,
                    labels={"korea": "인박", "month": "월"})
        f.update_traces(line={"color": "#C8102E"})
        f.update_layout(height=330, margin={"l": 0, "r": 0, "t": 34, "b": 0},
                        title="월별 한국인 숙박자")
        st.plotly_chart(f, width="stretch")
    with g2:
        f = px.bar(p, x="month", y="min_minutes", labels={"min_minutes": "분", "month": "월"})
        f.update_traces(marker_color="#1D4E89")
        f.update_layout(height=330, margin={"l": 0, "r": 0, "t": 34, "b": 0},
                        title="월별 최단 소요시간")
        st.plotly_chart(f, width="stretch")
    if row["uncertain"]:
        st.warning(f"이 지역은 12개월 중 {int(row['uncertain'])}개월이 "
                   "표본오차가 커서 참고값(*)으로 공표된 값입니다.")

with st.expander("계산 방법과 한계 — 반드시 함께 읽어주세요"):
    st.markdown("""
**소요시간** = 출입국 수속 165분 + 비행(대권거리 ÷ 800km/h + 이착륙 25분)
+ 지상이동(대권거리 ÷ 60km/h)
→ 출발 4개 공항 × 그 달 실제 운항한 노선을 모두 계산해 **가장 빠른 경로**를 취합니다.

**어긋남** = 실제 한국인 비중 ÷ 접근성으로 예측한 비중.
로그-선형 회귀에 월 고정효과를 넣었습니다 (R² 0.42).

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
- **대표점은 도도부현 중심점**입니다. 넓은 현은 내부 편차가 큽니다.
- **숙박자 ≠ 방문자.** 당일치기·크루즈가 빠지고, 숙박지와 관광지가 다를 수 있습니다.
- **해상 노선이 빠져 있습니다.** 부산–쓰시마 등 배편이 반영되지 않아
  나가사키현이 실제보다 멀게 나옵니다.
- 숙박통계는 **종업원 10인 이상 시설** 기준이라 소규모 숙박이 많은 지방이 과소평가됩니다.
- 별표(*)가 붙은 값은 일본 관광청이 **표본오차가 크다고 표시한 참고값**입니다.

**출처** — 국토교통부 항공통계(2025년 월별) · 일본 관광청 숙박여행통계조사(2025년 확정치)
· OurAirports · 일본 도도부현 경계
""")
