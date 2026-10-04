# 事前宣言を sha256 で固定する

Qiita の記事「結果を見てから線を動かさない — 事前宣言を sha256 で『鍵』にする約60行」から来た方へ。

## このページにあるもの

- 本体（約60行・標準ライブラリだけ）: [`src/prereg_lock.py`](../src/prereg_lock.py)
- テスト（4件）: [`src/test_prereg_lock.py`](../src/test_prereg_lock.py)
- 事前宣言のテンプレート: [`templates/pre_declaration.md`](../templates/pre_declaration.md)
- 判定を回すエンジン: [`src/backtest_engine.py`](../src/backtest_engine.py)

## 要点だけ再掲

**試す前に「何を試すか・何なら合格か」をファイルに書き、そのファイルの sha256 を記録してから結果を見る。**
あとで線を動かしたくなったら、上書きではなく「理由つきの追記」だけを許す。

半年で約200回の検定をして分かったのは、

- 何十通りも試して一番良いものだけ見せると、**それだけで「効いている」ように見える**
- 結果を見た後だと、「この閾値は少し厳しすぎた」「この期間は特殊だった」と、線を動かす理由がいくらでも思いつく
- しかも、動かした本人には悪気がない

ということでした。100回じゃんけんして勝った1回だけ報告するのと同じです。

A/B テストでも機械学習の実験でもバックテストでも、同じ形で効きます。

## 使い方

```bash
python src/prereg_lock.py lock  plan.md analysis.py   # 鍵をかける（lock.json ができる）
python src/prereg_lock.py check                       # 鍵をかけた後に変わっていないか
python src/prereg_lock.py amend "理由" analysis.py    # 変えるなら理由つきで追記（上書きはしない）
```

`lock` は2回目を拒否します。黙って線を緩めると `check` が `変わっている: analysis.py` と言います。
`amend` を使えば最初の指紋は残り、何をいつどんな理由で変えたかが `lock.json` に積まれます。

テストはこれで回ります。

```bash
cd src && python -m unittest test_prereg_lock
```

## 次の一歩

この仕組みは「戦略のアイデアを7日で検定して、通らなければ捨てる」手順の Day3（検定条件の固定）にあたります。全7日ぶんは note にまとめています。
