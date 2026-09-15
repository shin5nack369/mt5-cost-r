# -*- coding: utf-8 -*-
"""
backtest_engine.py — USDJPY ラウンドナンバー回帰のバックテスト

事前宣言 `templates/pre_declaration.md` に完全準拠。
格子・時間足・コスト・時間帯除外は、すべて宣言から取っている。**勝手に広げない。**

🔴 設計上の選択: 損益は **R単位** で測り、残高とロットを一切持たない。
   理由は事故予防。過去に「ロット計算が未来の残高を参照していて
   バックテストの数値が全部過大だった」ことがある。
   残高をループに持ち込まなければ、そのバグは構造的に起こりえない。

🔴 時刻: MT5 の rates["time"] は **サーバー時刻**（UTCではない）。
   時間帯の除外もサーバー時刻で行う。実運用のbotも同じ基準にすること。

使い方:
    python backtest_engine.py                # 全36検定
    python backtest_engine.py --selftest     # MT5なしでエンジンを検証
"""

import argparse
import itertools
import json
import sys
from datetime import datetime, timezone

import numpy as np

# ── 事前宣言から転記（ここを編集したら宣言も直すこと）─────────────
SYMBOL = "USDJPY"
TIMEFRAMES = ["M15", "M30"]
LEVEL_STEP = 0.50                 # 水準の刻み（円）
K_GRID = [0.15, 0.25, 0.40]       # 接近距離 = ATR × K
M_GRID = [1.5, 2.0]               # SL = ATR × M
T_GRID = [1.0, 1.5, 2.0]          # TP = 1R × T
COST_PRICE = 0.02700              # 往復実質コスト 2.700 pips（実測）
EXCLUDE_SERVER_HOURS = {0}        # サーバー時刻 0時台は発注しない（スプレッド5倍）
DATE_FROM = datetime(2023, 1, 1, tzinfo=timezone.utc)
DATE_TO = datetime(2026, 9, 10, tzinfo=timezone.utc)
OOS_SPLIT = datetime(2025, 9, 1, tzinfo=timezone.utc).timestamp()
ATR_PERIOD = 14
MAX_BARS_HELD = 500               # 保険。これを超えたら成行で閉じて記録する

EXPECTED_TESTS = len(K_GRID) * len(M_GRID) * len(T_GRID) * len(TIMEFRAMES)  # 36


# ══════════════════════════════════════════════════════════════
#  エンジン（MT5に依存しない。純関数。だから単体で検証できる）
# ══════════════════════════════════════════════════════════════

def atr_series(high, low, close, period=ATR_PERIOD):
    """
    atr[i] は バー i までの確定情報だけで計算される。
    atr[i] は high[i]/low[i] を含むので、**バー i のエントリー判定には atr[i-1] を使う**。
    """
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    ])
    out = np.full(n, np.nan)
    csum = np.cumsum(tr)
    out[period:] = (csum[period:] - csum[:-period]) / period
    return out


def nearest_level(price, step=LEVEL_STEP):
    return round(price / step) * step


def run_backtest(bars, K, M, T, cost=COST_PRICE,
                 exclude_hours=EXCLUDE_SERVER_HOURS, shift=0):
    """
    bars: dict of numpy arrays -- time(int sec, server), open, high, low, close
    shift: 先読み自己検査用。シグナルを shift バーずらす（本番は 0）

    戻り値: list[trade]。trade は R単位。残高もロットも持たない。
    """
    t, o, h, l, c = bars["time"], bars["open"], bars["high"], bars["low"], bars["close"]
    n = len(c)
    atr = atr_series(h, l, c)
    hours = (t // 3600) % 24

    trades = []
    i = ATR_PERIOD + 2
    while i < n:
        s = i - 1 - shift                     # シグナル元のバー（確定済み）
        if s < 1 or np.isnan(atr[s]):
            i += 1
            continue
        if hours[i] in exclude_hours:         # 会場が発注に適さない時間帯
            i += 1
            continue

        a = atr[s]                            # 🔴 atr[i] ではない
        zone = a * K
        lv_h, lv_l = nearest_level(h[s]), nearest_level(l[s])
        bear = c[s] < o[s]
        bull = c[s] > o[s]

        side = 0
        if abs(h[s] - lv_h) <= zone and bear and c[s] < lv_h:
            side = -1                          # 上から接近 → 売り
        elif abs(l[s] - lv_l) <= zone and bull and c[s] > lv_l:
            side = +1                          # 下から接近 → 買い

        if side == 0:
            i += 1
            continue

        entry = o[i]                           # 🔴 約定は必ずバー i の始値
        risk = a * M
        if risk <= 0:
            i += 1
            continue
        sl = entry - side * risk
        tp = entry + side * risk * T

        # ── 決済をバー単位で歩く ──
        exit_i, exit_px, reason = None, None, None
        for j in range(i, min(n, i + MAX_BARS_HELD)):
            hit_sl = (l[j] <= sl) if side > 0 else (h[j] >= sl)
            hit_tp = (h[j] >= tp) if side > 0 else (l[j] <= tp)
            if hit_sl and hit_tp:
                # 🔴 バー内の順序は分からない。有利な方を選ばない。
                exit_i, exit_px, reason = j, sl, "SL(同時)"
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

        pnl = side * (exit_px - entry) - cost   # コストは必ず引く
        trades.append({
            "entry_i": i, "exit_i": exit_i, "side": side,
            "entry": float(entry), "exit": float(exit_px),
            "r": float(pnl / risk), "reason": reason, "time": int(t[i]),
        })
        i = exit_i + 1                          # 同時保有は1本まで

    return trades


def summarize(trades, months):
    if not trades:
        return {"n": 0, "pf": None, "avg_r": None, "win_rate": None,
                "max_dd_r": None, "trades_per_month": 0.0, "total_r": 0.0,
                "pf_ci95": [None, None]}
    r = np.array([x["r"] for x in trades])
    win, loss = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))

    # PF の95%信頼区間（ブートストラップ1000回）
    rng = np.random.default_rng(20260911)
    boot = []
    for _ in range(1000):
        s = rng.choice(r, size=len(r), replace=True)
        w, lo = s[s > 0].sum(), -s[s < 0].sum()
        boot.append(w / lo if lo > 0 else np.inf)
    boot = np.array([b for b in boot if np.isfinite(b)])
    ci = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))] if len(boot) else [None, None]

    return {
        "n": int(len(r)),
        "pf": float(win / loss) if loss > 0 else None,
        "avg_r": float(r.mean()),
        "win_rate": float((r > 0).mean()),
        "max_dd_r": dd,
        "trades_per_month": float(len(r) / months) if months > 0 else 0.0,
        "total_r": float(r.sum()),
        "pf_ci95": ci,
    }


# ══════════════════════════════════════════════════════════════
#  先読み自己検査
# ══════════════════════════════════════════════════════════════

def assert_no_lookahead(bars, trades):
    """検査に落ちたら結果を出さずに止める。警告を出して続行は禁止。"""
    fails = []

    # 1. 約定価格は必ずそのバーの open
    for tr in trades:
        if abs(tr["entry"] - bars["open"][tr["entry_i"]]) > 1e-12:
            fails.append(f"約定価格が open と違う (bar {tr['entry_i']})")
            break

    # 2. 決済バーはエントリーバー以降
    for tr in trades:
        if tr["exit_i"] < tr["entry_i"]:
            fails.append(f"決済バーがエントリーより前 (bar {tr['entry_i']})")
            break

    # 3. シグナルを1本ずらすと結果が変わること
    #    （変わらないなら、そもそも未来の情報を見ている疑い）
    base = run_backtest(bars, 0.25, 2.0, 1.5)
    sh = run_backtest(bars, 0.25, 2.0, 1.5, shift=1)
    if len(base) and len(sh):
        b = sum(x["r"] for x in base)
        s = sum(x["r"] for x in sh)
        if abs(b - s) < 1e-9:
            fails.append("シグナルを1本ずらしても結果が同一（先読みの疑い）")
    elif not base:
        fails.append("基準条件でトレードが0件（検査不能）")

    # 4. ATR が自分のバーを含んでいないか（atr[s] は close[s] までで決まる）
    a1 = atr_series(bars["high"], bars["low"], bars["close"])
    b2 = {k: v.copy() for k, v in bars.items()}
    b2["high"][-1] += 10.0          # 最終バーだけ壊す
    a2 = atr_series(b2["high"], b2["low"], b2["close"])
    if not np.allclose(a1[:-1], a2[:-1], equal_nan=True):
        fails.append("最終バーを変えたら過去の ATR が変わった（未来参照）")

    if fails:
        print("\n🔴 先読み検査に失敗しました。結果は出力しません。")
        for f in fails:
            print("   -", f)
        raise SystemExit(3)
    print("[OK] 先読み検査 4項目すべて通過")


# ══════════════════════════════════════════════════════════════
#  データ取得（MT5）
# ══════════════════════════════════════════════════════════════

def _abort(msg, mt5):
    """握り潰さない。診断材料を出して止める。"""
    print(f"\n[ABORT] {msg}")
    try:
        print(f"        last_error = {mt5.last_error()}")
        ti = mt5.terminal_info()
        if ti:
            print(f"        terminal   = build {ti.build} / connected={ti.connected} "
                  f"/ trade_allowed={ti.trade_allowed}")
        ai = mt5.account_info()
        if ai:
            print(f"        account    = {ai.login} @ {ai.server}")
    except Exception:
        pass
    raise SystemExit(2)


def ensure_symbol(mt5):
    """
    🔴 copy_rates_range は、銘柄が Market Watch に出ていないと
       (-2, 'Terminal: Invalid params') で落ちる。取得の前に必ず select する。
       2026-09-11 に実際に踏んだ。measure_cost.py には書いてあったのに、
       こちらに書き忘れていた。**同じ前処理を2箇所に書くとこうなる。**
    """
    syms = mt5.symbols_get()
    names = [x.name for x in syms] if syms else []
    name = SYMBOL if SYMBOL in names else next(
        (n for n in names if n.upper().startswith(SYMBOL.upper())), None)
    if name is None:
        _abort(f"'{SYMBOL}' に該当する銘柄がありません。"
               f" 似た名前: {[n for n in names if SYMBOL[:3].upper() in n.upper()][:20]}", mt5)
    if name != SYMBOL:
        print(f"[i] '{SYMBOL}' → '{name}' を使います。")
    if not mt5.symbol_select(name, True):
        _abort(f"symbol_select({name}) に失敗。Market Watch に出せません。", mt5)
    return name


def load_rates(mt5, sym, tf_name):
    """
    🔴 端末の maxbars（チャートの最大バー数）が取得の上限を決める（2026-09-11 実測）。
       この端末は maxbars=100000。99,999 は通り、100,000 以上は
       (-2, 'Terminal: Invalid params') で落ちる。

       copy_rates_range も同じ上限に当たる。ただし MT5 は**実際のバー数ではなく
       期間から計算した理論本数**で判定しているらしく、
       2023-01-01〜2026-09-10 の M15 は 1,348日 × 96本/日 = 129,408スロットとなり
       実バー約92,000本でも落ちる。1年（35,040）なら通る。

       そこで from_pos で maxbars-1 本を取り、**宣言の期間に切り詰める**。
       期間は宣言どおりのまま、取得方法だけが変わる。
    """
    tf = getattr(mt5, "TIMEFRAME_" + tf_name)
    ti = mt5.terminal_info()
    maxbars = getattr(ti, "maxbars", 0) or 100_000

    rates, used = None, None
    for cnt in (maxbars - 1, maxbars // 2, 50_000, 20_000):
        if cnt < 1000:
            continue
        r = mt5.copy_rates_from_pos(sym, tf, 0, cnt)
        if r is not None and len(r) > 0:
            rates, used = r, cnt
            break
        print(f"    [!] count={cnt:,} は不可 ({mt5.last_error()}) → 減らして再試行")

    if rates is None:
        _abort(f"{tf_name} のバーを取得できませんでした（count を下げても不可）。", mt5)

    t = np.array([r["time"] for r in rates], dtype=np.int64)
    raw_from = datetime.fromtimestamp(int(t[0]), timezone.utc)
    raw_to = datetime.fromtimestamp(int(t[-1]), timezone.utc)

    # ── 宣言の期間へ切り詰める ──
    # 時刻はサーバー時刻。境界での差は最大3時間程度で、3.7年の窓に対しては無視できる。
    lo, hi = DATE_FROM.timestamp(), DATE_TO.timestamp()
    m = (t >= lo) & (t <= hi)
    if m.sum() < 1000:
        _abort(f"{tf_name}: 宣言の期間に入るバーが {int(m.sum())} 本しかありません。", mt5)

    bars = {
        "time": t[m],
        "open": np.array([r["open"] for r in rates], dtype=float)[m],
        "high": np.array([r["high"] for r in rates], dtype=float)[m],
        "low": np.array([r["low"] for r in rates], dtype=float)[m],
        "close": np.array([r["close"] for r in rates], dtype=float)[m],
    }
    t0 = datetime.fromtimestamp(int(bars["time"][0]), timezone.utc)
    t1 = datetime.fromtimestamp(int(bars["time"][-1]), timezone.utc)

    meta = {
        "how": f"copy_rates_from_pos(count={used:,}) → 宣言期間に切り詰め",
        "maxbars": maxbars,
        "fetched": len(rates),
        "fetched_from": raw_from.strftime("%Y-%m-%d"),
        "bars": int(m.sum()),
        "from": t0.strftime("%Y-%m-%d"),
        "to": t1.strftime("%Y-%m-%d"),
    }

    # 宣言の開始日に届いていなければ、期間短縮として**記録して**進む
    if t0.timestamp() > lo + 86400 * 7:
        print(f"    [!] 宣言の開始日 {DATE_FROM:%Y-%m-%d} に届かず {meta['from']} から。"
              f" **期間短縮として記録します。**")
        meta["shortened"] = True

    return bars, meta


def split_oos(bars, trades):
    tr_train = [t for t in trades if t["time"] < OOS_SPLIT]
    tr_test = [t for t in trades if t["time"] >= OOS_SPLIT]
    span = lambda a, b: max((b - a) / (86400 * 30.44), 1e-9)
    t0, t1 = bars["time"][0], bars["time"][-1]
    return (tr_train, span(t0, OOS_SPLIT)), (tr_test, span(OOS_SPLIT, t1))


# ══════════════════════════════════════════════════════════════
#  セルフテスト（MT5なしでエンジンを検証する）
# ══════════════════════════════════════════════════════════════

def _bars_from(seq, start_ts=1_672_531_200, wig=0.004):
    """open/close の列から OHLC バーを作る。wig はスカラーでもバー毎の配列でも可。"""
    o = np.array(seq[:-1], dtype=float)
    c = np.array(seq[1:], dtype=float)
    w = np.full(len(o), float(wig)) if np.isscalar(wig) else np.asarray(wig, dtype=float)
    assert len(w) == len(o), f"wig の長さが違う: {len(w)} != {len(o)}"
    return {
        "time": np.arange(len(o), dtype=np.int64) * 900 + start_ts,
        "open": o, "close": c,
        "high": np.maximum(o, c) + w,
        "low": np.minimum(o, c) - w,
    }


def _warmup(base=150.20, k=40, amp=0.05):
    """ATR を立ち上げるためのジグザグ。水準から離した場所で振動させる。"""
    out = []
    for i in range(k):
        out.append(base + (amp if i % 2 else -amp))
    return out


def selftest():
    print("=== エンジン単体検証（合成データ / MT5不要）===\n")
    ok = lambda msg: print(f"  [OK] {msg}")

    # ── 1. 決定的ケース: 売りシグナル → TP に届く ──────────────
    #  150.00 に上から接近して陰線で確定 → 翌バー始値で売り → 下落して TP
    seq = _warmup() + [150.20, 150.01, 149.98, 149.70, 149.40, 149.10, 148.80, 148.50]
    b = _bars_from(seq)
    tr = run_backtest(b, K=0.40, M=2.0, T=1.5, cost=0.0, exclude_hours=set())
    assert tr, "決定的ケースでシグナルが出ない"
    t0 = tr[0]
    assert t0["side"] == -1, f"方向が売りでない: {t0['side']}"
    assert t0["reason"] == "TP", f"TP に届くはずが {t0['reason']}"
    assert abs(t0["r"] - 1.5) < 1e-6, f"TP の R が 1.5 でない: {t0['r']}"
    ok(f"売り→TP: r={t0['r']:.3f} reason={t0['reason']}")

    # ── 2. 決定的ケース: 逆行して SL ────────────────────────────
    seq = _warmup() + [150.20, 150.01, 149.98, 150.30, 150.60, 150.90, 151.20]
    b = _bars_from(seq)
    tr = run_backtest(b, K=0.40, M=2.0, T=1.5, cost=0.0, exclude_hours=set())
    assert tr and tr[0]["reason"] == "SL", f"SL のはずが {tr[0]['reason'] if tr else 'なし'}"
    assert abs(tr[0]["r"] + 1.0) < 1e-6, f"SL の R が -1.0 でない: {tr[0]['r']}"
    ok(f"売り→SL: r={tr[0]['r']:.3f}")

    # ── 3. コストは必ず R から引かれる ──────────────────────────
    seq = _warmup() + [150.20, 150.01, 149.98, 149.70, 149.40, 149.10, 148.80, 148.50]
    b = _bars_from(seq)
    t_free = run_backtest(b, 0.40, 2.0, 1.5, cost=0.0, exclude_hours=set())[0]
    t_cost = run_backtest(b, 0.40, 2.0, 1.5, cost=COST_PRICE, exclude_hours=set())[0]
    assert t_cost["r"] < t_free["r"], "コストを入れても R が変わらない"
    ok(f"コスト反映: {t_free['r']:.4f} → {t_cost['r']:.4f}")

    # ── 4. 同一バーで SL と TP の両方に触れたら SL ──────────────
    #    ATR は細いバーで確定させ、**決済側のバーだけ**ヒゲを極端に広げる。
    #    （全バーを太くすると ATR ごと太り、SL/TP が届かず TIMEOUT になる）
    seq = _warmup() + [150.20, 150.01, 149.98, 149.99, 149.99]
    wig = np.full(len(seq) - 1, 0.004)
    wig[-2:] = 0.60                        # エントリー直後のバーだけ両側に触れさせる
    b = _bars_from(seq, wig=wig)
    tr = run_backtest(b, 0.40, 2.0, 1.5, cost=0.0, exclude_hours=set())
    assert tr and tr[0]["reason"].startswith("SL"), \
        f"同時ヒットは SL のはずが {tr[0]['reason'] if tr else 'なし'}"
    ok(f"同一バー同時ヒット → {tr[0]['reason']}（有利な方を選んでいない）")

    # ── 5. 時間帯除外が効く ─────────────────────────────────────
    rng = np.random.default_rng(7)
    walk = 150.0 + np.cumsum(rng.normal(0, 0.03, 20001))   # 素直なランダムウォーク
    bw = _bars_from(walk, wig=0.012)
    n_all = len(run_backtest(bw, 0.25, 2.0, 1.5, exclude_hours=set()))
    n_half = len(run_backtest(bw, 0.25, 2.0, 1.5, exclude_hours=set(range(12))))
    assert 0 < n_half < n_all, f"時間帯除外が効いていない ({n_half}/{n_all})"
    ok(f"時間帯除外: {n_all} → {n_half} 件")

    # ── 6. 先読み検査 ───────────────────────────────────────────
    trades = run_backtest(bw, 0.25, 2.0, 1.5)
    assert len(trades) > 50, f"ランダムウォークでトレードが少なすぎる ({len(trades)})"
    assert_no_lookahead(bw, trades)

    # ── 7. 参考統計（ランダムウォーク＝優位性ゼロのはず）────────
    s = summarize(trades, months=12.0)
    print(f"\n  参考: ランダムウォーク上での結果 "
          f"n={s['n']} PF={s['pf']:.3f} avg_r={s['avg_r']:+.4f} "
          f"win={s['win_rate']:.1%} maxDD={s['max_dd_r']:.1f}R")
    print(f"        PF 95%CI = [{s['pf_ci95'][0]:.3f}, {s['pf_ci95'][1]:.3f}]")
    print("        ※ 優位性の無い系列なので、コスト分だけ負けるのが正常です。")
    print("        ※ ここで PF が明らかに 1 を超えるなら、エンジンを疑ってください。")
    if s["pf"] is not None and s["pf"] > 1.20:
        raise SystemExit("🔴 ランダムウォークで PF>1.20。エンジンに優位性が混入しています。")

    print("\n[OK] エンジンの単体検証 7項目すべて通過しました。")
    print("     ※ これは実データの検証ではありません。実行は本番モードで。")


# ══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default="results_engine.json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"[ABORT] mt5.initialize 失敗: {mt5.last_error()}")
        raise SystemExit(2)

    sym = ensure_symbol(mt5)

    results = []
    data_meta = {}
    grid = list(itertools.product(TIMEFRAMES, K_GRID, M_GRID, T_GRID))
    assert len(grid) == EXPECTED_TESTS, (
        f"検定数が宣言と違う: {len(grid)} != {EXPECTED_TESTS}")
    print(f"総検定数 {len(grid)}（事前宣言どおり）\n")

    for tf in TIMEFRAMES:
        bars, dm = load_rates(mt5, sym, tf)
        data_meta[tf] = dm
        print(f"[{tf}] バー {dm['bars']:,} 本 "
              f"({dm['from']} 〜 {dm['to']} サーバー時刻) 経路={dm['how']}")

        # 🔴 各時間足で1度だけ、先読み検査を通す
        assert_no_lookahead(bars, run_backtest(bars, 0.25, 2.0, 1.5))

        for K, M, T in itertools.product(K_GRID, M_GRID, T_GRID):
            idx = len(results) + 1
            trades = run_backtest(bars, K, M, T)
            (tr, m_tr), (te, m_te) = split_oos(bars, trades)
            row = {
                "tf": tf, "K": K, "M": M, "T": T,
                "train": summarize(tr, m_tr),
                "test": summarize(te, m_te),
            }
            results.append(row)
            s = row["test"]
            print(f"  {idx:2d}/{len(grid)}  {tf} K={K} M={M} T={T}  "
                  f"test: n={s['n']:4d} "
                  f"PF={s['pf'] if s['pf'] is None else round(s['pf'],3)} "
                  f"avg_r={s['avg_r'] if s['avg_r'] is None else round(s['avg_r'],4)}")
            # 途中で落ちてもここまでが残るように毎回書く
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"meta": {
                    "symbol": sym, "data": data_meta, "cost_price": COST_PRICE,
                    "exclude_server_hours": sorted(EXCLUDE_SERVER_HOURS),
                    "oos_split": "2025-09-01", "generated": datetime.now(timezone.utc).isoformat(),
                }, "results": results}, f, ensure_ascii=False, indent=2)

    mt5.shutdown()
    print(f"\n完了。{args.out} に {len(results)} 件を書きました。")
    print("🔴 ここで結果を見る前に、事前宣言 §4 のゲートが埋まっていることを確認すること。")


if __name__ == "__main__":
    main()
