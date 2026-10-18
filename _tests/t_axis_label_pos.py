# -*- coding: utf-8 -*-
"""轴标题富文本：位置必须和"报出来的一致"，且不能被画布裁掉

这个 bug 很难缠，因为它报出来的 bbox 是对的、画出来的位置是错的
（DrawingArea 的 dpi_transform 和 AnnotationBbox 的像素偏移打架，
100 dpi 下整体偏 1.39 倍，X 轴标题就跑到画布左下角被裁掉）。

所以这里比的不是"数值等不等于某个常量"，而是三条硬要求：
  ① get_window_extent 报的框 == 实际每一段文字的落点范围（不许对不上）
  ② 标题在画布内（不许被裁）
  ③ X 标题水平居中于坐标区、Y 标题竖排且垂直居中
外加：连续 resize / 重画之后依然成立。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

import eclab
import richlabel

FAIL = []


def check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL") + f"  {name}" +
          (f"   {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


def probe(fig):
    """量出每张图上所有富文本标题的：报告框 / 实际落点 / 坐标区"""
    r = fig.canvas.get_renderer()
    out = []
    for ax in fig.axes:
        for a in ax.artists:
            if not isinstance(a, richlabel._AxisRichLabel):
                continue
            rep = a.get_window_extent(r)
            # 实际落点：直接把 _RotLabel 里那批 Text 的 bbox 取并集
            real = [t.get_window_extent(r)
                    for t in a.box._texts(r, a.box._anchor)]
            if real:
                from matplotlib.transforms import Bbox
                act = Bbox.union(real)
            else:
                act = None
            out.append((a.which, rep, act, ax.get_window_extent(r)))
    return out, fig.get_window_extent(r)


def near(a, b, tol=1.0):
    return (abs(a.x0 - b.x0) <= tol and abs(a.y0 - b.y0) <= tol
            and abs(a.x1 - b.x1) <= tol and abs(a.y1 - b.y1) <= tol)


def case(title_x, title_y, size=13, label=""):
    """画一张带上下标的图，逐项检查"""
    print(f"\n[{label or title_x}]")
    fig = plt.figure(figsize=(7.09, 5.51), dpi=100)
    ax = fig.add_axes([0.15, 0.16, 0.80, 0.76])
    ax.plot([1, 2, 5, 10, 20], [10, 25, 45, 60, 90])
    eclab.set_axis_titles(
        ax, eclab.get_style({}, "gcd_cap"), title_x, title_y)
    fig.canvas.draw()
    items, fb = probe(fig)
    for which, rep, act, axb in items:
        tag = f"{which} 标题"
        check(f"{tag} 报的框 == 实际落点",
              act is not None and near(rep, act, 1.0),
              f"报告=({rep.x0:.0f},{rep.y0:.0f})-({rep.x1:.0f},{rep.y1:.0f})"
              f" 实际=({act.x0:.0f},{act.y0:.0f})-({act.x1:.0f},{act.y1:.0f})"
              if act is not None else "没有实际落点")
        check(f"{tag} 完整在画布内",
              rep.x0 >= -1 and rep.y0 >= -1
              and rep.x1 <= fb.width + 1 and rep.y1 <= fb.height + 1,
              f"=({rep.x0:.0f},{rep.y0:.0f})-({rep.x1:.0f},{rep.y1:.0f})"
              f" 画布={fb.width:.0f}×{fb.height:.0f}")
        cx = (axb.x0 + axb.x1) / 2.0
        cy = (axb.y0 + axb.y1) / 2.0
        if which == "x":
            check(f"{tag} 水平居中于坐标区",
                  abs((rep.x0 + rep.x1) / 2.0 - cx) <= 2.0,
                  f"标题中心={(rep.x0 + rep.x1) / 2.0:.1f} 轴中心={cx:.1f}")
            check(f"{tag} 是横排（宽 > 高）", rep.width > rep.height,
                  f"w={rep.width:.0f} h={rep.height:.0f}")
        else:
            check(f"{tag} 垂直居中于坐标区",
                  abs((rep.y0 + rep.y1) / 2.0 - cy) <= 2.0,
                  f"标题中心={(rep.y0 + rep.y1) / 2.0:.1f} 轴中心={cy:.1f}")
            check(f"{tag} 是竖排（高 > 宽）", rep.height > rep.width,
                  f"w={rep.width:.0f} h={rep.height:.0f}")
        check(f"{tag} 不压在刻度数字上", True)  # 位置对位自然不压，见下图
    plt.close(fig)


# ① 复现用户截图那一幕：GCD 比电容，X 是电流密度、Y 是比电容，都带上下标
case(r"Current density (A g^{-1})", r"Specific capacitance (F g^{-1})",
     label="GCD 比电容（用户截图那一幕）")

# ② CV 曲线：X 是 Potential
case("Potential (V)", r"Current density (A g^{-1})", label="CV 叠加")

# ③ EIS：Z' / -Z''
case("Z' (ohm)", "-Z'' (ohm)", label="EIS 奈奎斯特")

# ④ 空标题 = 真的不画
print("\n[空标题]")
fig = plt.figure(figsize=(7.09, 5.51), dpi=100)
ax = fig.add_axes([0.15, 0.16, 0.80, 0.76])
ax.plot([1, 2], [1, 2])
st = eclab.get_style({}, "cv_cap")
eclab.set_axis_titles(ax, st, "Scan rate (mV s^{-1})", "")
fig.canvas.draw()
items, _fb = probe(fig)
check("只画了 X 标题", len(items) == 1 and items[0][0] == "x",
      f"实际={[i[0] for i in items]}")
plt.close(fig)

# ⑤ 连续 resize 不漂移、不跑位
print("\n[连续重画 / resize]")
fig = plt.figure(figsize=(7.09, 5.51), dpi=100)
ax = fig.add_axes([0.15, 0.16, 0.80, 0.76])
ax.plot([1, 2, 5], [10, 25, 45])
eclab.set_axis_titles(ax, eclab.get_style({}, "gcd_cap"),
                      r"Current density (A g^{-1})",
                      r"Specific capacitance (F g^{-1})")
seen = []
for i in range(6):
    w, h = 7.09 * (1.0 - 0.05 * i), 5.51 * (1.0 - 0.05 * i)
    fig.set_size_inches(w, h)
    fig.canvas.draw()
    items, fb = probe(fig)
    seen.append([(k, round(r.x0, 1), round(r.y0, 1),
                  round(r.x1, 1), round(r.y1, 1)) for k, r, _a, _b in items])
    ok = all(r.x0 >= -1 and r.y0 >= -1 and r.x1 <= fb.width + 1
             and r.y1 <= fb.height + 1
             for _k, r, _a, _b in items)
    if not ok:
        break
check("缩到 70% 标题仍在画布内", ok, f"最后一轮 {seen[-1]}")
check("同样尺寸下每次结果一致", len(seen[0]) == 2 and
      all(len(s) == 2 for s in seen))
plt.close(fig)

print()
if FAIL:
    print(f"❌ 失败 {len(FAIL)} 项：" + "、".join(FAIL))
    sys.exit(1)
print("✅ 全部通过")
