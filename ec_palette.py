# -*- coding: utf-8 -*-
"""
配色存储 —— 存配色、找配色、记用户用过的颜色
==========================================
放在 eclab.py 里，因为它属于"绘图外观"这一层，CLI 和界面都能用。

设计要点：
1. 存哪儿固定死在 PROFILE_DIR，不让用户每次都选路径（用户明确要求）。
2. 配色就是一排颜色块，看色块挑就行。旧版那个独立的"配色库浏览器"
   （画 CV 曲线缩略图 + 一堆 png）已按用户要求取消，功能全部并进
   调色盘的「配色方案」页。
3. 记住用户用过的每个颜色（recents）和他自己攒的颜色组（groups），
   下次打开调色盘直接能拿到。
"""

import os
import json
import time
import zipfile

# 用户数据目录：放 AppData，不污染程序目录，也方便备份
PROFILE_DIR = os.path.join(os.path.expanduser("~"), "ec-lab 数据")
PALETTE_DIR = os.path.join(PROFILE_DIR, "我的配色")
PALETTE_JSON = os.path.join(PALETTE_DIR, "_记忆.json")
RECENT_MAX = 60          # 最近用过的颜色记多少个
GROUP_MAX = 40           # 自定义颜色组记多少组

# ---------- 记忆文件 ----------
_DEF_MEMORY = {"recents": [], "groups": [], "counter": 0}


def _ensure_dir():
    os.makedirs(PALETTE_DIR, exist_ok=True)


def load_memory():
    """读记忆文件；坏文件直接当空的，不让程序起不来"""
    try:
        with open(PALETTE_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return json.loads(json.dumps(_DEF_MEMORY))
    if not isinstance(data, dict):
        return json.loads(json.dumps(_DEF_MEMORY))
    data.setdefault("recents", [])
    data.setdefault("groups", [])
    data.setdefault("counter", 0)
    return data


def save_memory(mem):
    _ensure_dir()
    tmp = PALETTE_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PALETTE_JSON)


def remember_color(hexcolor):
    """记住这个颜色（用户用过的），放到最前面"""
    c = (hexcolor or "").strip().upper()
    if not c.startswith("#") or len(c) not in (4, 7):
        return
    mem = load_memory()
    rec = [x for x in mem["recents"] if x.upper() != c]
    rec.insert(0, c)                  # 放最前 = 最近用
    mem["recents"] = rec[:RECENT_MAX]
    save_memory(mem)


def remember_group(name, colors):
    """记住一整组颜色（配色方案）"""
    cols = [str(c).strip().upper() for c in colors if str(c).strip()]
    if not cols:
        return
    mem = load_memory()
    groups = [g for g in mem["groups"]
              if [c.upper() for c in g.get("colors", [])] != cols]
    groups.insert(0, {"name": name or "我的配色", "colors": cols,
                      "saved": time.strftime("%Y-%m-%d %H:%M")})
    mem["groups"] = groups[:GROUP_MAX]
    save_memory(mem)


# ---------- 配色文件 ----------
def _safe_name(name):
    """文件名安全化：去掉路径分隔符和 Windows 非法字符"""
    out = "".join("_" if c in '\\/:*?"<>|' else c for c in str(name))
    out = out.strip().strip(".") or "未命名"
    return out[:60]


def save_palette(name, colors):
    """存一套配色到固定目录，不弹路径选择框

    name 留空就自动按时间起名。同名会写成 名称_2、名称_3，不会覆盖。
    返回存出来的 json 路径。
    """
    cols = [str(c).strip().upper() for c in colors if str(c).strip()]
    if not cols:
        return None
    _ensure_dir()
    mem = load_memory()
    base = _safe_name(name) if name else time.strftime("配色_%m%d_%H%M%S")
    stem, n = base, 1
    while os.path.exists(os.path.join(PALETTE_DIR, stem + ".json")):
        n += 1
        stem = f"{base}_{n}"
    mem["counter"] = n
    save_memory(mem)

    path = os.path.join(PALETTE_DIR, stem + ".json")
    payload = {"名称": name or stem, "颜色": cols,
               "保存时间": time.strftime("%Y-%m-%d %H:%M")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    remember_group(name or stem, cols)
    remember_color(cols[0])
    return path


def _read_palette_json(path):
    """读一个配色 json，各种字段名都认一下，兼容老文件"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if isinstance(data, list):
        return {"名称": os.path.splitext(os.path.basename(path))[0],
                "颜色": [str(c) for c in data]}
    if not isinstance(data, dict):
        return None
    cols = (data.get("颜色") or data.get("colors")
            or data.get("palette") or [])
    cols = [str(c).strip().upper() for c in cols if str(c).strip()]
    if not cols:
        return None
    name = (data.get("名称") or data.get("name")
            or os.path.splitext(os.path.basename(path))[0])
    return {"名称": str(name), "颜色": cols,
            "保存时间": data.get("保存时间", "")}


def scan_palettes(*extra_dirs):
    """扫描配色目录 + 额外目录，返回 [{名称,颜色,来源}]

    额外目录支持：文件夹（含子目录）、zip 压缩包、单个 json 文件。
    """
    out, seen, used_names = [], set(), {}

    def add(name, cols, src):
        """去重后收进列表；被去重返回 None

        颜色完全相同但名字不同时，不丢名字，而是把新名字记成别名 ——
        比如自己的配色和导师给的配色颜色一样，两个名字都得留着。
        """
        key = tuple(c.upper() for c in cols)
        if not key:
            return None
        if key in seen:
            for prev in out:
                if tuple(c.upper() for c in prev["颜色"]) == key:
                    nm = str(name)
                    if (nm and nm != prev["名称"]
                            and nm not in prev.get("别名", [])):
                        prev.setdefault("别名", []).append(nm)
                    break
            return None
        seen.add(key)
        # 同名但颜色不同的会有多套（用户允许重名保存），
        # 显示时加个序号，免得界面上两排一模一样的名字分不清
        disp = str(name)
        if disp in used_names:
            used_names[disp] += 1
            disp = f"{disp} ({used_names[disp]})"
        else:
            used_names[disp] = 1
        item = {"名称": disp, "原名": str(name), "颜色": cols,
                "来源": src}
        out.append(item)
        return item

    # 1) 我存的配色
    if os.path.isdir(PALETTE_DIR):
        for fn in sorted(os.listdir(PALETTE_DIR)):
            if not fn.lower().endswith(".json") or fn.startswith("_"):
                continue
            p = os.path.join(PALETTE_DIR, fn)
            got = _read_palette_json(p)
            if not got:
                continue
            add(got["名称"], got["颜色"], p)

    # 2) 记忆里的颜色组
    for g in load_memory().get("groups", []):
        add(g.get("name", "我的配色"), g.get("colors", []), "记忆")

    # 3) 外部文件夹 / zip / 单个 json
    for src in extra_dirs:
        if not src:
            continue
        if os.path.isfile(src) and src.lower().endswith(".zip"):
            _scan_zip(src, add)
        elif os.path.isfile(src) and src.lower().endswith(".json"):
            got = _read_palette_json(src)
            if got:
                add(got["名称"], got["颜色"], src)
        elif os.path.isdir(src):
            for root, _dirs, files in os.walk(src):
                for fn in sorted(files):
                    fp = os.path.join(root, fn)
                    if fn.lower().endswith(".zip"):
                        _scan_zip(fp, add)
                    elif fn.lower().endswith(".json"):
                        got = _read_palette_json(fp)
                        if got:
                            add(got["名称"], got["颜色"], fp)
    return out


def _scan_zip(zpath, add):
    """从 zip 里找配色 json（不整包解压，直接读，省事又安全）"""
    try:
        with zipfile.ZipFile(zpath) as z:
            for nm in z.namelist():
                if not nm.lower().endswith(".json"):
                    continue
                try:
                    data = json.loads(z.read(nm).decode("utf-8", "ignore"))
                except Exception:
                    continue
                if isinstance(data, dict):
                    cols = (data.get("颜色") or data.get("colors") or [])
                    nm_in = (data.get("名称") or data.get("name") or "")
                elif isinstance(data, list):
                    cols, nm_in = data, ""
                else:
                    continue
                cols = [str(c).strip().upper() for c in cols if str(c).strip()]
                if not cols:
                    continue
                name = str(nm_in).strip() or os.path.splitext(
                    os.path.basename(nm))[0]
                add(name, cols, f"{zpath} → {nm}")
    except Exception:
        pass


def _forget_group(name, colors):
    """从记忆里去掉一组颜色。

    配色方案同时存在两个地方：配色目录里的 json（真身）和记忆里的副本。
    只删 json 的话，记忆那份还在，scan_palettes 又会把它捞出来 ——
    界面上看着像"删不掉"。所以删除和改名都得把记忆副本一起清掉。
    """
    want = [str(c).strip().upper() for c in (colors or []) if str(c).strip()]
    nm = str(name or "")
    mem = load_memory()
    old = mem["groups"]
    new = [g for g in old
           if not (str(g.get("name", "")) == nm
                   and [str(c).strip().upper()
                        for c in g.get("colors", [])] == want)]
    if len(new) != len(old):
        mem["groups"] = new
        save_memory(mem)
        return True
    return False


def delete_palette(item):
    """删掉自己存的一套配色（只在我存的目录里才允许删）

    真身（json）和记忆里的副本一起删，不然界面上删了还会再冒出来。
    """
    src = item.get("来源") or ""
    d = os.path.dirname(src) if src else ""
    if os.path.normpath(d) != os.path.normpath(PALETTE_DIR):
        return False
    old = _read_palette_json(src) or {}
    ok = False
    try:
        os.remove(src)
        ok = True
    except Exception:
        pass
    _forget_group(old.get("名称", item.get("名称", "")), old.get("颜色", []))
    _forget_group(item.get("原名", item.get("名称", "")), item.get("颜色", []))
    return ok


def update_palette(item, name, colors):
    """编辑自己存的配色：直接覆盖原 json（只在我存的目录里才允许）。

    item 是 scan_palettes 返回的那条；返回新路径，失败返回 None。
    """
    src = item.get("来源") or ""
    d = os.path.dirname(src) if src else ""
    if os.path.normpath(d) != os.path.normpath(PALETTE_DIR):
        return None
    cols = [str(c).strip().upper() for c in colors if str(c).strip()]
    if not cols or not name.strip():
        return None
    path = os.path.join(PALETTE_DIR, os.path.basename(src))
    # 先记下改之前叫什么、什么色，改完把记忆里那条老记录清掉，
    # 否则老名字还会被扫出来，看着像"改名没生效"
    old = _read_palette_json(path) or {}
    payload = {"名称": name.strip(), "颜色": cols,
               "保存时间": time.strftime("%Y-%m-%d %H:%M")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    _forget_group(old.get("名称", ""), old.get("颜色", []))
    remember_group(name.strip(), cols)
    return path