# -*- coding: utf-8 -*-
"""验证：图例文字里把上下标那几段单独包进 $...$ 后，matplotlib 能不能正常渲染"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["mathtext.fontset"] = "custom"
matplotlib.rcParams["mathtext.rm"] = "Arial"
matplotlib.rcParams["mathtext.it"] = "Arial:italic"
matplotlib.rcParams["mathtext.bf"] = "Arial:bold"
matplotlib.rcParams["mathtext.default"] = "it"
matplotlib.rcParams["font.family"] = ["Arial"]

fig, ax = plt.subplots(figsize=(3, 2))
ax.plot([0, 1], [0, 1], label="A g$^{-1}$")        # 上标，base 在 math 外
ax.plot([0, 1], [1, 0], label="Fe$_{3}$O$_{4}$")   # 下标
ax.plot([0, 1], [0.5, 0.5], label="50 mV s$^{-1}$")
leg = ax.legend()
fig.canvas.draw()
print("OK 渲染没报错")
for t in leg.get_texts():
    print("  ->", repr(t.get_text()))
plt.close(fig)

# 再试中文 + 上下标混排（中文留在 math 外）
fig, ax = plt.subplots(figsize=(3, 2))
ax.plot([0, 1], [0, 1], label="电流密度 A g$^{-1}$")
leg = ax.legend()
fig.canvas.draw()
print("OK 中文+上标也没报错")
plt.close(fig)
