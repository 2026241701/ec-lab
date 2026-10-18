# -*- coding: utf-8 -*-
"""回归测试：EIS 等效电路代码的合法性（GUI 交互 + 引擎两端）

背景 bug：GUI 的等效电路下拉框是 setEditable(True)，用户可能手输
自定义串，或在「auto」后带一个尾随空格。原先这两个情况会原样进
eclab.fit_eis，因 bounds/初值长度不匹配被 least_squares 抛异常、
被 except 吞掉，最终报「拟合失败：该电路无法收敛」——既误导又看不出
是哪一步错了。

修复：
- eclab.fit_eis 对未知电路代码直接返回明确的“不支持的等效电路”提示；
- ec_gui._circuit_code 先 strip 去首尾空格，避免「auto 」类输入误判。

本测试同时验证两端。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import eclab  # noqa: E402
import ec_gui  # noqa: E402


def check(name, cond):
    print(("✅ " if cond else "❌ ") + name)
    if not cond:
        check.failed += 1
check.failed = 0


# ---- 找一个能解析的 EIS 文件 ----
# 公开仓库里不带任何真实测量数据，所以这里不写死路径，按下面的顺序找：
#   ① 环境变量 EC_EIS_SAMPLE（自己指定一个 EIS 文件）
#   ② config.json 的 data_dir（Ding 本机的真实数据）
#   ③ 仓库内置合成样例 examples/sample_data/EIS/eis-1.txt
# 都找不到就跳过「引擎实证」这一段，只跑后面的白盒不变量（不报失败）。
def _eis_candidates():
    cands = []
    env = os.environ.get("EC_EIS_SAMPLE", "").strip()
    if env:
        cands.append(env)
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            dirs = json.load(f).get("data_dir") or []
    except Exception:
        dirs = []
    if isinstance(dirs, str):
        dirs = [dirs]
    for d in dirs:
        try:
            if not d or not os.path.isdir(d):
                continue
            for name in ("1.txt", "EIS.txt"):
                cands.append(os.path.join(d, name))
                cands.append(os.path.join(d, "EIS", name))
            cands.extend(sorted(glob.glob(os.path.join(d, "**", "*.txt"),
                                          recursive=True))[:20])
        except Exception:
            continue
    cands.append(os.path.join(ROOT, "examples", "sample_data", "EIS",
                              "eis-1.txt"))
    return cands


_eis_path = None
for _p in _eis_candidates():
    if not os.path.isfile(_p):
        continue
    try:
        eclab.parse_eis(_p)          # 能解析才算数
    except Exception:
        continue
    _eis_path = _p
    break

if _eis_path is None:
    print("⚠️ 找不到可解析的 EIS 样本，跳过引擎实证（仅跑白盒不变量）")
else:
    print("EIS 样本：%s" % _eis_path)
    _meta, _f, _zr, _zi = eclab.parse_eis(_eis_path)

    # 1) 已知电路仍能正常拟合
    for _c in ("auto", "W", "Wo", "Ws"):
        _d, _zf, _rep = eclab.fit_eis(_f, _zr, _zi, _c)
        check("fit_eis(%r) 正常返回拟合结果" % _c, _d is not None
              and _zf is not None and "R²" in _rep)

    # 2) 未知电路：返回明确“不支持”提示，且不再内含“无法收敛”
    for _bad in ("我的电路", "Rs-(Rp+CPE)", "auto ", "Wo "):
        _d, _zf, _rep = eclab.fit_eis(_f, _zr, _zi, _bad)
        check("fit_eis(%r) 给明确报错而非“无法收敛”" % _bad,
              _d is None and "不支持的等效电路" in _rep
              and "无法收敛" not in _rep)


# ---- GUI 端：_circuit_code 映射 + strip ----
class _FakeCombo:
    def __init__(self, text):
        self._t = text

    def currentText(self):
        return self._t


_mw = ec_gui.MainWindow.__new__(ec_gui.MainWindow)  # 不跑完整 __init__
_mw.cb_circuit = _FakeCombo("")
for _disp, _code in (
    ("自动择优（W / Wo / Ws 选 R² 最高）", "auto"),
    ("Rs-[(Rp+W)‖CPE]（平面扩散）", "W"),
    ("Rs-[(Rp+Wo)‖CPE]（有限短路）", "Wo"),
    ("Rs-[(Rp+Ws)‖CPE]（有限阻塞）", "Ws"),
):
    _mw.cb_circuit = _FakeCombo(_disp)
    check("_circuit_code 映射 %r -> %r" % (_disp, _code),
          _mw._circuit_code() == _code)

# 尾随空格 / 前后空格应被 strip
for _bad in ("auto ", " 自动择优（…）", "Wo "):
    _mw.cb_circuit = _FakeCombo(_bad)
    _got = _mw._circuit_code()
    check("_circuit_code 对带空格输入 %r 不再是原样" % _bad,
          _got != _bad and " " not in _got)


if check.failed:
    print("\n!! 有 %d 项不通过" % check.failed)
    sys.exit(1)
print("\n✅ EIS 电路代码：引擎明确报错 + GUI 去空格映射全部成立")
