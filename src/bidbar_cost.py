"""bidbar_cost.py -- bid の足で測った損益から、実際の損益に直すための最小の道具。

- MT5 のローソク足は bid（売値）でできている。
- 買い: ask で入り bid で出る  -> 払うのは「入る足」のスプレッド1回
- 売り: bid で入り ask で出る  -> 払うのは「出る足」のスプレッド1回
- 持ち越し（スワップ）は、払う側だけを数える。3倍の曜日も数える。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Bar:
    """MT5 の足1本（bid の OHLC と、その足のスプレッド[points]）。"""
    time: datetime
    open: float
    close: float
    spread_pts: int


def bid_pnl(side: str, entry: float, exit_: float) -> float:
    """bid の値だけで測った損益（価格の単位）。"""
    if side == "long":
        return exit_ - entry
    if side == "short":
        return entry - exit_
    raise ValueError(side)


def spread_cost(side: str, entry_bar: Bar, exit_bar: Bar, point: float,
                median_spread_pts: float = 0.0, n_spreads: float = 1.0) -> float:
    """往復のスプレッドのコスト（価格の単位）。

    払う側の足のスプレッドと、長い期間の中央値の大きい方を使う
    （足のスプレッドが 0 と記録される足への保険）。
    n_spreads=2.0 はストレス用。基準は 1.0。
    """
    paying = entry_bar if side == "long" else exit_bar
    return n_spreads * max(float(paying.spread_pts), median_spread_pts) * point


def rollovers(entry: datetime, exit_: datetime, triple_weekday_mt5: int) -> int:
    """entry から exit_ までにまたいだ日付の変わり目を、3倍の曜日込みで数える。

    時刻はブローカーのサーバー時間。triple_weekday_mt5 は MT5 の
    swap_rollover3days（0=日曜 ... 6=土曜）。
    日付の変わり目で閉じる日の曜日が triple_weekday_mt5 なら 3 と数える。
    """
    if exit_ <= entry:
        return 0
    n = 0
    midnight = datetime(entry.year, entry.month, entry.day) + timedelta(days=1)
    while midnight <= exit_:
        closing_day = midnight - timedelta(days=1)
        mt5_weekday = (closing_day.weekday() + 1) % 7  # Python は 月=0、MT5 は 日=0
        n += 3 if mt5_weekday == triple_weekday_mt5 else 1
        midnight += timedelta(days=1)
    return n


def swap_cost(side: str, nights: int, swap_mode: int, swap_long: float,
              swap_short: float, price: float, point: float) -> float:
    """持ち越しで「払う」分（価格の単位、0 以上）。受け取る分は数えない。

    swap_mode 1: points（1泊あたり swap × point）
    swap_mode 5: 年率 %、360日割り（1泊あたり |swap|/100/360 × 価格）
    """
    s = swap_long if side == "long" else swap_short
    if s >= 0 or nights <= 0:
        return 0.0
    if swap_mode == 1:
        per_night = -s * point
    elif swap_mode == 5:
        per_night = -s / 100.0 / 360.0 * price
    else:
        raise NotImplementedError("swap_mode %d" % swap_mode)
    return nights * per_night


def net_pnl(side: str, entry_bar: Bar, exit_bar: Bar, point: float,
            median_spread_pts: float, swap: dict, n_spreads: float = 1.0) -> float:
    """入る足・出る足の始値で売買したときの、コストとスワップを引いた損益。"""
    gross = bid_pnl(side, entry_bar.open, exit_bar.open)
    cost = spread_cost(side, entry_bar, exit_bar, point, median_spread_pts, n_spreads)
    nights = rollovers(entry_bar.time, exit_bar.time, swap["triple_weekday_mt5"])
    sw = swap_cost(side, nights, swap["mode"], swap["long"], swap["short"],
                   entry_bar.open, point)
    return gross - cost - sw
