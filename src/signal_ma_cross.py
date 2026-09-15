# -*- coding: utf-8 -*-
"""
signal_ma_cross.py — 「ゴールデンクロスで買う」を 36 通り測る。

事前宣言: templates/pre_declaration.md (2026-09-15)
**宣言を書いてからこのファイルを書いた。順序を入れ替えないこと。**

🔴 エンジンは前回 (backtest_engine.py) を **import して再利用する**。
   コピペしない。理由は2つ:

   1. 前回のエンジンは先読み検査つきで7項目の単体検証を通っている。
      コピペすると「同じはずのもの」が2つになり、片方だけ直る日が来る
      (この環境が 2026-07-09 の v12 BT ロット先読みで踏んだ型)。
   2. 2本の検証結果を並べて読むとき、**差がシグナルの差だけである**ことを
      保証したい。エンジンが違えば比較は成立しない。

   したがってこのファイルが定義するのは **シグナルだけ** である。
   コスト・約定・決済・R換算・OOS分割・ゲートは一切触っていない。

使い方:
    python signal_ma_cross.py --selftest   # MT5不要
    python signal_ma_cross.py              # 本番 (MT5必要)
"""

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

# ── バックテストエンジンを読み込む ────────────────────────────
#  🔴 コピペしない。**同じはずのもの**が2つあると、片方だけ直る日が来る。
#     そしてシグナルAとシグナルBの結果を並べて読むとき、
#     差がシグナルの差だけであることを保証できなくなる。
import backtest_engine as _ENG

atr_series = _ENG.atr_series
summarize = _ENG.summarize
assert_no_lookahead = _ENG.assert_no_lookahead
split_oos = _ENG.split_oos
_bars_from = _ENG._bars_from
_warmup = _ENG._warmup


# ── 事前宣言から転記（ここを編集したら宣言も直すこと）─────────────
SYMBOL = _ENG.SYMBOL                      # USDJPY
TIMEFRAMES = _ENG.TIMEFRAMES              # ["M15", "M30"]
MA_PAIRS = [(5, 20), (10, 50), (20, 100)]  # (短期, 長期)
M_GRID = _ENG.M_GRID                      # [1.5, 2.0]  SL = ATR × M
T_GRID = _ENG.T_GRID                      # [1.0, 1.5, 2.0]  TP = 1R × T
COST_PRICE = _ENG.COST_PRICE              # 0.02700 (実測 2.700 pips)
EXCLUDE_SERVER_HOURS = _ENG.EXCLUDE_SERVER_HOURS   # {0}
ATR_PERIOD = _ENG.ATR_PERIOD
MAX_BARS_HELD = _ENG.MAX_BARS_HELD

EXPECTED_TESTS = len(MA_PAIRS) * len(M_GRID) * len(T_GRID) * len(TIMEFRAMES)  # 36


def sma(x, period):
    """単純移動平均。確定足だけで計算する (先読みしない)。"""
    out = np.full(len(x), np.nan)
    if len(x) < period:
        return out
    csum = np.cumsum(np.insert(np.asarray(x, dtype=float), 0, 0.0))
    out[period - 1:] = (csum[period:] - csum[:-period]) / period
    return out


def run_backtest(bars, short_p, long_p, M, T, cost=COST_PRICE,
                 exclude_hours=EXCLUDE_SERVER_HOURS, shift=0):
    """シグナルだけが前回と違う。約定も決済もコストも 04 と同じ扱い。

    shift: 先読み自己検査用。シグナルを shift バーずらす（本番は 0）
    """
    t, o, h, l, c = bars["time"], bars["open"], bars["high"], bars["low"], bars["close"]
    n = len(c)
    atr = atr_series(h, l, c)
    hours = (t // 3600) % 24
    ma_s = sma(c, short_p)
    ma_l = sma(c, long_p)

    trades = []
    i = max(ATR_PERIOD + 2, long_p + 2)
    while i < n:
        s = i - 1 - shift                  # シグナル元のバー（確定済み）
        if s < 1 or np.isnan(atr[s]) or np.isnan(ma_l[s]) or np.isnan(ma_l[s - 1]):
            i += 1
            continue
        if hours[i] in exclude_hours:
            i += 1
            continue

        a = atr[s]                         # 🔴 atr[i] ではない
        up = ma_s[s] > ma_l[s] and ma_s[s - 1] <= ma_l[s - 1]
        dn = ma_s[s] < ma_l[s] and ma_s[s - 1] >= ma_l[s - 1]

        side = 0
        if up:
            side = +1                      # ゴールデンクロス → 買い
        elif dn:
            side = -1                      # デッドクロス → 売り
        if side == 0:
            i += 1
            continue

        entry = o[i]                       # 🔴 約定は必ずバー i の始値
        risk = a * M
        if risk <= 0:
            i += 1
            continue
        sl = entry - side * risk
        tp = entry + side * risk * T

        exit_i, exit_px, reason = None, None, None
        for j in range(i, min(n, i + MAX_BARS_HELD)):
            hit_sl = (l[j] <= sl) if side > 0 else (h[j] >= sl)
            hit_tp = (h[j] >= tp) if side > 0 else (l[j] <= tp)
            if hit_sl and hit_tp:
                exit_i, exit_px, reason = j, sl, "SL(同時)"   # 有利な方を選ばない
                break
            if hit_sl:
                exit_i, exit_px, reason = j, sl, "SL"
                break
            if hit_tp:
                exit_i, exit_px, reason = j, tp, "TP"
                break
        if exit_i is None:
            exit_i = min(n - 1, i + MAX_BARS_HELD - 1)
            exit_px, reason = c[exit_i], "TIMEOUT"

        pnl = side * (exit_px - entry) - cost
        trades.append({
            "entry_i": i, "exit_i": exit_i, "side": side,
            "entry": float(entry), "exit": float(exit_px),
            "r": float(pnl / risk), "reason": reason, "time": int(t[i]),
        })
        i = exit_i + 1

    return trades


def selftest():
    print("=== エンジン単体検証（合成データ / MT5不要）===\n")
    ok = lambda msg: print(f"  [OK] {msg}")

    # 短期=3 長期=8 で試す。上げに転じればゴールデンクロスが必ず1回出る。
    SP, LP = 3, 8
    down = [150.00 - 0.02 * k for k in range(40)]     # 下げ続けて短期<長期にする
    up = [down[-1] + 0.06 * k for k in range(1, 26)]  # 上げに転じる

    # ── 1. 決定的ケース: ゴールデンクロス → 買い → TP ───────────
    b = _bars_from(down + up)
    tr = run_backtest(b, SP, LP, M=2.0, T=1.5, cost=0.0, exclude_hours=set())
    assert tr, "ゴールデンクロスでシグナルが出ない"
    t0 = tr[0]
    assert t0["side"] == +1, f"方向が買いでない: {t0['side']}"
    assert t0["reason"] == "TP", f"TP に届くはずが {t0['reason']}"
    assert abs(t0["r"] - 1.5) < 1e-6, f"TP の R が 1.5 でない: {t0['r']}"
    ok(f"GC→買い→TP: r={t0['r']:.3f}")

    # ── 2. 決定的ケース: クロス直後に逆行して SL ────────────────
    b = _bars_from(down + up[:3] + [up[2] - 0.30 * k for k in range(1, 12)])
    tr = run_backtest(b, SP, LP, M=2.0, T=1.5, cost=0.0, exclude_hours=set())
    assert tr and tr[0]["reason"] == "SL", \
        f"SL のはずが {tr[0]['reason'] if tr else 'なし'}"
    assert abs(tr[0]["r"] + 1.0) < 1e-6, f"SL の R が -1.0 でない: {tr[0]['r']}"
    ok(f"GC→買い→SL: r={tr[0]['r']:.3f}")

    # ── 3. デッドクロスで売り側も出ること ────────────────────────
    b = _bars_from([150.00 + 0.02 * k for k in range(40)]
                   + [150.78 - 0.06 * k for k in range(1, 26)])
    tr = run_backtest(b, SP, LP, M=2.0, T=1.5, cost=0.0, exclude_hours=set())
    assert tr and tr[0]["side"] == -1, "デッドクロスで売りが出ない"
    ok(f"DC→売り: side={tr[0]['side']} reason={tr[0]['reason']}")

    # ── 4. コストは必ず R から引かれる ──────────────────────────
    b = _bars_from(down + up)
    t_free = run_backtest(b, SP, LP, 2.0, 1.5, cost=0.0, exclude_hours=set())[0]
    t_cost = run_backtest(b, SP, LP, 2.0, 1.5, cost=COST_PRICE, exclude_hours=set())[0]
    assert t_cost["r"] < t_free["r"], "コストを入れても R が変わらない"
    ok(f"コスト反映: {t_free['r']:.4f} → {t_cost['r']:.4f}")

    # ── 5. 時間帯除外が効く ─────────────────────────────────────
    rng = np.random.default_rng(7)
    walk = 150.0 + np.cumsum(rng.normal(0, 0.03, 20001))
    bw = _bars_from(walk, wig=0.012)
    n_all = len(run_backtest(bw, 10, 50, 2.0, 1.5, exclude_hours=set()))
    n_half = len(run_backtest(bw, 10, 50, 2.0, 1.5, exclude_hours=set(range(12))))
    assert 0 < n_half < n_all, f"時間帯除外が効いていない ({n_half}/{n_all})"
    ok(f"時間帯除外: {n_all} → {n_half} 件")

    # ── 6. 先読み検査 (04 と同じ関数をそのまま使う) ─────────────
    trades = run_backtest(bw, 10, 50, 2.0, 1.5)
    assert len(trades) > 50, f"ランダムウォークでトレードが少なすぎる ({len(trades)})"
    assert_no_lookahead(bw, trades)
    ok("先読み検査 (04 と同一の assert_no_lookahead)")

    # ── 7. ランダムウォーク＝優位性ゼロのはず ───────────────────
    s = summarize(trades, months=12.0)
    print(f"\n  参考: ランダムウォーク上での結果 "
          f"n={s['n']} PF={s['pf']:.3f} avg_r={s['avg_r']:+.4f} "
          f"win={s['win_rate']:.1%} maxDD={s['max_dd_r']:.1f}R")
    print("        ※ 優位性の無い系列なので、コスト分だけ負けるのが正常です。")
    if s["pf"] is not None and s["pf"] > 1.20:
        raise SystemExit("🔴 ランダムウォークで PF>1.20。エンジンに優位性が混入しています。")

    print("\n[OK] エンジンの単体検証 7項目すべて通過しました。")
    print("     ※ これは実データの検証ではありません。実行は本番モードで。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default="results.json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"[ABORT] mt5.initialize 失敗: {mt5.last_error()}")
        raise SystemExit(2)

    sym = _ENG.ensure_symbol(mt5)

    grid = [(tf, sp, lp, M, T)
            for tf in TIMEFRAMES
            for (sp, lp) in MA_PAIRS
            for M in M_GRID
            for T in T_GRID]
    assert len(grid) == EXPECTED_TESTS, (
        f"検定数が宣言と違う: {len(grid)} != {EXPECTED_TESTS}")
    print(f"総検定数 {len(grid)}（事前宣言どおり）\n")

    results = []
    data_meta = {}

    for tf in TIMEFRAMES:
        # 🔴 load_rates は (bars, meta_dict) を返す。meta は月数ではない。
        bars, dm = _ENG.load_rates(mt5, sym, tf)
        data_meta[tf] = dm
        print(f"[{tf}] バー {dm['bars']:,} 本 "
              f"({dm['from']} 〜 {dm['to']} サーバー時刻) 経路={dm['how']}")

        # 各時間足で1度だけ先読み検査を通す（04 と同じ関数）
        assert_no_lookahead(bars, run_backtest(bars, 10, 50, 2.0, 1.5))

        for (sp, lp) in MA_PAIRS:
            for M in M_GRID:
                for T in T_GRID:
                    idx = len(results) + 1
                    trades = run_backtest(bars, sp, lp, M, T)
                    # 🔴 split_oos は ((train, 月数), (test, 月数)) を返す
                    (tr, m_tr), (te, m_te) = split_oos(bars, trades)
                    row = {
                        "tf": tf, "short": sp, "long": lp, "M": M, "T": T,
                        "train": summarize(tr, m_tr),
                        "test": summarize(te, m_te),
                    }
                    results.append(row)
                    s = row["test"]
                    print(f"  {idx:2d}/{len(grid)}  {tf} MA{sp}/{lp} M={M} T={T}  "
                          f"test: n={s['n']:4d} "
                          f"PF={s['pf'] if s['pf'] is None else round(s['pf'], 3)} "
                          f"avg_r={s['avg_r'] if s['avg_r'] is None else round(s['avg_r'], 4)}")

                    # 途中で落ちてもここまでが残るように毎回書く（04 と同じ作法）
                    with open(args.out, "w", encoding="utf-8") as f:
                        json.dump({"meta": {
                            "symbol": sym,
                            "data": data_meta,
                            "cost_price": COST_PRICE,
                            "exclude_server_hours": sorted(EXCLUDE_SERVER_HOURS),
                            "ma_pairs": MA_PAIRS,
                            "expected_tests": EXPECTED_TESTS,
                            "oos_split": "2025-09-01",
                            "predeclaration": "templates/pre_declaration.md (2026-09-15)",
                            "generated": datetime.now(timezone.utc).isoformat(),
                        }, "results": results}, f, ensure_ascii=False, indent=2)

    mt5.shutdown()

    assert len(results) == EXPECTED_TESTS, \
        f"🔴 検定数が宣言と違う: {len(results)} != {EXPECTED_TESTS}"

    print(f"\n完了。{args.out} に {len(results)} 件を書きました。")
    print("🔴 結果を見る前に、事前宣言のゲート G1〜G8 と「通過0〜2件は通過と呼ばない」を読み直すこと。")


if __name__ == "__main__":
    main()
