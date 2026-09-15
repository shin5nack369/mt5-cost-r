# -*- coding: utf-8 -*-
"""
dryrun_wiring.py — 偽の MetaTrader5 で 06 の main() を最後まで通す「配線検査」。

🔴 なぜ要るか (2026-09-15 に踏んだ):
   06 の selftest はエンジン (run_backtest / assert_no_lookahead / summarize) を
   合成データで7項目検証する。**しかし main() を一度も呼ばない。**
   そのため main() の中の

       bars, months = load_rates(...)      # 実際は (bars, meta_dict)
       tr_in, tr_out = split_oos(...)      # 実際は ((tr,m),(te,m))
       summarize(tr, months)               # months に dict を渡していた

   という受け渡しミスを selftest は 1つも捕まえられず、
   STEP 1 が全通過したまま STEP 2 が即死し、results.json が
   1バイトも書かれない状態になった。

   検査していたのは「エンジンが正しいか」だけで、
   「エンジンの呼び方が正しいか」は誰も見ていなかった。

   このファイルはそこだけを見る。数字の意味は一切見ない。
   MT5 も相場も要らないので、STEP 2 の前に必ず通す。

使い方:
    python dryrun_wiring.py
"""

import importlib.util
import json
import os
import sys
import tempfile
import types
from datetime import datetime, timezone

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))


class _Sym:
    def __init__(self, name):
        self.name = name


class _TerminalInfo:
    maxbars = 100_000


def _synth(tf_sec, n, start_year=2022):
    """ランダムウォークの OHLC。相場としての意味は無い（配線だけ見る）。"""
    rng = np.random.default_rng(42)
    start = int(datetime(start_year, 6, 1, tzinfo=timezone.utc).timestamp())
    t = np.arange(n, dtype=np.int64) * tf_sec + start
    c = 140.0 + np.cumsum(rng.normal(0, 0.03, n))
    o = np.concatenate([[c[0]], c[:-1]])
    hi = np.maximum(o, c) + 0.02
    lo = np.minimum(o, c) - 0.02
    return [{"time": int(t[i]), "open": o[i], "high": hi[i],
             "low": lo[i], "close": c[i]} for i in range(n)]


def install_fake_mt5():
    """本番と同じ期間（2023-01〜2026-09）をまたぐ長さにする。
       こうしないと OOS の test 側が全部 n=0 になり、
       test 側の受け渡しミスを見逃す。"""
    # M15: 4年分 ≒ 140,000 本、M30 はその半分。maxbars で切られる挙動も再現される。
    m15 = _synth(900, 140_000)
    m30 = _synth(1800, 70_000)

    m = types.ModuleType("MetaTrader5")
    m.TIMEFRAME_M15 = 15
    m.TIMEFRAME_M30 = 30
    m.initialize = lambda *a, **k: True
    m.shutdown = lambda: None
    m.last_error = lambda: (-2, "Terminal: Invalid params")
    m.terminal_info = lambda: _TerminalInfo()
    m.symbols_get = lambda: [_Sym("USDJPY")]
    m.symbol_select = lambda name, on: True

    def copy_rates_from_pos(sym, tf, pos, cnt):
        # 🔴 本物と同じく maxbars 以上は None を返す
        if cnt >= _TerminalInfo.maxbars:
            return None
        src = m15 if tf == m.TIMEFRAME_M15 else m30
        return src[-min(cnt, len(src)):]

    m.copy_rates_from_pos = copy_rates_from_pos
    sys.modules["MetaTrader5"] = m
    return m


def main():
    install_fake_mt5()

    out = os.path.join(tempfile.gettempdir(), "dryrun_results.json")
    sys.argv = ["06_dryrun_wiring", "--out", out]

    spec = importlib.util.spec_from_file_location(
        "signal_ma_cross", os.path.join(_HERE, "signal_ma_cross.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    print("=== 配線検査: 偽 MT5 で main() を最後まで通す ===\n")
    mod.main()

    with open(out, encoding="utf-8") as f:
        d = json.load(f)

    print("\n=== 検査 ===")
    n = len(d["results"])
    assert n == mod.EXPECTED_TESTS, f"件数が宣言と違う: {n} != {mod.EXPECTED_TESTS}"
    print(f"  [OK] results 件数 = {n} (宣言どおり)")

    need = {"n", "pf", "avg_r", "win_rate", "max_dd_r", "trades_per_month"}
    for row in d["results"]:
        for side in ("train", "test"):
            s = row[side]
            missing = need - set(s)
            assert not missing, f"{side} に欠けているキー: {missing}"
            tpm = s["trades_per_month"]
            assert isinstance(tpm, (int, float)), \
                f"trades_per_month が数値でない: {type(tpm)} — months に dict を渡していないか"
    print("  [OK] train/test とも summarize の戻り値が揃っている")
    print("  [OK] trades_per_month は数値 (months に meta dict を渡していない)")

    n_test = sum(1 for r in d["results"] if r["test"]["n"] > 0)
    assert n_test > 0, "test 側が全部 n=0。OOS 分割の受け渡しを検査できていない。"
    print(f"  [OK] test 側にトレードのある格子点が {n_test}/{n} ある (OOS 分割が生きている)")

    for k in ("symbol", "data", "cost_price", "exclude_server_hours", "expected_tests"):
        assert k in d["meta"], f"meta に {k} が無い"
    print("  [OK] meta が揃っている")

    print("\n[OK] 配線検査を通過。STEP 2 (本番 MT5) に進んでよい。")
    print("     ※ これは相場の検証ではない。数字の意味は一切見ていない。")


if __name__ == "__main__":
    main()
