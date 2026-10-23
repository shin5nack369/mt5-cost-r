# 「良いバックテスト」を自分で疑うための道具

投資ナビ＋ の記事「AIで作ったEAが、フォワードテストで落ちる理由――一番だまされるのは作った本人」から来た方へ。
記事に出てくる数字を、どのコードで出したかを置いてあります。**MIT ライセンスなので、そのまま使えます。**

## このページにあるもの

- 判定そのものの当たり具合を測る: [`src/gate_power.py`](../src/gate_power.py) ／ [テスト](../src/test_gate_power.py)
- 「コストが高いから負けたのでは」を潰す診断: [`src/diag_gross.py`](../src/diag_gross.py)
- 検定を回すエンジン: [`src/backtest_engine.py`](../src/backtest_engine.py)
- 試した回数を先に固定する: [`src/prereg_lock.py`](../src/prereg_lock.py) ／ [テスト](../src/test_prereg_lock.py)
- 往復コストを実測する: [`src/measure_cost.py`](../src/measure_cost.py)
- 取引リストの例: [`examples/results_ma_cross.json`](../examples/results_ma_cross.json) ／ [`examples/diag_gross.json`](../examples/diag_gross.json)

## 記事の3つの理由に対応する道具

### 理由2「何回試したかが、見えない」→ 先に固定する

試した回数はバックテストのレポートに残りません。だから、**始める前に**条件と合格ラインを書いて
ハッシュで固定しておきます。`prereg_lock.py` は宣言文を sha256 で封じるだけの約60行です。

```python
from prereg_lock import lock, verify

h = lock("prereg.md")        # 宣言を固定。ハッシュを残す
verify("prereg.md", h)       # 後から1文字でも変われば False
```

固定してあると、通らなかったときに線を動かせません。**動かせないことが、この道具の機能です。**

### 理由3「数件の大勝ちに支えられている」→ 除いて見る

記事では MT5 付属のサンプルEA「Moving Average」を EURUSD 1時間足で回し、
取引193件・PF 1.55 から利益の大きい順に除いていきました。同じことが
`backtest_engine.py` の出力（`examples/results_ma_cross.json` の形）に対して回せます。

### 「合格」という判定自体を疑う → `gate_power.py`

合格ラインを決めても、**その判定が本物をどれだけ通し、偽物をどれだけ通すか**は別の話です。

```python
from gate_power import gate_power

gate_power(trade_r, n=30, pf_min=1.0)
# {'本物が合格': 0.659, '偽物が合格': 0.478, '連続n件で不合格': 0.337}
```

「最初の30件で PF ≥ 1 なら合格」は、**本物でも4割落ち、偽物でも半分が通ります。**
上の数字は分布を作って出した例なので、**自分の取引リストで出し直してください。**

### 落ちた理由をコストに押し付けないため → `diag_gross.py`

落ちたあとに「コストが高かったせいだ」と言いたくらます。`diag_gross.py` は
**格子を1つも変えず、合格ラインを1つも下げず**に、コストを 0 にしたとき avg_r が
どこまで上がるかだけを出します。上げてもラインに届かないなら、敗因はコストではありません。

🔴 これは再検定ではありません。**通るまで条件を動かすことと、落ちた理由を特定することは別です。**

## 使うときの前提

`numpy` だけで動きます。数字はすべて筆者の口座・筆者の検証条件での実測で、
将来の成績を保証するものではありません。

---

この記事の点検を自分の手でやる道具と解説書は
[「EA頑健性チェック」](https://www.gogojungle.co.jp/tools/ebooks/87672)（¥4,980）にまとめてあります。
MT5 のバックテストレポートを渡すと、上の観点をまとめて調べて判定を出します。
判定の基準は固定で、結果を見てから緩めることはできません。

レポートを預けて第三者に点検してもらう形は
[EAバックテストの頑健性を第三者が点検します](https://skijan.com/ja/skill/4344)（¥14,800）です。
