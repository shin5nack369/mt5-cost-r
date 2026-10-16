import os, sys, time, tempfile
from watchdog import call_with_timeout, Heartbeat, check_heartbeats


def test_normal():
    r, e = call_with_timeout(lambda: 1 + 1, 1.0)
    assert (r, e) == (2, None), (r, e)


def test_exception():
    def boom(): raise ValueError("x")
    r, e = call_with_timeout(boom, 1.0)
    assert r is None and isinstance(e, ValueError), (r, e)


def test_timeout():
    t0 = time.time()
    r, e = call_with_timeout(lambda: time.sleep(5), 0.3)
    dt = time.time() - t0
    assert r is None and isinstance(e, TimeoutError), (r, e)
    assert dt < 1.0, dt          # 5秒待たずに返ること


def test_args():
    r, e = call_with_timeout(lambda a, b=0: a + b, 1.0, 3, b=4)
    assert (r, e) == (7, None), (r, e)


def test_heartbeat_roundtrip():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "hb.json")
    assert Heartbeat.age_sec(p) is None           # 未作成は UNKNOWN
    Heartbeat(p, "worker").beat(loop=1)
    age = Heartbeat.age_sec(p)
    assert age is not None and age < 1.0, age
    res = check_heartbeats([("worker", p, 60), ("missing", p + "x", 60)])
    assert res[0][1] == "OK", res
    assert res[1][1] == "UNKNOWN" and res[1][2] is None, res


def test_heartbeat_stale():
    d = tempfile.mkdtemp(); p = os.path.join(d, "hb.json")
    Heartbeat(p, "w").beat()
    time.sleep(0.2)
    assert check_heartbeats([("w", p, 0.1)])[0][1] == "STALE"


def test_atomic_no_tmp_left():
    d = tempfile.mkdtemp(); p = os.path.join(d, "hb.json")
    Heartbeat(p, "w").beat()
    assert os.listdir(d) == ["hb.json"], os.listdir(d)


for name, fn in sorted(list(globals().items())):
    if name.startswith("test_"):
        fn(); print(f"  [OK] {name}")
print("\n全て通過")
