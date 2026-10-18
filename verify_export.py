# -*- coding: utf-8 -*-
"""验证循环稳定性导出表：跑完整流程，检查 xlsx / csv 的按列排布"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eclab

BASE = os.path.dirname(os.path.abspath(__file__))
MOCK = os.path.join(BASE, "_mock", "循环")

cfg = eclab.load_config()
cfg["data_dir"] = [MOCK]                      # 只扫模拟目录
cfg["skip_keywords_cv"] = []                  # 模拟文件不含"活化"
cfg["mass_mg"] = {"CV循环-理想": 1.8, "CV循环-真实": 1.8, "GCD循环": 1.8}
eclab.process_all(cfg)

xlsx = os.path.join(BASE, "output", "processed_data.xlsx")
print("\n" + "=" * 66)
for sheet in ("cycle_capacitance", "cycle_retention", "summary"):
    df = pd.read_excel(xlsx, sheet_name=sheet)
    print("\n[%s]  形状 = %s" % (sheet, df.shape))
    print("列名：", list(df.columns))
    print(df.head(8).to_string())
    print("  ...")
    print(df.tail(3).to_string())

for f in ("cycle_capacitance.csv", "cycle_retention.csv"):
    p = os.path.join(BASE, "output", f)
    if os.path.exists(p):
        print("\n[%s] 前 5 行：" % f)
        print(open(p, encoding="utf-8-sig").read().splitlines()[:5])
