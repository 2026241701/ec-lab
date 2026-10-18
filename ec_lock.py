# -*- coding: utf-8 -*-
"""ec-lab 协作锁：多个人（多个 AI）同时改同一个项目时的秩序保障

## 为什么需要它

Ding 会同时开好几个项目窗口（有时是多个 AI 助手）改同一个软件。
问题是它们都在改 `ec_gui.py` 这一个文件，互相看不见对方：

  - 甲改完准备收工，乙不知道，把甲的改动覆盖了
  - 甲正在改配色，乙同时改主窗口，两个都写坏
  - 甲跑测试报「_refresh_swatch 不存在」，其实是乙写到一半 —— 白查半小时

**光靠约定没用**，必须有一个所有人都必须经过的关卡。这个文件就是那道关。

## 规矩（三条，任何 AI 都必须遵守）

1. **动手改之前先 `python ec_lock.py take <名字>`**
   拿不到锁 → 只能读文件和思考，**绝对不能写 ec_gui.py / eclab.py 等代码**
   拿不到锁时应该：读代码 → 写下打算怎么改 → 告诉 Ding「我在等谁」→ 去改别的文件

2. **改完立刻 `python ec_lock.py release <名字>`**
   哪怕改失败了、只改了一半，也必须还钥匙。不还锁别人会一直干等。

3. **还锁之前必须跑测试**
   `python ec_lock.py release <名字> --test`
   测试不过就不该还锁给别人（你改坏了，别人接手更惨）。

## 命令

    python ec_lock.py take A      拿锁，开始改
    python ec_lock.py status       看现在是谁在改、已持有多久
    python ec_lock.py release A    还锁（建议加 --test 自动跑测试）
    python ec_lock.py release A --force   测试没过但必须还锁时用
    python ec_lock.py whoami       我这次该叫什么名字（按窗口自动猜）
    python ec_lock.py test         单独跑一遍所有测试
    python ec_lock.py handover     写交接便条，让下一个人知道进度
    python ec_lock.py handover -m "已经加完横向下拉框，接下来处理配色"
    python ec_lock.py read         看交接便条

## 名字怎么取

`whoami` 会自动猜一个（基于时间），比如 `A` / `B` / `C`。
想固定用同一个名字（比如你手上这个窗口一直叫「配色」）：

    python ec_lock.py take 配色

名字只要不重复就行，中文英文都可以。
"""

import os
import sys
import json
import time
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
LOCK_DIR = os.path.join(BASE, "_collab")
LOCK_FILE = os.path.join(LOCK_DIR, "lock.json")
LOG_FILE = os.path.join(LOCK_DIR, "history.log")
HANDOVER = os.path.join(LOCK_DIR, "handover.md")

# 超过这个时间（秒）认为是拿着钥匙忘了还，自动作废
STALE_SEC = 3600          # 1 小时

# 这些文件别人正在改时绝对不许写
PROTECTED = ["ec_gui.py", "eclab.py", "ec_palette.py", "richlabel.py",
             "config.json"]

PY = sys.executable


# ==================================================================
# 底层
# ==================================================================

def _ensure_dir():
    os.makedirs(LOCK_DIR, exist_ok=True)


def _read_lock():
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_lock(d):
    _ensure_dir()
    # 原子写：万一同时有两个人写，也不会写出半个文件
    tmp = LOCK_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LOCK_FILE)


def _log(line):
    _ensure_dir()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + line + "\n")


def guess_name():
    """自动猜一个名字：按当前时间映射到 A/B/C，避免撞名"""
    slot = int(time.time() / 900) % 6
    return "ABCDEF"[slot]


# ==================================================================
# 命令
# ==================================================================

def cmd_take(name=None):
    name = name or guess_name()
    cur = _read_lock()

    # 拿到过期的空壳锁（还锁后留下的）当没有
    if cur and not cur.get("name"):
        cur = None

    if cur:
        held = time.time() - (cur.get("since") or time.time())
        if held > STALE_SEC:
            _log(f"[自动作废] {cur.get('name')} 拿了 {held/60:.0f} 分钟没还，"
                 f"钥匙收回")
            cur = None
        elif cur.get("name") != name:
            print("!! 拿不到钥匙")
            print("   正在改的人：%s（已持有 %.0f 分钟）"
                  % (cur.get("name"), held / 60))
            print("   你要改的文件：%s" % "、".join(cur.get("files", [])))
            print()
            print("   现在该做什么：")
            print("   1. 只读代码、想清楚要怎么改（不要写任何代码文件）")
            print("   2. python ec_lock.py handover -m \"你的想法\""
                  "   把想法留给他")
            print("   3. 跟 Ding 说「我在等 %s 改完 %s」"
                  % (cur.get("name"), cur.get("doing", "它手上的东西")))
            print("   4. 去改不会冲突的文件，或等一会儿再试")
            print()
            print("   锁太旧可以强制拿：python ec_lock.py steal")
            return 1

    _write_lock({"name": name, "since": time.time(),
                 "files": PROTECTED, "pid": os.getpid()})
    _log(f"[拿锁] {name} 开始改")
    print("钥匙已拿到：%s" % name)
    print("现在可以改：%s" % "、".join(PROTECTED))
    print("改完立刻跑：python ec_lock.py release %s --test" % name)
    return 0


def cmd_release(name=None, run_test=False, force=False):
    cur = _read_lock()
    if not cur or not cur.get("name"):
        print("现在没有人持有钥匙，不用还。")
        return 0
    # 不给名字就默认还当前持有者那把锁 —— AI 常常拿锁时用一个名字、
    # 还锁时忘了用同一个，强制要求一致反而容易卡住
    holder = cur.get("name")
    if name and name != holder and not force:
        print("钥匙在 %s 手里，不是 %s 的。" % (holder, name))
        print("   直接还锁（不指定名字）：python ec_lock.py release --test")
        print("   或强制还：python ec_lock.py release %s --force" % holder)
        return 1
    name = holder

    held = time.time() - (cur.get("since") or time.time())
    ok = True

    if run_test and not force:
        print("跑测试中…（测试过了才还锁）")
        ok = run_tests()

    if ok:
        _write_lock({"name": None, "since": None, "files": []})
        _log(f"[还锁] {name} 持有 {held/60:.1f} 分钟")
        print("钥匙已归还（持有 %.1f 分钟）。" % (held / 60))
        if os.path.isfile(HANDOVER):
            print("下一个人会看到你的交接便条。")
        return 0
    else:
        print()
        print("!! 测试没过，钥匙暂时不放。")
        print("   别人接手会一起坏。先把问题修好，或确认要放弃时：")
        print("   python ec_lock.py release %s --force" % name)
        return 1


def cmd_steal():
    """强制拿锁：确认前一个人已经不干了才用"""
    cur = _read_lock()
    if not cur:
        return cmd_take()
    old = cur.get("name")
    held = time.time() - (cur.get("since") or time.time())
    print("强行拿锁，会覆盖 %s 的记录（已持有 %.0f 分钟）"
          % (old, held / 60))
    ans = input("确认 %s 已经不干了吗？输入 y 确认：" % old)
    if ans.strip().lower() in ("y", "yes"):
        _log(f"[抢锁] {guess_name()} 从 {old} 手里抢走")
        _write_lock({"name": None, "since": None, "files": []})
        return cmd_take()
    print("已取消。")
    return 1


def cmd_status():
    cur = _read_lock()
    print("=" * 56)
    print("  ec-lab 协作状态")
    print("=" * 56)
    if cur and cur.get("name"):
        held = time.time() - (cur.get("since") or time.time())
        print("  钥匙在：%s" % cur["name"])
        print("  已持有：%.1f 分钟%s"
              % (held / 60,
                 "（超过 1 小时算失效，可以抢）" if held > STALE_SEC else ""))
        print("  正在改：%s" % "、".join(cur.get("files", [])))
    else:
        print("  钥匙空闲，可以直接开始改：")
        print("    python ec_lock.py take <你的名字>")
    print()
    if os.path.isfile(HANDOVER):
        print("-" * 56)
        print("交接便条：")
        print(open(HANDOVER, encoding="utf-8").read())
    print("=" * 56)
    return 0


def cmd_handover(msg=None):
    _ensure_dir()
    if msg is None:
        print("当前交接便条：")
        print(open(HANDOVER, encoding="utf-8").read()
              if os.path.isfile(HANDOVER) else "（还没有）")
        return 0
    with open(HANDOVER, "w", encoding="utf-8") as f:
        f.write(time.strftime("%m-%d %H:%M ") + msg + "\n")
    _log("[交接] " + msg[:60])
    print("已记下。下一个人拿锁时会看到。")
    return 0


def run_tests():
    """跑门禁测试，全过才算没改坏。

    判定以**退出码**为准 —— 各测试脚本自己最清楚过没过。
    退出码为 0 就算过，非 0 就算挂并打印末尾输出便于排查。

    门禁只认维护中的两个：
      - regress_check.py  回归基线（合成档锁定计算公式）
      - smoke_test.py     离屏冒烟（配置保险箱 / 引擎数据流 / 界面 / 出图）
    更全的界面套件在 _tests/run_all.py，可以另外手动跑。
    """
    tests = [t for t in ("regress_check.py", "smoke_test.py")
             if os.path.isfile(os.path.join(BASE, t))]
    if not tests:
        print("（没找到测试脚本，跳过）")
        return True
    all_ok = True
    for t in tests:
        try:
            r = subprocess.run([PY, t], cwd=BASE, capture_output=True,
                               timeout=900)
            out = (r.stdout or b"").decode(errors="replace")
            good = (r.returncode == 0)
        except Exception as exc:
            print("  %-20s 出错 %s" % (t, exc))
            all_ok = False
            continue
        print("  %-20s %s" % (t, "通过" if good else "失败"))
        if not good:
            all_ok = False
            tail = [x for x in out.splitlines() if x.strip()][-8:]
            for x in tail:
                print("      " + x)
    return all_ok


def cmd_test():
    ok = run_tests()
    print()
    print("测试结果：%s" % ("全部通过" if ok else "有失败"))
    return 0 if ok else 1


def cmd_whoami():
    cur = _read_lock()
    print("建议名字：%s" % guess_name())
    if cur and cur.get("name"):
        print("（现在 %s 持有钥匙）" % cur["name"])
    return 0


# ==================================================================

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("help", "-h", "--help"):
        print(__doc__)
        return 0
    cmd = args[0]
    rest = args[1:]

    if cmd == "take":
        return cmd_take(rest[0] if rest else None)
    if cmd == "release":
        name = None
        run_test = "--test" in rest
        force = "--force" in rest
        for a in rest:
            if not a.startswith("--"):
                name = a
        return cmd_release(name, run_test, force)
    if cmd == "steal":
        return cmd_steal()
    if cmd == "status":
        return cmd_status()
    if cmd in ("handover", "note"):
        msg = None
        for i, a in enumerate(rest):
            if a in ("-m", "--msg") and i + 1 < len(rest):
                msg = rest[i + 1]
        return cmd_handover(msg)
    if cmd == "read":
        return cmd_handover(None)
    if cmd == "test":
        return cmd_test()
    if cmd == "whoami":
        return cmd_whoami()

    print("不认识命令：%s" % cmd)
    print("可用：take / release / steal / status / handover / read /"
          " test / whoami")
    return 1


if __name__ == "__main__":
    sys.exit(main())
