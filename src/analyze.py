"""접근성 ↔ 실제 방문. 인과가 아니라 '어긋남'을 잰다."""
from __future__ import annotations
import pathlib
import numpy as np, pandas as pd

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "processed"
MODELS = {
    # 주력: 관광 매력도를 비중으로 통제한 뒤 접근성만 본다
    "korea_share": ["min_minutes"],
    # 보조: 절대 규모. 그 지역 외국인 총량을 통제한다
    "korea": ["min_minutes", "log_foreign"],
}


def _ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    resid = y - pred
    ss = float(resid @ resid)
    tot = float(((y - y.mean()) ** 2).sum())
    return beta, pred, resid, (1 - ss / tot if tot else np.nan)


def fit(d: pd.DataFrame, target: str, xs: list[str]) -> pd.DataFrame:
    d = d.copy()
    d["log_foreign"] = np.log(d["foreign_total"].clip(lower=1))
    y = np.log(d[target].clip(lower=1e-12)).to_numpy()
    months = pd.get_dummies(d["month"], prefix="m", drop_first=True).astype(float).to_numpy()
    X = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in xs] + [months])
    beta, pred, resid, r2 = _ols(X, y)
    d[f"{target}_pred"] = np.exp(pred)
    d[f"{target}_resid"] = resid
    d[f"{target}_ratio"] = np.exp(resid)      # 1=예측대로, <1=과소, >1=초과
    coefs = "  ".join(f"{c} {b:+.4f}" for c, b in zip(xs, beta[1:1 + len(xs)]))
    print(f"  [{target}] n={len(d)}  {coefs}  R²={r2:.3f}")
    return d


def main():
    d = pd.read_csv(OUT / "panel.csv")
    for t, xs in MODELS.items():
        d = fit(d, t, xs)
    d.to_csv(OUT / "panel.csv", index=False, encoding="utf-8")

    ann = (d.groupby(["pref_code", "pref_ja", "pref_en", "lat", "lon"])
             .agg(korea=("korea", "sum"), foreign_total=("foreign_total", "sum"),
                  min_minutes=("min_minutes", "mean"), gravity=("gravity", "mean"),
                  n_reachable=("n_reachable", "mean"), ratio=("korea_share_ratio", "median"),
                  ratio_min=("korea_share_ratio", "min"), ratio_max=("korea_share_ratio", "max"),
                  uncertain=("korea_uncertain", "sum")).reset_index())
    ann["korea_share"] = ann["korea"] / ann["foreign_total"]
    ann.to_csv(OUT / "annual.csv", index=False, encoding="utf-8")

    fmt = lambda v: f"{v:,.2f}"
    c = ["pref_ja", "min_minutes", "korea", "korea_share", "ratio"]
    print("\n=== 접근성 대비 과소방문 (한국인 비중 기준, 잔차 중앙값) ===")
    print(ann.nsmallest(8, "ratio")[c].to_string(index=False, float_format=fmt))
    print("\n=== 접근성 대비 초과방문 ===")
    print(ann.nlargest(8, "ratio")[c].to_string(index=False, float_format=fmt))


if __name__ == "__main__":
    main()
