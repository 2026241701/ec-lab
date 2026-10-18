# -*- coding: utf-8 -*-
"""上下标渲染：按字号等比缩放 + 垂直偏移，不走 mathtext

为什么不用 mathtext：mathtext 自带一套数学字体，即使设成custom，
字形（斜体样式、负号、间距）跟正文仍然对不上，中文更会变方块。
这里改成把文字拆成若干段，上标/下标只改字号和基线偏移，
所以每一段的字形跟正文完全一致。

用法：
    add_label(ax, "A g^{-1}", (0.5, -0.10), size=14)
    add_label(ax, "Fe_{3}O_{4}", (0.1, 0.5), size=13, rotation=90)
写法：上标 ^{...}（或单个字符 ^-1），下标 _{...}（或 _x）。
"""
import math
import re

from matplotlib.artist import Artist
from matplotlib.text import Text as _Text
from matplotlib.transforms import Bbox, IdentityTransform

CJK_RE = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")
MARK_RE = re.compile(r"([_^])\{([^}]*)\}|([_^])(\S)")


def split_font(txt, west, cjk):
    """按中西文切段：Arial 没有汉字字形，汉字必须交给中文字体"""
    out, buf, cur = [], "", None
    for ch in txt:
        f = cjk if CJK_RE.match(ch) else west
        if cur is not None and f != cur:
            out.append((buf, cur))
            buf = ""
        buf += ch
        cur = f
    if buf:
        out.append((buf, cur or west))
    return out


def parse_markup(text):
    """'A g^{-1}' -> [('A g', 0), ('-1', 1)]；role: 0 正文 / 1 上标 / -1 下标"""
    segs, pos = [], 0
    for m in MARK_RE.finditer(text or ""):
        if m.start() > pos:
            segs.append((text[pos:m.start()], 0))
        if m.group(2) is not None:
            segs.append((m.group(2), 1 if m.group(1) == "^" else -1))
        else:
            segs.append((m.group(4), 1 if m.group(3) == "^" else -1))
        pos = m.end()
    if pos < len(text):
        segs.append((text[pos:], 0))
    return [s for s in segs if s[0]]


def has_markup(text):
    """文字里有没有写上下标（没有的话走普通 ax.text，性能更好）"""
    return bool(MARK_RE.search(text or ""))


def strip_markup(text):
    """去掉上下标记号，只留可读文字（图例列表、提示里用）"""
    return "".join(t for t, _ in parse_markup(text))


class _ShiftedTextArea:
    """占位保留：早期版本用 TextArea 实现，已被 _TextSeg 取代。

    留着名字是为了不破坏可能引用它的地方（实际已无调用点）。
    """

    def __init__(self, *a, **k):
        raise NotImplementedError("已改用 _TextSeg")


class _TextSeg:
    """富文本里的一段文字

    自己管字号、颜色、字型、旋转，并负责：
      · measure()  量出这段的 bbox（相对自身基线左端，单位：点）
      · draw()     直接画到画布绝对像素坐标

    用 Text + IdentityTransform 而不是 TextArea，是为了绕开
    DrawingArea 的 dpi_transform 与 AnnotationBbox 偏移换算打架。
    """

    def __init__(self, text, family, size, color, weight, style, rotation):
        self.text = text
        self.family = family
        self.size = size
        self.color = color
        self.weight = weight
        self.style = style
        self.rotation = rotation
        self.prop = None
        self._descent = 0.0

    def _ensure_prop(self):
        if self.prop is None:
            from matplotlib.font_manager import FontProperties
            p = FontProperties(family=self.family, size=self.size,
                               weight=self.weight or "normal",
                               style=self.style or "normal")
            self.prop = p
        return self.prop

    def measure(self, renderer, ppu):
        """这段文字相对「基线左端」的 bbox，单位：点（y 向上）"""
        p = self._ensure_prop()
        w, h, d = renderer.get_text_width_height_descent(
            self.text, p, False)
        # 基线在 y=0，向上为正：顶 = h - d，底 = -d
        return Bbox.from_bounds(0.0, -d / ppu, w / ppu, h / ppu)

    def make_text(self, x, y, fig):
        """造一个定位到画布绝对像素坐标 (x, y) 的 Text"""
        p = self._ensure_prop()
        t = _Text(x=x, y=y, text=self.text, fontproperties=p,
                  color=self.color, ha="left", va="baseline",
                  rotation=self.rotation, rotation_mode="anchor",
                  transform=IdentityTransform())
        t.set_figure(fig)
        return t

    def draw(self, renderer, x, y, fig):
        self.make_text(x, y, fig).draw(renderer)


def _align(ha, va):
    h = {"left": 0.0, "center": 0.5, "right": 1.0}.get(ha, 0.5)
    v = {"bottom": 0.0, "baseline": 0.0, "center": 0.5,
         "top": 1.0}.get(va, 0.5)
    return (h, v)


def add_label(ax, text, xy, size=12, color="#000000", west="Arial",
              cjk="SimSun", ha="center", va="center", rotation=0.0,
              sub_ratio=0.68, rise=0.40, drop=0.18,
              weight="normal", style="normal", zorder=6, alpha=1.0):
    """往坐标区里加一行带上下标的文字；xy 是 axes 坐标（0~1）

    rotation 支持任意角度：每段文字按 rot 旋转，整体沿旋转后的基线排布，
    上标/下标始终垂直于基线（文字框怎么转，上下标就怎么转）。
    """
    box = _make_box(text, rotation, size, color, west, cjk,
                    sub_ratio, rise, drop, weight, style)
    box.set_figure(ax.figure)
    box.set_alpha(alpha)
    box.set_zorder(zorder)
    holder = _AnchoredLabel(ax, box, xy, _align(ha, va))
    holder.set_zorder(zorder)
    ax.add_artist(holder)
    return holder


class _AnchoredLabel(Artist):
    """把 _RotLabel 钉在 axes 的某个归一化坐标上

    必须在 draw 时才换算成像素：axes 的 bbox 这时才是最终值，
    提前算会随画布尺寸变化而失准。
    """

    def __init__(self, ax, box, xy, align):
        super().__init__()
        self.ax = ax
        self.box = box
        self.xy = tuple(xy)
        self.align = align

    @property
    def offsetbox(self):
        """兼容旧名：早期这里挂的是 matplotlib 的 AnnotationBbox，
        它的 .offsetbox 就是这个 _RotLabel。现在自己画了，属性名改成
        box，老代码/老测试还认 offsetbox，留个别名。"""
        return self.box

    def _anchor_px(self, renderer):
        try:
            bb = self.ax.get_window_extent(renderer)
        except Exception:
            return (0.0, 0.0)
        return (bb.x0 + self.xy[0] * bb.width,
                bb.y0 + self.xy[1] * bb.height)

    def _shift(self, renderer):
        """按 ha/va 把锚点推到框的对应角上（像素）"""
        bb = self.box.get_bbox(renderer)
        ha, va = self.align
        dx = -(bb.x0 + bb.width * ha)
        dy = -(bb.y0 + bb.height * (1.0 - va))
        return dx, dy

    def get_window_extent(self, renderer=None):
        if renderer is None:
            renderer = self.get_figure(root=True)._get_renderer()
        ax_, ay_ = self._anchor_px(renderer)
        dx, dy = self._shift(renderer)
        self.box.set_anchor((ax_ + dx, ay_ + dy))
        return self.box.get_window_extent(renderer)

    def draw(self, renderer):
        if not self.get_visible():
            return
        ax_, ay_ = self._anchor_px(renderer)
        dx, dy = self._shift(renderer)
        self.box.set_anchor((ax_ + dx, ay_ + dy))
        self.box.draw(renderer)


def _make_box(text, rotation, size, color, west, cjk,
              sub_ratio, rise, drop, weight, style,
              sub_dx=0.0, sup_dx=0.0):
    return _RotLabel(text, size, color, west, cjk, sub_ratio, rise, drop,
                     weight, style, sub_dx=sub_dx, sup_dx=sup_dx,
                     rot=rotation)


def add_axis_label(ax, text, which="x", size=12, color="#000000",
                   west="Arial", cjk="SimSun", gap=6,
                   sub_ratio=0.68, rise=0.40, drop=0.18,
                   weight="normal", style="normal", zorder=6,
                   shift=(0.0, 0.0), sub_dx=0.0, sup_dx=0.0):
    """把轴标题贴在坐标区外面。

    关键做法：原生 xlabel/ylabel 里塞一份"占位文字"（无上下标的那份），
    让 matplotlib 自己把边距、刻度、标签位置全算好；绘制时再把真正的
    富文本盖在占位文字上。这样换字号、换刻度数量都不会跑位或被裁掉。

    shift = (dx, dy)：在算好的位置上再手动微调，单位是点（1/72 英寸），
    往右/往上为正。用来微调标题对不对齐、会不会压到刻度上。
    """
    holder = _AxisRichLabel(ax, text, which, size=size, color=color,
                            west=west, cjk=cjk, gap=gap,
                            sub_ratio=sub_ratio, rise=rise, drop=drop,
                            weight=weight, style=style, zorder=zorder,
                            shift=shift, sub_dx=sub_dx, sup_dx=sup_dx)
    ax.add_artist(holder)
    return holder


class _AxisRichLabel(Artist):
    """按 matplotlib 算好的标签位置摆放富文本轴标题"""

    def __init__(self, ax, text, which="x", **kw):
        super().__init__()
        self.ax = ax
        self.which = which
        self.gap = kw.pop("gap", 6)
        self.shift = tuple(kw.pop("shift", (0.0, 0.0)) or (0.0, 0.0))
        self.kw = kw
        size = kw.get("size", 12)
        rot = 90.0 if which == "y" else 0.0
        self.box = _make_box(text, rot, size, kw.get("color", "#000"),
                             kw.get("west", "Arial"),
                             kw.get("cjk", "SimSun"),
                             kw.get("sub_ratio", 0.68),
                             kw.get("rise", 0.40),
                             kw.get("drop", 0.18),
                             kw.get("weight", "normal"),
                             kw.get("style", "normal"),
                             kw.get("sub_dx", 0.0), kw.get("sup_dx", 0.0))
        self.box.set_figure(ax.figure)
        # 锚点放在框的"贴刻度那一侧"：X 轴是顶边中点，Y 轴是右边中点。
        # 这样只要锚点落在刻度字外侧 gap 个点，整块字就一定不会压到刻度。
        self.align = (0.5, 1.0) if which == "x" else (1.0, 0.5)
        self.set_zorder(kw.get("zorder", 6))
        # 占位文字要"透明"而不是"隐藏"：set_visible(False) 会让 matplotlib
        # 在排版时跳过它，标签就会压在刻度数字上。透明则照样占位。
        native = ax.xaxis.label if which == "x" else ax.yaxis.label
        native.set_fontsize(size)
        native.set_alpha(0.0)

    def get_window_extent(self, renderer=None):
        if renderer is None:
            renderer = self.get_figure(root=True)._get_renderer()
        self.box.set_anchor(self._center(renderer))
        return self.box.get_window_extent(renderer)

    def _label_center(self, renderer):
        """算富文本轴标题该挂在哪个像素位置（窗口坐标）

        直接量原生占位标签的 bbox，把富文本盖在它上面 ——
        matplotlib 算边距时已经把"刻度线长 + 刻度字厚 + labelpad +
        标题字号"全算进去了，我们只要对齐，就绝不会压到刻度上，
        刻度数量、字号、刻度朝向变了也都自动跟着走。
        早先这里自己重算"刻度字外侧 gap 个点"，跟 matplotlib 的实际
        排版对不上（gap 是像素、labelpad 是点，两套单位），标题会压住
        刻度数字，所以 gap 现在只当"占位标签找不到时的兜底"。

        早先试过照公式重算，也是同一个坑：那个公式算的是刻度线那侧，
        刻度朝外/朝内时差一截。量真实 bbox 最稳。
        """
        ax = self.ax
        native = ax.xaxis.label if self.which == "x" else ax.yaxis.label
        try:
            bb = native.get_window_extent(renderer)
            if bb.width > 0 and bb.height > 0:
                return ((bb.x0 + bb.x1) / 2.0, (bb.y0 + bb.y1) / 2.0)
        except Exception:
            pass
        # 兜底：占位标签量不到（极少见），退回"刻度字外侧 gap 个点"
        is_x = self.which == "x"
        try:
            ax_bb = ax.get_window_extent(renderer)
        except Exception:
            return None
        cx, cy = (ax_bb.x0 + ax_bb.x1) / 2.0, (ax_bb.y0 + ax_bb.y1) / 2.0
        try:
            axis = ax.xaxis if is_x else ax.yaxis
            boxes = [t.get_window_extent(renderer)
                     for t in axis.get_ticklabels()
                     if t.get_visible() and t.get_text()]
            boxes = [b for b in boxes if b.width > 0 and b.height > 0]
        except Exception:
            boxes = []
        if is_x:
            edge = min((b.y0 for b in boxes), default=ax_bb.y0)
            return (cx, edge - self.gap)
        edge = min((b.x0 for b in boxes), default=ax_bb.x0)
        return (edge - self.gap, cy)

    def _center(self, renderer):
        pos = self._label_center(renderer)
        if pos is None:
            ax_bb = self.ax.get_window_extent(renderer)
            pos = ((ax_bb.x0 + ax_bb.x1) / 2.0,
                   ax_bb.y0 - self.gap)
        x, y = pos
        # 手动微调：shift 单位是点，转成像素
        try:
            ppu = renderer.points_to_pixels(1.0) or 1.0
        except Exception:
            ppu = 1.0
        return (x + self.shift[0] * ppu, y + self.shift[1] * ppu)

    def _set_xy(self, xy):
        """挪动富文本框（锚点，画布像素坐标）"""
        self.box.set_anchor((float(xy[0]), float(xy[1])))

    def draw(self, renderer):
        if not self.get_visible():
            return
        x, y = self._center(renderer)
        self._set_xy((x, y))
        # 用户手动微调过就不兜底：微调的作用就是把标题挪到自己想要的位置，
        # 越界挪回来等于微调没生效（"往左调没反应"）。
        # 没微调时才防裁：画布一小（比如预览窗缩小、适应窗口），
        # 刻度数字不会同比缩小，标题会被裁到画布外 —— 表现就是
        # "Y 轴标题突然没了"。
        if not any(self.shift):
            self._keep_inside(renderer)
        self.box.draw(renderer)

    def _keep_inside(self, renderer):
        """把标题夹回画布内（画布一小它就会被裁掉）

        标题位置是"刻度字外侧 gap 个点"算出来的，画布一小（比如预览窗
        缩小、适应窗口），刻度数字却不会同比缩小，算出来的 x 就成了负数，
        整块标题被裁到画布外 —— 表现就是"Y 轴标题突然没了"。
        这里量一次真实 bbox，超出画布就平移回来。
        """
        try:
            bb = self.box.get_window_extent(renderer)
            fb = self.ax.figure.get_window_extent(renderer)
        except Exception:
            return
        pad = 2.0
        dx = dy = 0.0
        if bb.x1 - bb.x0 < fb.width:
            if bb.x0 < fb.x0 + pad:
                dx = fb.x0 + pad - bb.x0
            elif bb.x1 > fb.x1 - pad:
                dx = fb.x1 - pad - bb.x1
        else:
            dx = (fb.x0 + fb.x1) / 2.0 - (bb.x0 + bb.x1) / 2.0
        if bb.y1 - bb.y0 < fb.height:
            if bb.y0 < fb.y0 + pad:
                dy = fb.y0 + pad - bb.y0
            elif bb.y1 > fb.y1 - pad:
                dy = fb.y1 - pad - bb.y1
        else:
            dy = (fb.y0 + fb.y1) / 2.0 - (bb.y0 + bb.y1) / 2.0
        if dx or dy:
            self._set_xy((self.box._anchor[0] + dx,
                          self.box._anchor[1] + dy))


class _RotLabel(Artist):
    """任意旋转角的富文本框

    每段文字按 rot 旋转（textprops.rotation），整体沿"旋转后的基线"依次
    排布；上标/下标按文字框旋转角换算到垂直于基线的方向。

    为什么自己画而不沿用 DrawingArea + TextArea：
    matplotlib 3.11 的 AnnotationBbox 已无 box_rotation 参数，
    OffsetBox.set_transform 又被忽略，只能逐段文字级旋转 + 手动 2D 摆位。
    但只要还挂在 AnnotationBbox 的 offsetbox 位置上，DrawingArea.draw()
    里的 dpi_transform.scale() 就会和 AnnotationBbox.update_positions()
    算出的像素偏移打架 —— 报出来的位置对、画出来的位置整体偏一个 ppu 倍
    （100 dpi 下 1.39 倍），轴标题会跑到画布左下角被裁掉。
    干脆跟图例富文本（LegendRichText）用同一套做法：
    每段一个 Text + IdentityTransform，直接画到画布绝对坐标。
    """

    def __init__(self, text, size, color, west, cjk, sub_ratio, rise, drop,
                 weight, style, sub_dx=0.0, sup_dx=0.0, rot=0.0):
        super().__init__()
        self._fig = None
        self._rot = float(rot or 0) % 360.0
        th = math.radians(self._rot)
        # 旋转后 reading 方向 (rx, ry)、垂直于基线向外(上) (nx, ny)
        # 取 matplotlib 约定（逆时针为正、+y 向上）
        self._rx, self._ry = math.cos(th), math.sin(th)
        self._nx, self._ny = -math.sin(th), math.cos(th)
        # items: (TextSeg, 片段文字, 字号, perp 抬升量, along 微调量)
        self._items = []
        for txt, role in parse_markup(text or ""):
            fs = size * (1.0 if role == 0 else sub_ratio)
            perp = (rise if role == 1 else (-drop if role == -1
                                            else 0.0)) * size
            along = (sup_dx if role == 1 else (sub_dx if role == -1
                                               else 0.0)) * size
            for frag, fam in split_font(txt, west, cjk):
                self._items.append(
                    (_TextSeg(frag, fam, fs, color, weight, style, self._rot),
                     frag, fs, perp, along))
        self._ppu = 1.0
        self._total = 0.0
        self._anchor = (0.0, 0.0)
        # 缓存：draw 与 get_window_extent 共用同一批 Text 对象，
        # 保证"量出来的框"和"画出来的字"是同一份数据。
        self._ckey = None
        self._cache = []

    def set_figure(self, fig):
        self._fig = fig
        super().set_figure(fig)

    # ---------- 排版 ----------

    def _place(self, renderer, anchor):
        """按锚点造出实际要画的 Text 列表（同一批对象供量取和绘制共用）

        排布规则：整块字沿"旋转后的阅读方向"居中放在锚点上，
        垂直方向以锚点为基线（上下标只做垂直偏移）。
        """
        ppu = renderer.points_to_pixels(1.0) or 1.0
        self._ppu = ppu
        # 先量总宽（单位：点）
        widths = []
        total = 0.0
        for seg, frag, fs, perp, along in self._items:
            wpx = renderer.get_text_width_height_descent(
                frag, seg._ensure_prop(), False)[0]
            wpts = wpx / ppu
            widths.append(wpts)
            total += wpts
        self._total = total
        half = total / 2.0
        fig = self._fig or self.get_figure(root=True)
        ax_, ay_ = anchor
        texts = []
        cum = 0.0
        for (seg, frag, fs, perp, along), wpts in zip(self._items, widths):
            # 沿基线的位置（居中后再转 90° 就变成沿 y 居中）
            t_along = cum - half + along
            # 旋转后的偏移（display 帧，+y 向上）：
            #   垂直向量 (0, perp) 转 θ -> (-perp·sinθ, perp·cosθ)
            #   沿基线向量 (t_along, 0) 转 θ -> (t_along·cosθ, t_along·sinθ)
            ox = self._rx * t_along + self._nx * perp
            oy = self._ry * t_along + self._ny * perp
            texts.append(seg.make_text(ax_ + ox * ppu, ay_ + oy * ppu, fig))
            cum += wpts
        return texts

    def _texts(self, renderer, anchor):
        """带缓存的 _place：同一锚点+dpi 只重排一次"""
        key = (round(anchor[0], 2), round(anchor[1], 2),
               round(self._ppu_of(renderer), 4))
        if self._ckey == key:
            return self._cache
        self._ckey = key
        self._cache = self._place(renderer, anchor)
        return self._cache

    @staticmethod
    def _ppu_of(renderer):
        try:
            return renderer.points_to_pixels(1.0) or 1.0
        except Exception:
            return 1.0

    def get_bbox(self, renderer):
        """相对锚点（锚点为原点）的 bbox，单位：像素"""
        texts = self._texts(renderer, (0.0, 0.0))
        if not texts:
            return Bbox.from_bounds(0.0, 0.0, 0.0, 0.0)
        return Bbox.union([t.get_window_extent(renderer) for t in texts])

    def get_window_extent(self, renderer=None):
        if renderer is None:
            renderer = self.get_figure(root=True)._get_renderer()
        texts = self._texts(renderer, self._anchor)
        if not texts:
            return Bbox.from_bounds(self._anchor[0], self._anchor[1],
                                    self._anchor[0], self._anchor[1])
        return Bbox.union([t.get_window_extent(renderer) for t in texts])

    def set_anchor(self, xy):
        """设锚点（画布像素坐标）。绘制与量取都以它为基准。"""
        self._anchor = (float(xy[0]), float(xy[1]))

    def draw(self, renderer):
        if not self.get_visible():
            return
        for t in self._texts(renderer, self._anchor):
            t.draw(renderer)


# ==================================================================
# 图例富文本：让图例里的上下标跟正文一个字形（不走 mathtext）
# ==================================================================
#
# matplotlib 图例文字只支持 mathtext（$...$），而 mathtext 自带数学字体：
# 字母一律斜体、字形跟正文对不上，缩放比也没法控制。
# 这里的做法跟轴标题一样 —— 原生图例文字只当"占位符"（透明但占着位置，
# 图例框、行距全按它排），画图时再把逐段缩放/偏移的真文字盖上去。

from matplotlib.artist import Artist as _Artist  # noqa: F401  (兼容旧引用)


class LegendRichText(_Artist):
    """把图例里带 ^{}/_{} 标记的行画成富文本

    pairs: [(图例第几行, parse_markup 的结果), ...]
    rise/drop/sub_ratio 等直接来自「画布/字体」页的上下标栏，
    所以那里调比例，图例跟着变。
    """

    def __init__(self, leg, pairs, sub_ratio=0.68, rise=0.40, drop=0.18,
                 sup_dx=0.0, sub_dx=0.0, west=None, cjk=None):
        """pairs: [(图例行号, 带 ^{}/_{} 标记的原文), ...]"""
        super().__init__()
        self.leg = leg
        self.pairs = [(i, str(txt)) for i, txt in pairs]
        self.sub_ratio = float(sub_ratio)
        self.rise = float(rise)
        self.drop = float(drop)
        self.sup_dx = float(sup_dx)
        self.sub_dx = float(sub_dx)
        self.west = west
        self.cjk = cjk
        for i, _segs in pairs:          # 原生文字只占位，不真正画出来
            try:
                leg.texts[i].set_alpha(0.0)
            except Exception:
                pass
        try:
            self.set_zorder(leg.get_zorder() + 0.1)
        except Exception:
            self.set_zorder(6)

    def _segments(self, txt):
        """[(片段, 字体, 字号比, 抬升量, 左右微调), ...]"""
        west = self.west
        cjk = self.cjk or west
        for part, role in parse_markup(txt):
            ratio = 1.0 if role == 0 else self.sub_ratio
            dy = (self.rise if role == 1
                  else -self.drop if role == -1 else 0.0)
            dx = (self.sup_dx if role == 1
                  else self.sub_dx if role == -1 else 0.0)
            for frag, fam in split_font(part, west, cjk):
                yield frag, fam, ratio, dy, dx

    def draw(self, renderer):
        if not self.get_visible():
            return
        fig = self.leg.figure
        try:
            ppu = renderer.points_to_pixels(1.0) or 1.0
        except Exception:
            ppu = 1.0
        for i, markup in self.pairs:
            try:
                t = self.leg.texts[i]
                if not markup:
                    continue
                bb = t.get_window_extent(renderer)
                # 基线 = 占位文字 bbox 底边 + 这串字自己的下降部
                _w, _h, desc = renderer.get_text_width_height_descent(
                    t.get_text() or markup, t.get_fontproperties(), False)
                base = bb.y0 + desc
                size0 = t.get_fontproperties().get_size_in_points()
                color = t.get_color()
                x = bb.x0
                for frag, fam, ratio, dy, dx in self._segments(markup):
                    prop = t.get_fontproperties().copy()
                    prop.set_family(fam)
                    prop.set_size(size0 * ratio)
                    w = renderer.get_text_width_height_descent(
                        frag, prop, False)[0]
                    seg = _Text(x=x + dx * size0 * ppu,
                                y=base + dy * size0 * ppu,
                                text=frag, fontproperties=prop,
                                color=color, ha="left", va="baseline",
                                transform=IdentityTransform())
                    seg.set_figure(fig)
                    seg.draw(renderer)
                    x += w
            except Exception:
                continue
