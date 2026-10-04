import os, pathlib, tempfile, unittest
import prereg_lock as P


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        pathlib.Path("plan.md").write_text("合格: 平均 > 0 かつ p < 0.05\n", encoding="utf-8")
        pathlib.Path("analysis.py").write_text("THRESHOLD = 0.05\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.cwd)

    def test_lock_then_check_ok(self):
        P.lock(["plan.md", "analysis.py"])
        self.assertEqual(P.check(), [])

    def test_silent_edit_is_caught(self):
        P.lock(["plan.md", "analysis.py"])
        pathlib.Path("analysis.py").write_text("THRESHOLD = 0.10\n", encoding="utf-8")   # 結果を見て線を緩めた
        self.assertEqual(P.check(), ["analysis.py"])

    def test_amend_records_reason_and_keeps_history(self):
        P.lock(["plan.md", "analysis.py"])
        pathlib.Path("analysis.py").write_text("THRESHOLD = 0.05  # バグ修正: 型の変換\n", encoding="utf-8")
        data = P.amend("バグ修正（結果は未確認）", ["analysis.py"])
        self.assertEqual(P.check(), [])
        self.assertEqual(len(data["amendments"]), 1)
        self.assertIn("files", data)                       # 最初の指紋は残る

    def test_second_lock_refused(self):
        P.lock(["plan.md"])
        with self.assertRaises(SystemExit):
            P.lock(["plan.md"])


if __name__ == "__main__":
    unittest.main()
