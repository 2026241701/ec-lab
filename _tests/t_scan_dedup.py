# -*- coding: utf-8 -*-
"""回归测试：data_dir 同时含父目录与子目录时，scan_files 不得重复扫描同一文件。

复现 Bug：config.data_dir = [父目录, 父目录/GCD]，递归 glob 会把
GCD 子目录里的文件扫到两次（路径分隔符不一致导致朴素去重失效）。
"""
import os
import shutil
import tempfile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import eclab as E

SRC_GCD = os.path.join(ROOT, "_raw", "电化学数据结构", "GCD", "1A.txt")


def main():
    tmp = tempfile.mkdtemp(prefix="ec_scan_dedup_")
    try:
        parent = os.path.join(tmp, "data")
        sub = os.path.join(parent, "GCD")
        os.makedirs(sub, exist_ok=True)
        # 真实 GCD 样本放进子目录
        shutil.copy(SRC_GCD, os.path.join(sub, "1A.txt"))

        # data_dir 同时含父目录（递归会扫到 GCD/1A.txt）与子目录本身
        cfg = {"data_dir": [parent, sub]}
        found, skipped = E.scan_files(cfg)

        # 真实文件只有一个
        assert len(found["GCD"]) == 1, (
            f"GCD 被重复扫描：期望 1 个，实际 {len(found['GCD'])} 个 -> {found['GCD']}")

        # 归一化绝对路径集合不应有重复
        norm = {os.path.normpath(os.path.abspath(p)) for p in found["GCD"]}
        assert len(norm) == len(found["GCD"]), "扫描结果存在重复路径"

        # CV 同理不受影响
        assert isinstance(found["CV"], list)
        print("✅ scan_files 父+子目录重复扫描问题已修复："
              f"GCD 去重后 {len(found['GCD'])} 个（原会得 2 个）")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
