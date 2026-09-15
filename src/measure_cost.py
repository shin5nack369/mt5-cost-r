# -*- coding: utf-8 -*-
"""
measure_cost.py — 自分の口座の「実際の取引コスト」を測り、
その戦略が成立する時間足を確定する。

このリポジトリの入口。まずこれを走らせて、自分の口座で戦える時間足を確定する。

使い方:
    python measure_cost.py

    # 銘柄や口座条件を変える場合
    python measure_cost.py --symbol EURUSD --days 5 --commission-jpy 600

🔴 時刻について (2026-09-11 に踏んだ):
    MT5 が返す tick["time"] / rates["time"] は **サーバー時刻** であって UTC ではない。
    ブローカーのサーバーは GMT+2/+3 が多く、そのまま "UTC" と書くと 2〜3時間ずれる。
    このスクリプトは実測でオフセットを出し、両方の時刻を併記する。

なぜこれを測るか:
    スプレッドと手数料は「コスト」ではなく **制約** で、
    あなたの戦略が成立する時間足を先に決めてしまう。
    ネットの「平均スプレッド 0.2 pips」は最良条件の値であって、
    あなたが実際に約定する時間帯の値ではない。
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("MetaTrader5 パッケージが見つかりません。pip install MetaTrader5")


# ── 設定 ────────────────────────────────────────────────
TIMEFRAMES = [
    ("M5",  "TIMEFRAME_M5"),
    ("M15", "TIMEFRAME_M15"),
    ("M30", "TIMEFRAME_M30"),
    ("H1",  "TIMEFRAME_H1"),
    ("H4",  "TIMEFRAME_H4"),
    ("D1",  "TIMEFRAME_D1"),
]
SL_MULTS = [1.5, 2.0]     # 損切り = ATR(14) × この倍率
COST_R_RULE = 3.0         # avg_r >= cost_r × 3 を成立条件とする
ATR_BARS = 500
MAX_TICKS = 2_000_000


def die(msg):
    """握り潰さない。理由を出して止める。"""
    print(f"\n[ABORT] {msg}")
    try:
        print(f"        mt5.last_error() = {mt5.last_error()}")
    except Exception:
        pass
    mt5.shutdown()
    sys.exit(2)


def resolve_symbol(want: str) -> str:
    """
    ブローカーによって USDJPY / USDJPY.r / USDJPYm など名前が違う。
    完全一致 → 前方一致 の順で探す。見つからなければ候補を出して終了。
    """
    syms = mt5.symbols_get()
    if syms is None:
        die("symbols_get() が None を返した。")
    names = [s.name for s in syms]

    if want in names:
        return want

    cands = [n for n in names if n.upper().startswith(want.upper())]
    if len(cands) == 1:
        print(f"[i] '{want}' は見つからないので '{cands[0]}' を使います。")
        return cands[0]
    if len(cands) > 1:
        print(f"[i] '{want}' の候補が複数あります: {cands}")
        print(f"[i] 先頭の '{cands[0]}' を使います。違う場合は --symbol で明示してください。")
        return cands[0]

    die(f"'{want}' に該当する銘柄が見つかりません。"
        f"似た名前: {[n for n in names if want[:3].upper() in n.upper()][:20]}")


def atr(high, low, close, period=14):
    """ATR(14)。指標は必ず確定足から計算する。"""
    prev_close = close[:-1]
    h, l = high[1:], low[1:]
    tr = np.maximum.reduce([
        h - l,
        np.abs(h - prev_close),
        np.abs(l - prev_close),
    ])
    if len(tr) < period:
        return None
    # 単純移動平均版（Wilder でなく SMA。目安を出すだけなので十分）
    return float(np.mean(tr[-period:]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="USDJPY")
    ap.add_argument("--days", type=int, default=3, help="ティックを遡る日数")
    ap.add_argument("--commission-jpy", type=float, default=0.0,
                    help="1ロットあたりの往復手数料（口座通貨建て）。不明なら 0")
    args = ap.parse_args()

    if not mt5.initialize():
        die("mt5.initialize() に失敗。MT5端末が起動しているか確認してください。")

    sym = resolve_symbol(args.symbol)
    if not mt5.symbol_select(sym, True):
        die(f"symbol_select({sym}) に失敗。")

    info = mt5.symbol_info(sym)
    if info is None:
        die(f"symbol_info({sym}) が None。")

    digits = info.digits
    point = info.point
    # 3桁/5桁ブローカーでは 1 pip = 10 point
    pip = point * (10 if digits in (3, 5) else 1)

    # 価格1単位あたりの損益（1ロット・口座通貨）
    if info.trade_tick_size and info.trade_tick_value:
        value_per_price = info.trade_tick_value / info.trade_tick_size
    else:
        value_per_price = None

    print("=" * 70)
    print(f"  会場コスト実測: {sym}")
    print(f"  digits={digits}  point={point}  1pip={pip}")
    print(f"  計測日: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC / 過去 {args.days} 日")
    print("=" * 70)

    # ── 1. ティックからスプレッド分布 ────────────────────
    frm = datetime.now(timezone.utc) - timedelta(days=args.days)
    ticks = mt5.copy_ticks_from(sym, frm, MAX_TICKS, mt5.COPY_TICKS_ALL)

    if ticks is None:
        die("copy_ticks_from が None を返した（取得できなかった）。")
    if len(ticks) == 0:
        # 🔴 「0件だった」と「取得できなかった」を同じ扱いにしない
        die("ティックが 0 件。期間・銘柄・気配値表示を確認してください。")

    bid = np.array([t["bid"] for t in ticks], dtype=float)
    ask = np.array([t["ask"] for t in ticks], dtype=float)
    tsec = np.array([t["time"] for t in ticks], dtype=np.int64)

    ok = (bid > 0) & (ask > 0) & (ask >= bid)
    if not ok.any():
        die("有効なティックがありません（bid/ask がすべて 0 または逆転）。")

    sp = (ask - bid)[ok]
    hours = ((tsec[ok] // 3600) % 24)

    q = lambda p: float(np.quantile(sp, p))
    sp_med = q(0.50)
    sp_p75 = q(0.75)

    print(f"\n■ スプレッド分布（n={len(sp):,} ティック）")
    print(f"    平均   : {sp.mean()/pip:7.3f} pips")
    print(f"    中央値 : {sp_med/pip:7.3f} pips   ← 通常の約定")
    print(f"    75%点  : {sp_p75/pip:7.3f} pips   ← ここをコスト前提にする")
    print(f"    90%点  : {q(0.90)/pip:7.3f} pips")
    print(f"    最大   : {sp.max()/pip:7.3f} pips")

    # ── 2. 時間帯別（サーバー時刻。UTCではない） ──────────
    # 🔴 MT5 の time は **サーバー時刻**。最新ティックと現在UTCの差でオフセットを実測する。
    last_srv = int(tsec.max())
    now_utc = int(datetime.now(timezone.utc).timestamp())
    offset_h = round((last_srv - now_utc) / 3600)
    print(f"\n■ サーバー時刻のオフセット: UTC{offset_h:+d}（実測）")
    print(f"    最新ティック(サーバー) = {datetime.fromtimestamp(last_srv, timezone.utc):%Y-%m-%d %H:%M}")
    print(f"    現在(UTC)              = {datetime.fromtimestamp(now_utc, timezone.utc):%Y-%m-%d %H:%M}")
    print(f"    → 以降の『時』はすべて **サーバー時刻**。UTC と読み替えないこと。")

    print(f"\n■ 時間帯別スプレッド中央値（サーバー時刻 / pips）")
    meds = []
    for h in range(24):
        m = sp[hours == h]
        meds.append(float(np.median(m)) if len(m) else None)

    for lo in (0, 12):
        print("    srv :  " + " ".join(f"{h:>5d}" for h in range(lo, lo + 12)))
        print("    utc :  " + " ".join(f"{(h - offset_h) % 24:>5d}" for h in range(lo, lo + 12)))
        print("        : " + " ".join(
            (f"{meds[h]/pip:5.2f}" if meds[h] is not None else "    -") for h in range(lo, lo + 12)))

    base = float(np.median([m for m in meds if m is not None]))
    bad = [h for h, m in enumerate(meds) if m is not None and m > base * 2]
    if bad:
        print(f"\n    🔴 通常の2倍を超える時間帯: "
              + ", ".join(f"srv {h}時 (UTC {(h-offset_h)%24}時) = {meds[h]/pip:.2f}p" for h in bad))
        print("       この時間帯に発注する戦略は、平均値で計算すると全部外れます。")
    else:
        print("\n    通常の2倍を超える時間帯はありませんでした。")

    # ── 3. 手数料を price 単位へ ──────────────────────────
    comm_price = 0.0
    if args.commission_jpy > 0:
        if value_per_price is None:
            print("\n[!] tick_value/tick_size が取れないため手数料を換算できません。"
                  " スプレッドのみで計算します。")
        else:
            comm_price = args.commission_jpy / value_per_price

    total_cost = sp_p75 + comm_price
    print(f"\n■ 往復の実質コスト")
    print(f"    スプレッド(75%点) : {sp_p75/pip:7.3f} pips")
    print(f"    手数料            : {comm_price/pip:7.3f} pips"
          f"  ({args.commission_jpy:,.0f} /lot 往復)")
    print(f"    ──────────────────────────────")
    print(f"    実質コスト        : {total_cost/pip:7.3f} pips  ({total_cost:.5f} price)")

    # ── 4. 時間足ごとの cost_r ────────────────────────────
    print(f"\n■ 時間足ごとの cost_r = 実質コスト ÷ (ATR(14) × SL倍率)")
    print(f"    成立条件: avg_r >= cost_r × {COST_R_RULE:.0f}")
    print()
    print("    TF    ATR(14)      SL×1.5              SL×2.0")
    print("                    cost_r  要avg_r     cost_r  要avg_r")
    print("    " + "-" * 58)

    verdict = []
    for label, attr in TIMEFRAMES:
        tf = getattr(mt5, attr)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, ATR_BARS)
        if rates is None or len(rates) < 30:
            print(f"    {label:<5} 取得できず（バー不足）")
            continue
        a = atr(np.array([r["high"] for r in rates], dtype=float),
                np.array([r["low"] for r in rates], dtype=float),
                np.array([r["close"] for r in rates], dtype=float))
        if a is None or a <= 0:
            print(f"    {label:<5} ATR を計算できず")
            continue

        cells = []
        for m in SL_MULTS:
            cr = total_cost / (a * m)
            cells.append((cr, cr * COST_R_RULE))
        print(f"    {label:<5} {a/pip:7.1f}p  "
              f"{cells[0][0]:6.3f}  {cells[0][1]:6.2f}R    "
              f"{cells[1][0]:6.3f}  {cells[1][1]:6.2f}R")

        # SL×2.0 で 要avg_r <= 0.5R なら現実的、とみなす
        verdict.append((label, cells[1][1]))

    # ── 5. 結論 ──────────────────────────────────────────
    print()
    ok_tf = [lb for lb, need in verdict if need <= 0.5]
    if ok_tf:
        print(f"■ 結論: {sym} / この口座では **{ok_tf[0]} 以上** でないと成立しません。")
        print(f"         （SL=ATR×2.0 のとき、必要な平均利益が 0.5R 以下に収まる最小の時間足）")
    else:
        print(f"■ 結論: {sym} / この口座では、どの時間足でも必要な平均利益が 0.5R を超えます。")
        print(f"         口座種別（RAW等）を変えるか、この銘柄を諦めてください。")
    print()
    print("  ※ '要avg_r' は「コストを払ってなお勝つために必要な平均利益(R)」です。")
    print("    0.5R を超える時間足を選ぶと、戦略の良し悪し以前にコストで負けます。")

    mt5.shutdown()


if __name__ == "__main__":
    main()
