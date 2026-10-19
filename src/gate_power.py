import numpy as np


def pf(r):
    """プロフィットファクター。

    🔴 損失が無いときに常に inf を返さない。
    - 利益があって損失が無い  : inf（本当に割る分母が無い）
    - 取引が無い / 全て 0     : nan（**測定不能**。合格側に丸めない）
    """
    r = np.asarray(r, dtype=float)
    g, l = r[r > 0].sum(), -r[r < 0].sum()
    if l == 0:
        return np.inf if g > 0 else np.nan
    return g / l


def gate_power(trade_r, n=30, pf_min=1.0, reps=10000, seed=0):
    """n 件で PF >= pf_min を合格とする判定の、
    本物のときの合格率・偽物（優位ゼロ）のときの合格率・連続した n 件での不合格率 を返す

    🔴 trade_r が n 件未満のときは「連続n件」の窓が1つも作れない。
    その場合は nan を返し、窓数も一緒に返す（黙って nan にしない）。
    """
    r = np.asarray(trade_r, dtype=float)
    if r.size == 0:
        raise ValueError("trade_r が空です")
    rng = np.random.default_rng(seed)
    real = np.array([pf(rng.choice(r, n)) for _ in range(reps)])
    zero = r - r.mean()                                  # 優位だけを取り除く（形はそのまま）
    fake = np.array([pf(rng.choice(zero, n)) for _ in range(reps)])

    windows = max(0, r.size - n + 1)
    if windows == 0:
        roll_fail = float("nan")
    else:
        roll = np.array([pf(r[i:i + n]) for i in range(windows)])
        roll_fail = float(np.mean(roll < pf_min))

    return {
        "本物が合格": float(np.mean(real >= pf_min)),
        "偽物が合格": float(np.mean(fake >= pf_min)),
        "連続n件で不合格": roll_fail,
        "連続n件の窓数": windows,
    }
