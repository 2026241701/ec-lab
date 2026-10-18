# -*- coding: utf-8 -*-
"""回归测试：质量兜底行为（铁律 #2 —— 质量未登记就跳过，绝不静默兜底）

config.mass_mg 里的 "*" 是兜底值，会让所有未登记样品静默套同一质量，
比电容全部算错。本测试锁定优先级与跳过行为：

    config 登记  >  "*" 兜底  >  文件名/路径自动提取  >  明确跳过

其中第 5 条断言真实 config.json 里不允许再有 "*"（2026-10-13 按体检
报告建议删除，cfg_guard 的配置说明也写明"删掉它则强制逐个填写（推荐）"）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import eclab as E


def main():
    # 1. 无兜底、登记表没有、文件名也提取不到 -> 必须跳过（None）
    cfg = {"mass_mg": {"CV_2": 2.0}}
    got = E.get_mass(cfg, ["某个未登记样品"],
                     os.path.join("某目录", "循环-100mV.txt"))
    assert got is None, f"未登记质量应被跳过，实际返回 {got}"

    # 2. 登记表里有 -> 用登记值（2.0 mg -> 0.002 g）
    got = E.get_mass(cfg, ["CV_2"], "任意路径")
    assert got == 0.002, f"config 登记值应优先，实际 {got}"

    # 3. 有 "*" 兜底时 -> 用兜底值（锁死旧行为，证明删掉它确实改变了什么）
    cfg2 = {"mass_mg": {"*": 1.8}}
    got = E.get_mass(cfg2, ["某个未登记样品"],
                     os.path.join("某目录", "循环-100mV.txt"))
    assert got == 0.0018, f"有兜底时应返回 1.8mg，实际 {got}"

    # 4. 无兜底但文件名/路径带质量 -> 自动提取这条路必须仍然有效
    cfg3 = {"mass_mg": {}}
    got = E.get_mass(cfg3, ["样品"], os.path.join("data", "2mg", "GCD", "1A.txt"))
    assert got == 0.002, f"文件名提取应生效，实际 {got}"

    # 5. 真实 config.json 不允许再有 "*" 兜底值
    import json
    real = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    assert "*" not in real.get("mass_mg", {}), (
        "config.json 的 mass_mg 里还有 '*' 兜底值——删掉它，"
        "未登记质量的文件必须被明确跳过")

    print("✅ 质量兜底行为正确：登记优先 / 无兜底时未登记即跳过 / "
          "文件名提取仍有效 / 真实 config 无 '*'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
