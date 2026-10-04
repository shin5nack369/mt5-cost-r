# mt5-cost-r

**Measure what your own MetaTrader 5 account actually costs you — then run backtests that are allowed to fail.**

Tooling for killing trading ideas quickly and honestly. Not for finding winners.

---

## Why

Two things kill retail strategies before the strategy itself gets a say:

**1. Cost is not a subtraction. It is a gate on which timeframe you can trade at all.**

```
cost_r = round-trip cost / 1R
```

If 1R is `ATR(14) x 2.0`, then the smaller the timeframe, the smaller 1R, and the
heavier the same fixed cost becomes. Empirically you need `avg_r >= cost_r * 3` to
survive. The same logic can be viable on M15 and hopeless on M5 **on the same account**.

Measured on one live USDJPY account (n=799,898 ticks, round trip 2.700 pips):

```
TF    ATR(14)   cost_r   required avg_r
M5      5.6p     0.241    0.72R   <- needs 68.8% win rate at TP=1.5R. Not happening.
M15    11.2p     0.121    0.36R
M30    16.1p     0.084    0.25R
H1     20.3p     0.067    0.20R
```

The broker's advertised "average 0.2 pips" is a best-case number, not the one you
get filled at. Measure your own.

**2. Testing 36 parameter combinations produces ~1.8 good-looking results from pure noise.**

```
36 tests x 0.05 = 1.8 expected false positives
```

So "one cell passed" is *below* what noise gives you. The only defence is deciding
what counts as a pass **before you look** — which is what `templates/pre_declaration.md`
is for.

---

## What is here

```
src/measure_cost.py      Measure YOUR account's real spread distribution, by hour,
                         and derive cost_r per timeframe. Start here.
src/backtest_engine.py   Backtest engine with look-ahead assertions, OOS split,
                         bootstrap PF confidence intervals. 7 unit checks, no MT5 needed.
src/signal_ma_cross.py   A worked example: MA cross, 36 tests. Imports the engine
                         rather than copying it, so two studies stay comparable.
src/dryrun_wiring.py     Runs main() end to end against a stubbed MT5. See below.
src/diag_gross.py        Re-runs with cost set to zero, to answer "did the spread
                         kill it, or was there never an edge?"
src/gate_power.py        How often a "first N trades, PF >= 1" gate passes a real edge
                         versus pure noise. Measured: ~6 in 10 vs ~5 in 10.
src/prereg_lock.py       Hash the pre-declaration with sha256 and refuse silent edits.
                         lock / check / amend. Tests in src/test_prereg_lock.py.
templates/pre_declaration.md   Fill in and commit BEFORE running anything.
examples/                Real output from the MA-cross study (36 tests, 0 passed).
docs/                    One landing page per article, so clicks can be told apart.
```

## Quick start

```bash
pip install -r requirements.txt
# MT5 terminal must be running and logged in; the symbol must be in Market Watch.

cd src
python measure_cost.py                 # what can this account trade at all?
python signal_ma_cross.py --selftest   # 7 engine checks, no MT5 required
python dryrun_wiring.py                # main() end to end against a stub MT5
python signal_ma_cross.py              # the real 36 tests
python diag_gross.py                   # cost-free counterfactual
python -m unittest test_prereg_lock    # 4 checks on the pre-declaration lock
```

---

## Three things that cost me real time

**MT5 `time` is SERVER time, not UTC.** Broker servers run GMT+2/+3. I only caught
it because the hourly medians showed a 5x spread spike at "09:00 Tokyo" — a claim
with no story behind it. It was actually 21:00-22:00 UTC, the daily rollover, which
explains a 5x spike perfectly. `measure_cost.py` measures the offset and prints both.

**A passing self-test does not mean the program runs.** The engine here passes 7
checks. The first production run still died instantly, having written zero bytes,
because `main()` unpacked the engine's return values wrongly — and `selftest()` never
calls `main()`. Green checks sent me looking at the terminal and the environment
instead of at my own call site. `dryrun_wiring.py` stubs MT5 into `sys.modules` and
runs `main()` to completion, checking only the plumbing: test count matches the
declaration, both train and test carry a full summary, `trades_per_month` is numeric.
It takes no market data and it fails on the bug it was written for.

**Build the ratio first, then average.** `cost_r` computed once from a mean ATR
understates what is actually paid by **39-47%** (measured), because 1R is set per
trade by the ATR at entry, and the mean of reciprocals exceeds the reciprocal of the
mean for any ATR that varies. Same shape as latency-per-request or cost-per-user:
average first, divide after, and the denominator's variance hands you a friendlier
number than reality.

---

## Worked example

`examples/results_ma_cross.json` — plain moving-average cross on USDJPY, M15 and M30,
2023-01 to 2026-09, 36 tests, declared before the run.

**0 of 36 passed.** Of the 72 windows (36 train + 36 test) exactly one is positive,
at +0.0081R against a 0.25R line. Not one training window has a profit factor above
1.0 — and the training half is the half where parameters can be chosen to flatter you.

With cost set to zero, still 0 of 36 reach the line: the best gross run is 51% of
what it needs. So the cross has *something* in it — about half of what the spread
costs — and the spread takes all of it. That is probably why the argument about
whether moving averages work never ends. Measured gross it works a little; measured
net it does not; both camps are right about the number they are looking at.

---

## 日本語

自分の MT5 口座の**実際の取引コスト**をティックから実測し、**戦える時間足を先に確定する**ためのツールです。あわせて、**落ちることを許されたバックテスト**の書き方を置いています。

- `cost_r = 往復コスト ÷ 1R`。1R が ATR の倍数なら、ATR の小さい時間足ほど同じコストが重くなる。`avg_r >= cost_r × 3` がないと運用に耐えません
- **36通り試せば、優位性ゼロでも 1.8 件は「通って」しまいます**（36 × 0.05）。だから通過の定義は**見る前に**決める。`templates/pre_declaration.md` がその雛形です
- `cost_r` は**トレードごとに計算して平均**してください。平均ATRから1回計算すると実測で **39〜47% 過小評価**します

詳しい経緯は記事にあります（日本語）。

- [MT5のスプレッドをPythonで実測する — ついでに「平均で割る」と4割ズレた話](https://qiita.com/shin5nack/items/efa2fabcf34a5563dc26)
- [「ゴールデンクロスで買う」36通り、通過0件](https://note.com/shin5nack/n/n9ac9e4a0a60b)

---

## Caveats

- Measured on one broker, one account, one symbol. **Re-measure on yours.** That is
  the entire point — the numbers in this README are not yours.
- Fills are idealised: no slippage, no requotes, no partial fills. Reality is worse
  than these results, never better.
- `measure_cost.py` reads ticks and rates only. Nothing here places an order.

## License

MIT
