"""confirm_time.py -- 売買の手法が「本物か」を確かめるのに、何件・何か月かかるかを出す。

前提（ここが崩れると数字も崩れる）:
- 1件ごとの損益（コスト後）が独立で、平均 m・標準偏差 sd の分布から出る
- 「平均 > 0」を片側 5% で確かめる。本物なら 80% の確率で確かめられる件数を求める
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist

_N = NormalDist()


def n_required(s: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """1件あたりの s = 平均 ÷ 標準偏差 から、必要な件数。"""
    if s <= 0:
        return math.inf
    z = _N.inv_cdf(1 - alpha) + _N.inv_cdf(power)
    return (z / s) ** 2


def months_required(s: float, trades_per_month: float, **kw) -> float:
    return n_required(s, **kw) / trades_per_month


def annual_sharpe(s: float, trades_per_month: float) -> float:
    """独立な売買なら、年率シャープ = s × √(年間の件数)。"""
    return s * math.sqrt(12 * trades_per_month)


def months_from_sharpe(sr: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """月数は年率シャープだけで決まる: 12 × z² ÷ SR²（件数は消える）。"""
    z = _N.inv_cdf(1 - alpha) + _N.inv_cdf(power)
    return 12 * z * z / sr ** 2


def sharpe_needed(months: float, alpha: float = 0.05, power: float = 0.80) -> float:
    z = _N.inv_cdf(1 - alpha) + _N.inv_cdf(power)
    return math.sqrt(12 * z * z / months)


def simulated_power(s: float, n: int, reps: int = 4000, alpha: float = 0.05, seed: int = 0) -> float:
    """本当に s の優位があるとき、n 件で「平均 > 0」を確かめられる割合（模擬）。"""
    rng = random.Random(seed)
    crit = _N.inv_cdf(1 - alpha)
    hit = 0
    for _ in range(reps):
        x = [rng.gauss(s, 1.0) for _ in range(n)]
        m = sum(x) / n
        sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
        hit += (m / (sd / math.sqrt(n))) > crit
    return hit / reps
