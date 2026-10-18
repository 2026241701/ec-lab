# -*- coding: utf-8 -*-
"""跑全部测试 + 重新生成界面截图

用法：
    python _tests/run_all.py
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

TESTS = ["test_round4.py", "test_title.py", "test_palette.py",
         "test_regress.py", "t_dir_fix.py", "t_rich_toggle.py",
         "t_gcd_shape.py", "t_leg_rich.py", "t_preview2.py",
         "t_round5.py", "t_scheme63.py",
         "t_titles_leak.py", "t_axis_label_pos.py", "t_e2e_titles.py",
         "t_bug5_pick.py", "t_bug1_zoom.py",
         "t_bug3_color_group.py", "t_bug4_palette_nest.py",
         "t_bug6_paths_preview.py",          "t_bug7_nocompress.py",
         "t_scan_dedup.py", "t_eis_circuit.py", "t_palette_edit.py",
         "t_mass_guard.py"]

if __name__ == "__main__":
    os.chdir(ROOT)
    fail = 0
    for t in TESTS:
        print("=" * 60)
        print("跑", t)
        print("=" * 60)
        r = subprocess.run([PY, os.path.join(HERE, t)],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip().splitlines()
        print("\n".join(out[-6:]) if out else "(无输出)")
        if r.returncode != 0:
            fail += 1
            print("!! 失败")
            print((r.stderr or "").strip()[-1200:])
        print()

    if "--shot" in sys.argv:
        print("生成界面截图…")
        r = subprocess.run([PY, os.path.join(HERE, "shot.py")],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print((r.stdout or "").strip()[-600:])
        if r.returncode != 0:
            print((r.stderr or "").strip()[-800:])

    print("=" * 60)
    print("全部通过" if not fail else f"{fail} 个测试失败")
    sys.exit(1 if fail else 0)