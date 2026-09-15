# 事前宣言テンプレート / Pre-registration template

> **Fill this in and commit it BEFORE you run a single backtest.**
> The commit timestamp is the evidence. If you write it after seeing results,
> it is not a pre-registration — it is a rationalisation.
>
> **1行でも書き換えたくなったら、それは新しい着想です。**
> 今回の検定に足さず、日付を入れて別の宣言を書き直してください。

---

## 0. What am I measuring? / 何を測るのか

> One sentence. If it takes a paragraph, the idea is not yet a hypothesis.

```
例) 短期MAが長期MAを下から上に抜けたら買い、上から下に抜けたら売る。
    フィルターは足さない。素のクロスだけを測る。
```

---

## 1. The venue (already measured) / 会場（測定済み・所与）

> Run `measure_cost.py` first. These are inputs, not choices.

| Item | Value | Source |
|---|---|---|
| Symbol / 銘柄 | | |
| Round-trip cost / 往復実質コスト | `___ pips = ___ price` | measure_cost.py, n=___ ticks |
| Minimum viable timeframe / 成立する最小時間足 | | same |
| Excluded hours (server time) / 除外時間帯 | | same |

🔴 **MT5 `time` is SERVER time, not UTC.** Broker servers are usually GMT+2/+3.

---

## 2. The grid / 格子 — nothing outside this gets measured

```
param A   { ... }
param B   { ... }
param C   { ... }
timeframe { ... }

total = ___ tests
```

- Period / 期間:
- Train/test split / 学習・検証の分割:
- Entry / エントリー:
- Exit / 決済:

**Declare the test count.** Make the script `assert` that the number of results
equals the declared number. If you quietly widen the grid later, it stops there.

---

## 3. Pass line / 合格ライン

```
avg_r >= cost_r * 3
```

| Timeframe | cost_r | required avg_r |
|---|---|---|
| | | |

🔴 **Compute `cost_r` per trade, then average.** Computing it once from a mean ATR
understates the cost you actually pay — measured at **+39% to +47%** on USDJPY,
because the mean of reciprocals exceeds the reciprocal of the mean whenever ATR varies.

---

## 4. How many passes count as a pass? / 通過を何件から「通過」と呼ぶか

> **Decide this before you look.** This is the whole point of the document.

If a single test has a 5% chance of looking good by luck:

```
___ tests x 0.05 = ___ expected false positives
```

- **___ or fewer passes → not a pass.** Inside the noise.
- **Only if ___ or more pass at ADJACENT grid points** does it mean anything.
- **More than ___ passes → suspect a bug first.** In practice this happens more
  often than a real edge does.

---

## 5. Gates / ゲート — all must pass

| # | Condition | Reading when it fails |
|---|---|---|
| G1 | test trades >= 100 | Not enough sample. "Undecidable", not "good" |
| G2 | trades per month >= 5 | Too rare to validate in a lifetime |
| G3 | `avg_r >= cost_r * 3` | Below the speed limit |
| G4 | \|train avg_r - test avg_r\| <= 0.15R | Overfit |
| G5 | test PF > 1.0 | Loses out of sample |
| G6 | max drawdown <= 30R | Unsurvivable |
| G7 | drop the 2 best winners, avg_r still > 0 | Outlier-dependent |
| G8 | look-ahead assertions pass | Engine defect. **All results void** |

🔴 **Keep per-trade records in the results file**, or G7 cannot be computed afterwards.
(Learned the hard way: G7 was unevaluable because only summaries were kept.)

---

## 6. If it does not pass, what will I NOT do? / やらないこと

**If ___ or fewer pass, discard the idea.** And do not:

- move parameters outside the grid and re-test
- add timeframes or symbols ("what about H1? what about EURUSD?")
- add a trend filter / higher timeframe / volume until something passes
- lower the pass line
- restrict to "shorts only" or "longs only" after the fact

**If you want to do any of these, write a NEW declaration with a NEW date.**
Not an extension of this one.

---

## 7. Prediction / 予想

> Write what you expect. You will be wrong sometimes; that is the point.

```
I expect ___ passes, because ...
```

**If I am wrong, I write that I was wrong. If I am right, I do not write "as expected."**
The only result is how many of ___ passed.

---

## 8. Record / 記録

- Script:
- Results:
- Judgement:
- Declared on: **YYYY-MM-DD** (before any run)

**This document is not edited after the results come in.**
