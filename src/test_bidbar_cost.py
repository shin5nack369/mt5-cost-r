import random
from datetime import datetime, timedelta

import pytest

from bidbar_cost import Bar, bid_pnl, net_pnl, rollovers, spread_cost, swap_cost

POINT = 0.01


def _quotes(n=500, seed=0):
    """bid と ask の組を作る。スプレッドは足ごとに変わる。"""
    rng = random.Random(seed)
    t0 = datetime(2026, 9, 21, 0, 0)
    bid, out = 60000.0, []
    for i in range(n):
        bid += rng.gauss(0, 30)
        sp_pts = rng.randint(1500, 4000)  # 15〜40 ドル
        out.append(Bar(t0 + timedelta(minutes=30 * i), round(bid, 2), round(bid, 2), sp_pts))
    return out


def _real(side, eb, xb):
    """実際の約定: 買いは ask で入り bid で出る。売りは bid で入り ask で出る。"""
    ask = lambda b: b.open + b.spread_pts * POINT
    return (xb.open - ask(eb)) if side == "long" else (eb.open - ask(xb))


@pytest.mark.parametrize("side", ["long", "short"])
def test_one_spread_matches_real_fills(side):
    bars = _quotes()
    rng = random.Random(1)
    for _ in range(200):
        i = rng.randrange(0, 400)
        j = i + rng.randrange(1, 40)
        eb, xb = bars[i], bars[j]
        est = bid_pnl(side, eb.open, xb.open) - spread_cost(side, eb, xb, POINT)
        assert est == pytest.approx(_real(side, eb, xb), abs=1e-6)


@pytest.mark.parametrize("side", ["long", "short"])
def test_two_spreads_overcounts_by_the_other_side(side):
    bars = _quotes()
    eb, xb = bars[10], bars[30]
    both = (eb.spread_pts + xb.spread_pts) * POINT  # 入口+出口（よくある数え方）
    est2 = bid_pnl(side, eb.open, xb.open) - both
    other = xb if side == "long" else eb  # 払っていない側の足
    assert _real(side, eb, xb) - est2 == pytest.approx(other.spread_pts * POINT)


def test_median_floor_for_zero_spread_bar():
    eb = Bar(datetime(2026, 9, 21), 100.0, 100.0, 0)
    xb = Bar(datetime(2026, 9, 21, 1), 101.0, 101.0, 0)
    assert spread_cost("long", eb, xb, POINT, median_spread_pts=25) == pytest.approx(0.25)
    assert spread_cost("long", eb, xb, POINT, 25, n_spreads=2.0) == pytest.approx(0.50)


def test_rollovers_with_triple_day():
    # 2026-09-23 は水曜。MT5 の水曜 = 3
    wed_2300 = datetime(2026, 9, 23, 23, 0)
    thu_0100 = datetime(2026, 9, 24, 1, 0)
    assert rollovers(wed_2300, thu_0100, triple_weekday_mt5=3) == 3
    assert rollovers(wed_2300, thu_0100, triple_weekday_mt5=5) == 1
    # 日をまたがない
    assert rollovers(datetime(2026, 9, 23, 1), datetime(2026, 9, 23, 22), 3) == 0
    # 月曜 12:00 -> 金曜 12:00 = 月火水木 の4回、水曜が3倍 -> 6
    assert rollovers(datetime(2026, 9, 21, 12), datetime(2026, 9, 25, 12), 3) == 6


def test_swap_only_counts_payments():
    # mode 5: 年 -8.33% / 360、価格 60,000 -> 1泊 約13.88 ドル
    assert swap_cost("long", 1, 5, -8.33, 0.0, 60000.0, POINT) == pytest.approx(13.8833, rel=1e-4)
    assert swap_cost("short", 3, 5, -8.33, 0.0, 60000.0, POINT) == 0.0
    # mode 1: points
    assert swap_cost("long", 2, 1, -79.48, 34.41, 3500.0, POINT) == pytest.approx(1.5896)
    assert swap_cost("short", 2, 1, -79.48, 34.41, 3500.0, POINT) == 0.0


def test_net_pnl_end_to_end():
    eb = Bar(datetime(2026, 9, 23, 20), 60000.0, 60000.0, 2500)
    xb = Bar(datetime(2026, 9, 24, 2), 60300.0, 60300.0, 3000)
    sw = {"mode": 5, "long": -8.33, "short": 0.0, "triple_weekday_mt5": 3}
    # 粗利 300 - 入口のスプレッド 25 - 水曜の3泊分 約41.65
    assert net_pnl("long", eb, xb, POINT, 0.0, sw) == pytest.approx(300 - 25 - 3 * 13.8833, rel=1e-4)
    # 売り: 粗利 -300 - 出口のスプレッド 30、スワップは 0
    assert net_pnl("short", eb, xb, POINT, 0.0, sw) == pytest.approx(-330.0)
