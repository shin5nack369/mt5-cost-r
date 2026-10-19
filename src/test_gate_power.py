"""gate_power.py の単体テスト（numpy だけで動く。pytest 不要）。

🔴 ここで一番見たいのは「測定不能を合格に丸めていないか」。
   通ることの確認より、落ちることの確認のほうが情報量がある。
"""
import math
import warnings

import numpy as np

from gate_power import gate_power, pf


# ---- pf ----------------------------------------------------------------

def test_pf_basic():
    assert pf(np.array([2.0, -1.0])) == 2.0
    assert pf(np.array([3.0, 1.0, -2.0])) == 2.0


def test_pf_zeros_do_not_change_ratio():
    assert pf(np.array([2.0, -1.0])) == pf(np.array([2.0, 0.0, -1.0, 0.0]))


def test_pf_wins_without_loss_is_inf():
    # 割る分母が本当に無い。これは inf でよい
    assert pf(np.array([1.0, 2.0])) == math.inf


def test_pf_all_zero_is_nan():
    # 🔴 利益も損失も無い＝PF は定義できない。inf（＝合格）に丸めてはいけない
    assert math.isnan(pf(np.array([0.0, 0.0, 0.0])))


def test_pf_empty_is_nan():
    # 🔴 取引0件を「PF 無限大」と言わない
    assert math.isnan(pf(np.array([])))


def test_nan_does_not_pass_the_gate():
    # 🔴 判定式に入れたとき、測定不能が合格側に回らないこと
    assert not (pf(np.array([0.0, 0.0])) >= 1.0)


# ---- gate_power --------------------------------------------------------

def _sample(win_rate, payoff, size, seed):
    rng = np.random.default_rng(seed)
    return np.where(rng.random(size) < win_rate, payoff, -1.0)


def test_deterministic_with_seed():
    r = _sample(0.35, 2.2, 400, seed=1)
    a = gate_power(r, n=30, reps=500, seed=7)
    b = gate_power(r, n=30, reps=500, seed=7)
    assert a == b


def test_strong_edge_is_detected():
    r = _sample(0.70, 2.2, 600, seed=2)          # 1件あたり +1.24R
    out = gate_power(r, n=30, reps=2000, seed=0)
    assert out["本物が合格"] > 0.95, out
    assert out["本物が合格"] - out["偽物が合格"] > 0.3, out


def test_no_edge_is_not_detected():
    # 🔴 「平均0で生成した」では足りない。600件なら標本平均は 0 からずれる（seed 3 で約 +0.06R）。
    #    gate_power が見ているのは**その取引リストに実際に乗っている優位**なので、
    #    ずれた分がそのまま「本物が合格」を押し上げてしまう。
    #    優位ゼロを測りたいなら、標本平均そのものを 0 にしてから渡すこと。
    rng = np.random.default_rng(3)
    r = rng.normal(0.0, 1.0, 600)
    r = r - r.mean()
    assert abs(float(r.mean())) < 1e-12
    out = gate_power(r, n=30, reps=2000, seed=0)
    assert abs(out["本物が合格"] - out["偽物が合格"]) < 0.02, out


def test_realized_edge_is_what_gets_measured():
    # 上の裏返し。標本平均を 0 にしないと、生成時の平均が 0 でも「本物」は通りやすくなる
    rng = np.random.default_rng(3)
    raw = rng.normal(0.0, 1.0, 600)
    assert float(raw.mean()) > 0.0
    out = gate_power(raw, n=30, reps=2000, seed=0)
    assert out["本物が合格"] > out["偽物が合格"], out


def test_short_input_reports_zero_windows_without_warning():
    # 🔴 n 件に満たない入力。以前はここで RuntimeWarning を出して黙って nan を返していた
    r = _sample(0.35, 2.2, 10, seed=4)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = gate_power(r, n=30, reps=100, seed=0)
    assert out["連続n件の窓数"] == 0, out
    assert math.isnan(out["連続n件で不合格"]), out
    assert [w for w in caught if issubclass(w.category, RuntimeWarning)] == []


def test_window_count_is_exact():
    r = _sample(0.35, 2.2, 100, seed=5)
    assert gate_power(r, n=30, reps=50, seed=0)["連続n件の窓数"] == 71


def test_empty_input_raises():
    try:
        gate_power(np.array([]), n=30, reps=10, seed=0)
    except ValueError:
        return
    raise AssertionError("空の入力は ValueError にすること")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  [OK] {name}")
    print("\n全て通過")
