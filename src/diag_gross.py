# -*- coding: utf-8 -*-
"""
diag_gross.py — 「コストが高いから負けたのでは?」を潰す診断。

🔴 これは再検定ではない。事前宣言 §6 が禁じているのは
   「通るまで格子や合格ラインを動かすこと」であって、
   **落ちた理由を特定すること**ではない。

   したがってこのスクリプトは:
     - 格子を1つも変えない（同じ36通り）
     - 合格ラインを1つも下げない
     - 判定を出さない。あなたの判定メモ の結論は変わらない

   出すのは2つだけ:
     1. cost=0（グロス）にしたとき avg_r がどこまで上がるか
        → 上げてもラインに届かないなら、敗因はコストではない
     2. 各検定の**実測 cost_r**（= 往復コスト ÷ 平均1R）
        → 判定書では SL=ATR×2.0 基準の甘いラインで採点した。
          ここで本来のラインを出し、甘く採点しても厳しく採点しても
          結論が変わらないことを示す

使い方:
    python diag_gross.py --out diag_gross.json
"""

import argparse
import importlib.util
import json
import os
from datetime import datetime, timezone

import numpy as np

import signal_ma_cross as _M06

_ENG = _M06._ENG
run_backtest = _M06.run_backtest
summarize = _M06.summarize
split_oos = _M06.split_oos

SYMBOL = _M06.SYMBOL
TIMEFRAMES = _M06.TIMEFRAMES
MA_PAIRS = _M06.MA_PAIRS
M_GRID = _M06.M_GRID
T_GRID = _M06.T_GRID
COST_PRICE = _M06.COST_PRICE
ATR_PERIOD = _M06.ATR_PERIOD
EXPECTED_TESTS = _M06.EXPECTED_TESTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="diag_gross.json")
    args = ap.parse_args()

    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"[ABORT] mt5.initialize 失敗: {mt5.last_error()}")
        raise SystemExit(2)
    sym = _ENG.ensure_symbol(mt5)

    print("=== 診断: コストをゼロにしたら届くのか ===")
    print("🔴 これは再検定ではない。判定は あなたの判定メモ のまま変わらない。\n")

    rows = []
    for tf in TIMEFRAMES:
        bars, dm = _ENG.load_rates(mt5, sym, tf)
        print(f"[{tf}] バー {dm['bars']:,} 本 ({dm['from']} 〜 {dm['to']})")

        atr = _ENG.atr_series(bars["high"], bars["low"], bars["close"],
                              ATR_PERIOD)
        atr_mean = float(np.nanmean(atr))
        print(f"      平均 ATR({ATR_PERIOD}) = {atr_mean:.5f} price")

        for (sp, lp) in MA_PAIRS:
            for M in M_GRID:
                # 実測 cost_r: 往復コスト ÷ 平均1R (= 平均ATR × M)
                cost_r = COST_PRICE / (atr_mean * M)
                line = cost_r * 3.0
                for T in T_GRID:
                    net = run_backtest(bars, sp, lp, M, T)                 # 本番と同一
                    gross = run_backtest(bars, sp, lp, M, T, cost=0.0)     # コストのみ0
                    (_, _), (te_net, m_net) = split_oos(bars, net)
                    (_, _), (te_gro, m_gro) = split_oos(bars, gross)
                    s_net, s_gro = summarize(te_net, m_net), summarize(te_gro, m_gro)
                    rows.append({
                        "tf": tf, "short": sp, "long": lp, "M": M, "T": T,
                        "atr_mean": atr_mean, "cost_r": cost_r, "pass_line": line,
                        "net_avg_r": s_net["avg_r"], "net_pf": s_net["pf"],
                        "gross_avg_r": s_gro["avg_r"], "gross_pf": s_gro["pf"],
                        "n": s_net["n"],
                    })
                    print(f"  {tf} MA{sp}/{lp} M={M} T={T}: "
                          f"cost_r={cost_r:.4f} line={line:.4f} "
                          f"net={s_net['avg_r']:+.4f} gross={s_gro['avg_r']:+.4f}")
    mt5.shutdown()

    assert len(rows) == EXPECTED_TESTS, f"件数が違う: {len(rows)} != {EXPECTED_TESTS}"

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": {
            "note": "diagnostic only - the grid, the pass line and the verdict are unchanged",
            "symbol": sym, "cost_price": COST_PRICE,
            "generated": datetime.now(timezone.utc).isoformat(),
        }, "results": rows}, f, ensure_ascii=False, indent=2)

    best_g = max(rows, key=lambda r: r["gross_avg_r"])
    n_line_net = sum(1 for r in rows if r["net_avg_r"] >= r["pass_line"])
    n_line_gro = sum(1 for r in rows if r["gross_avg_r"] >= r["pass_line"])
    n_zero_gro = sum(1 for r in rows if r["gross_avg_r"] > 0)

    print("\n=== まとめ ===")
    print(f"  実測 cost_r の範囲: {min(r['cost_r'] for r in rows):.4f} 〜 "
          f"{max(r['cost_r'] for r in rows):.4f}")
    print(f"  本来の合格ライン  : {min(r['pass_line'] for r in rows):.4f} 〜 "
          f"{max(r['pass_line'] for r in rows):.4f}")
    print(f"  ネットでライン到達: {n_line_net} / {len(rows)}")
    print(f"  グロスでライン到達: {n_line_gro} / {len(rows)}   "
          f"← コストをゼロにしても、である")
    print(f"  グロスで avg_r > 0: {n_zero_gro} / {len(rows)}")
    print(f"  グロス最良: {best_g['gross_avg_r']:+.4f}R "
          f"({best_g['tf']} MA{best_g['short']}/{best_g['long']} "
          f"M={best_g['M']} T={best_g['T']})  必要 {best_g['pass_line']:.4f}R  "
          f"= {100*best_g['gross_avg_r']/best_g['pass_line']:.1f}%")
    print(f"\n書き出し: {args.out}")
    print("🔴 判定は あなたの判定メモ のまま。これは敗因の特定であって再検定ではない。")


if __name__ == "__main__":
    main()
