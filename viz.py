"""색과 차트 껍데기 규격.

색은 눈으로 고르지 않았다. 네 가지 일(범주·순차·발산·상태) 중 하나만 하게 두고,
범주형은 검증기로 통과시킨 값만 쓴다. 지도·산점도처럼 아무 두 색이나 맞닿을 수 있는
형태는 all-pairs 기준을 넘겨야 하며, 기본 팔레트는 그 기준에서 3색이 상한이다.
4색이 필요해 4번 슬롯만 노랑→보라로 재배열했다(문서가 허용하는 순수 재배열).

    node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a,#4a3aa7" \
         --mode light --surface "#FBFBF9" --pairs all
    → ALL CHECKS PASS · CVD ΔE 9.2 (목표 8) · 일반시야 ΔE 16.3 (하한 15)

aqua(#1baf7a)는 표면 대비 2.72:1 로 3:1 에 못 미친다. 규정상 '완화 채널'이 필요하며,
범례·툴팁·「공항」 탭의 표가 그 역할을 한다.
"""
from __future__ import annotations

# ── 표면과 잉크 ──────────────────────────────────────────────────────
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# ── 범주형: 정체성(어느 출발공항인가) ────────────────────────────────
# 색은 순위가 아니라 대상을 따른다. 필터로 몇 개가 사라져도 남은 것의 색은 그대로다.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]

# ── 순차: 크기(얼마나 오래 걸리나) ───────────────────────────────────
# 무지개 금지. 한 가지 색상으로 밝음→어두움.
SEQUENTIAL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
              "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]

# ── 발산: 극성(기준선의 어느 쪽인가) ─────────────────────────────────
# 따뜻함↔차가움 두 극과 중립 회색 중간점. 중간점에 색상을 두지 않는다.
DIVERGING = [(0.0, "#2a78d6"), (0.5, "#f0efec"), (1.0, "#e34948")]

# 단일 계열 막대는 언제나 1번 슬롯 하나로 칠한다(값에 따라 색을 바꾸지 않는다).
SINGLE = CATEGORICAL[0]
NEUTRAL = "#d8d3c8"

FONT = ("Pretendard, 'Noto Sans KR', -apple-system, BlinkMacSystemFont, "
        "'Segoe UI', Roboto, sans-serif")


def style(fig, height: int = 420, title: str | None = None, legend: bool = True):
    """차트 껍데기를 한 곳에서 정한다 — 눈금선은 실선 헤어라인, 여백은 넉넉하게."""
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font={"family": FONT, "size": 13, "color": INK_2},
        title=None if title is None else {
            "text": title, "font": {"size": 15, "color": INK}, "x": 0, "xanchor": "left"},
        margin={"l": 8, "r": 8, "t": 44 if title else 12, "b": 8},
        hoverlabel={"font": {"family": FONT, "size": 12}, "bgcolor": SURFACE,
                    "bordercolor": AXIS},
        showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0,
                "title": {"text": ""}, "font": {"size": 12}},
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=AXIS, linewidth=1,
                     ticks="outside", tickcolor=AXIS, ticklen=4,
                     tickfont={"color": MUTED, "size": 12},
                     title_font={"color": MUTED, "size": 12})
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
                     showline=False, tickfont={"color": MUTED, "size": 12},
                     title_font={"color": MUTED, "size": 12})
    return fig


def style_map(fig, height: int = 620, title: str | None = None):
    """지도는 눈금선이 없으므로 축 설정을 건드리지 않는다."""
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        font={"family": FONT, "size": 13, "color": INK_2},
        title=None if title is None else {
            "text": title, "font": {"size": 15, "color": INK}, "x": 0, "xanchor": "left"},
        margin={"l": 0, "r": 0, "t": 40 if title else 0, "b": 0},
        hoverlabel={"font": {"family": FONT, "size": 12}, "bgcolor": SURFACE,
                    "bordercolor": AXIS},
        legend={"orientation": "h", "yanchor": "bottom", "y": 0.01, "x": 0.01,
                "bgcolor": "rgba(252,252,251,0.85)", "bordercolor": AXIS,
                "borderwidth": 1, "title": {"text": ""}, "font": {"size": 12}},
    )
    return fig
