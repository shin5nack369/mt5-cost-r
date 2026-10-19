import math

import pytest

from confirm_time import (annual_sharpe, months_from_sharpe, months_required, n_required,
                          sharpe_needed, simulated_power)


def test_n_required_matches_formula():
    z = 1.6448536 + 0.8416212
    assert n_required(0.1) == pytest.approx((z / 0.1) ** 2, rel=1e-6)   # 約618件
    assert n_required(0.0) == math.inf


def test_months_do_not_shrink_with_more_trades_at_same_sharpe():
    # 同じ年率シャープ 1.0 を、月10件（s 大）と月100件（s 小）で作る
    for rate in (10, 100):
        s = 1.0 / math.sqrt(12 * rate)
        assert annual_sharpe(s, rate) == pytest.approx(1.0)
        assert months_required(s, rate) == pytest.approx(months_from_sharpe(1.0))


def test_24_months_needs_sharpe_about_1_76():
    assert sharpe_needed(24) == pytest.approx(1.758, abs=1e-3)
    assert months_from_sharpe(1.758) == pytest.approx(24, abs=0.05)
    assert months_from_sharpe(0.5) == pytest.approx(297, abs=1)


def test_power_is_80_percent_at_n_required():
    s = 0.2
    n = math.ceil(n_required(s))                      # 155件
    assert simulated_power(s, n) == pytest.approx(0.80, abs=0.03)


def test_the_common_mistake_gives_only_50_percent():
    # よくある n = (1.645 / s)^2 は「期待される t が 1.645 に届くだけ」= 検出力 約5割
    s = 0.2
    n = math.ceil((1.645 / s) ** 2)                   # 68件
    assert simulated_power(s, n) == pytest.approx(0.50, abs=0.04)
