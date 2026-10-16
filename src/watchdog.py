"""常駐プロセスの「無応答」を検知する最小の道具立て。

Qiita 記事「常駐プロセスの『無応答』を検知する」の本文に載せたコードそのもの。
標準ライブラリだけで動く。依存なし。

- call_with_timeout : 返ってこない呼び出しを別スレッドで打ち切る
- Heartbeat         : 「1周終えた」だけを原子的に書き出す
- check_heartbeats  : OK / STALE / UNKNOWN の3値で返す（2値に丸めない）
- self_report       : 監視器自身も監視対象に入れる

使い方とハマりどころは docs/from-qiita-07-no-response.md を参照。
テストは src/test_watchdog.py（7件）。
"""

import json
import os
import threading
import time
from datetime import datetime, timezone


def call_with_timeout(fn, timeout_sec, *args, **kwargs):
    """fn を別スレッドで実行し、timeout_sec 以内に返らなければ
    (None, TimeoutError) を返す。

    返り値: (result, error)
      - 正常終了 : (戻り値, None)
      - 例外     : (None, 例外インスタンス)
      - 無応答   : (None, TimeoutError)
    """
    box = {}

    def runner():
        try:
            box["result"] = fn(*args, **kwargs)
        except BaseException as e:      # noqa: BLE001 - 呼び出し側へ渡す
            box["error"] = e

    th = threading.Thread(target=runner, daemon=True)
    th.start()
    th.join(timeout_sec)

    if th.is_alive():
        return None, TimeoutError(
            f"{getattr(fn, '__name__', fn)} が {timeout_sec}s 以内に返りませんでした"
        )
    if "error" in box:
        return None, box["error"]
    return box.get("result"), None


class Heartbeat:
    def __init__(self, path, name):
        self.path = path
        self.name = name

    def beat(self, **extra):
        tmp = f"{self.path}.tmp"
        payload = {
            "name": self.name,
            "pid": os.getpid(),
            "at": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            **extra,
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, self.path)      # 原子的に差し替える

    @staticmethod
    def age_sec(path):
        """最後の beat から何秒経ったか。ファイルが無ければ None。"""
        try:
            with open(path, encoding="utf-8") as f:
                return max(0.0, time.time() - float(json.load(f)["epoch"]))
        except (OSError, ValueError, KeyError):
            return None


def check_heartbeats(specs, now=None):
    """specs: [(name, path, 許容秒), ...] → [(name, 状態, 経過秒 or None)]"""
    out = []
    for name, path, limit in specs:
        age = Heartbeat.age_sec(path)
        if age is None:
            out.append((name, "UNKNOWN", None))
        elif age > limit:
            out.append((name, "STALE", age))
        else:
            out.append((name, "OK", age))
    return out


def self_report(path, version):
    Heartbeat(path, "watchdog").beat(version=version)
