"""prereg_lock.py -- 結果を見る前に「何を試すか・何なら合格か」をファイルに書き、sha256 で鍵をかける。

使い方:
    python prereg_lock.py lock  plan.md analysis.py      # 鍵をかける（lock.json を作る）
    python prereg_lock.py check                            # 鍵をかけた後にファイルが変わっていないか
    python prereg_lock.py amend "理由" analysis.py         # 変えるなら、理由と新しい指紋を追記（上書きしない）
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys

LOCK = pathlib.Path("lock.json")


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def lock(paths):
    if LOCK.exists():
        raise SystemExit("lock.json がもうある。変えるなら amend を使う（上書きしない）")
    data = {"locked_at": now(), "files": {p: sha256(p) for p in paths}, "amendments": []}
    LOCK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def current():
    """最初の鍵に、追記の指紋を順に上書きした「今の正しい指紋」"""
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    files = dict(data["files"])
    for a in data["amendments"]:
        files.update(a["files"])
    return data, files


def check():
    _, files = current()
    changed = [p for p, h in files.items() if not pathlib.Path(p).exists() or sha256(p) != h]
    return changed


def amend(reason, paths):
    data, _ = current()
    data["amendments"].append({"at": now(), "reason": reason, "files": {p: sha256(p) for p in paths}})
    LOCK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "lock":
        print(json.dumps(lock(sys.argv[2:]), ensure_ascii=False, indent=1))
    elif cmd == "check":
        bad = check()
        print("OK: 鍵をかけた時のまま" if not bad else "変わっている: " + ", ".join(bad))
        sys.exit(1 if bad else 0)
    elif cmd == "amend":
        print(json.dumps(amend(sys.argv[2], sys.argv[3:]), ensure_ascii=False, indent=1))
