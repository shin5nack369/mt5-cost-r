# 取引コストを実測する（cost_r）

Qiita の記事「MT5のスプレッドをPythonで実測する — ついでに『平均で割る』と4割ズレた話」から来た方へ。

## このページにあるもの

- 実測スクリプト本体: [`src/measure_cost.py`](../src/measure_cost.py)
- 依存: [`requirements.txt`](../requirements.txt)（`MetaTrader5` だけ）

## 要点だけ再掲

取引コストは引き算ではなく、**戦える時間足を決める制約**です。

```
cost_r = 往復コスト ÷ 1R
```

1R を `ATR(14) × 2.0` で取るなら、ATR の小さい時間足ほど 1R が小さく、同じコストが相対的に重くなります。経験的に `平均R >= cost_r × 3` が無いと運用に耐えません。

そして **順序を間違えると 39〜47% 過小評価します。**

```python
# NG: 平均を1回作って、それで割る
cost_ratio = cost / (atr_series.mean() * k)

# OK: 1件ずつ比を作ってから平均する
cost_ratio = (cost / (atr_series * k)).mean()
```

## 使い方

```bash
pip install -r requirements.txt
python src/measure_cost.py
```

MT5 のティックから、自分の口座・自分が約定する時間帯の値で出ます。ブローカーの広告値（「平均0.2 pips」など）は最良条件の値です。

## 次の一歩

この測定は「戦略のアイデアを7日で検定して、通らなければ捨てる」手順の Day2 にあたります。全7日ぶんは note にまとめています（題材の戦略は Day5 で死亡・36検定すべて不合格）。
