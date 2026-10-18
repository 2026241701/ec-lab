# -*- coding: utf-8 -*-
"""上下标方向 + 文本框旋转 回归测试

验证：
1. 竖排（CCW 90°）时上标垂直于基线、在文字左侧、下标在右侧；
2. 任意旋转角下上标始终垂直于基线（旋转向量公式正确）；
3. 文本框旋转列能传到引擎：add_label 用 _RotLabel（整框任意角旋转），
   apply_texts 把 texts[].rotation 透传；普通文本走 ax.text 旋转。
"""
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import richlabel
import eclab

SIZE = 20.0
RISE = 0.40
DROP = 0.18


def _layout_of(text, rot, size=SIZE, center=False):
    """构建富文本框，量出每段相对锚点的 2D 偏移（display 帧，+y 向上，点）

    返回 [(片段文字, ox, oy), ...]。算法跟 _RotLabel._place 同源：
    垂直向量 (0,perp) 转 θ、沿基线向量转 θ。center=False 时不做
    沿阅读方向的居中（ox/oy 就是纯粹的排版向量，用来验旋转公式）；
    center=True 时跟引擎实际排版一致（用来验阅读顺序）。
    这里独立复算一遍，免得"测的就是被测的"。
    """
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ab = richlabel.add_label(ax, text, (0.5, 0.5), size=size, rotation=rot,
                             rise=RISE, drop=DROP)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    box = ab.box
    th = math.radians(box._rot)
    rx, ry = math.cos(th), math.sin(th)
    nx, ny = -math.sin(th), math.cos(th)
    ppu = r.points_to_pixels(1.0) or 1.0
    widths = [r.get_text_width_height_descent(seg.text, seg._ensure_prop(),
                                              False)[0] / ppu
              for seg, *_ in box._items]
    shift = sum(widths) / 2.0 if center else 0.0
    pos, cum = [], 0.0
    for (seg, frag, fs, perp, along), wpts in zip(box._items, widths):
        t_along = cum - shift + along
        pos.append((frag,
                    rx * t_along + nx * perp,
                    ry * t_along + ny * perp))
        cum += wpts
    plt.close(fig)
    return pos


def test_vertical_sup_left():
    """CCW 90°：上标应在垂直基线左侧 (ox<0)，下标在右侧 (ox>0)；
    阅读方向是 +y，各段自下往上依次排开。"""
    pos = _layout_of("A g^{-1}", 90.0)
    sup = next(p for p in pos if "-1" in p[0])
    assert abs(sup[1] - (-RISE * SIZE)) < 1e-6, sup[1]

    pos2 = _layout_of("Fe_{3}O_{4}", 90.0, center=True)
    sub = next(p for p in pos2 if p[0] == "3")
    assert abs(sub[1] - (DROP * SIZE)) < 1e-6, sub[1]
    # 阅读顺序：自下往上（oy 递增）就是原文的先后
    assert [p[0] for p in sorted(pos2, key=lambda p: p[2])] == \
        ["Fe", "3", "O", "4"], pos2
    print("PASS test_vertical_sup_left (上标左/下标右)")


def test_rotated_vector_general():
    """任意角：单段上标偏移向量 = 把 (0, +rise*size) 逆时针转 rot
    （用纯上标文字，无前置阅读推进量干扰）"""
    for deg in (0.0, 30.0, 45.0, 90.0, 135.0, 180.0, 270.0):
        th = math.radians(deg)
        ox = -RISE * SIZE * math.sin(th)
        oy = RISE * SIZE * math.cos(th)
        pos = _layout_of("^{-1}", deg)
        sup = next(p for p in pos if "-1" in p[0])
        assert abs(sup[1] - ox) < 1e-6, (deg, sup[1], ox)
        assert abs(sup[2] - oy) < 1e-6, (deg, sup[2], oy)
    print("PASS test_rotated_vector_general (旋转向量公式)")


def test_add_label_rotlabel():
    """文本框旋转列 → _RotLabel，且整框按 rot 旋转"""
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ab = richlabel.add_label(ax, "A g^{-1}", (0.5, 0.5), size=SIZE,
                             rotation=45.0, rise=RISE, drop=DROP)
    assert isinstance(ab.offsetbox, richlabel._RotLabel), type(ab.offsetbox)
    assert abs(ab.offsetbox._rot - 45.0) < 1e-6
    plt.close(fig)
    print("PASS test_add_label_rotlabel (45° 整框旋转)")


def test_apply_texts_rotation():
    """文本框旋转列透传到引擎：rich 文本走 _RotLabel，普通文本走 ax.text"""
    fig = plt.figure()
    ax = fig.add_subplot(111)
    st = {
        "font": {"family": "Arial", "cjk": "SimSun", "base": 12, "label": 12},
        "mathtext": {"sub_ratio": 0.68, "rise": RISE, "drop": DROP},
        "texts": [
            {"text": "A g^{-1}", "x": 0.5, "y": 0.6, "rotation": 45,
             "rich": True},
            {"text": "普通文字", "x": 0.5, "y": 0.4, "rotation": 90,
             "rich": False},
        ],
    }
    eclab.apply_texts(ax, st)
    found_box = any(isinstance(a.offsetbox, richlabel._RotLabel)
                    and abs(a.offsetbox._rot - 45.0) < 1e-6
                    for a in ax.artists)
    assert found_box, "rich 文本框未整框旋转"
    found_text = any(abs(a.get_rotation() - 90.0) < 1e-6 for a in ax.texts)
    assert found_text, "普通文本框未旋转"
    plt.close(fig)
    print("PASS test_apply_texts_rotation (旋转列透传)")


def test_y_axis_title_no_crash():
    fig = plt.figure()
    ax = fig.add_subplot(111)
    richlabel.add_axis_label(ax, "Current Density (A g^{-1})", which="y",
                              size=SIZE, rise=RISE, drop=DROP)
    fig.canvas.draw()
    plt.close(fig)
    print("PASS test_y_axis_title_no_crash (Y 轴标题可绘制)")


if __name__ == "__main__":
    test_vertical_sup_left()
    test_rotated_vector_general()
    test_add_label_rotlabel()
    test_apply_texts_rotation()
    test_y_axis_title_no_crash()
    print("全部通过")
