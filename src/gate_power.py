import numpy as np


def pf(r):
    g, l = r[r > 0].sum(), -r[r < 0].sum()
    return np.inf if l == 0 else g / l


def gate_power(trade_r, n=30, pf_min=1.0, reps=10000, seed=0):
    """n 件で PF >= pf_min を合格とする判定の、
    本物のときの合格率・偽物（優位ゼロ）のときの合格率・連続した n 件での不合格率 を返す"""
    r = np.asarray(trade_r, dtype=float)
    rng = np.random.default_rng(seed)
    real = np.array([pf(rng.choice(r, n)) for _ in range(reps)])
    zero = r - r.mean()                                  # 優位だけを取り除く（形はそのまま）
    fake = np.array([pf(rng.choice(zero, n)) for _ in range(reps)])
    roll = np.array([pf(r[i:i + n]) for i in range(len(r) - n + 1)])
    return {
        "本物が合格": np.mean(real >= pf_min),
        "偽物が合格": np.mean(fake >= pf_min),
        "連続n件で不合格": np.mean(roll < pf_min),
    }
