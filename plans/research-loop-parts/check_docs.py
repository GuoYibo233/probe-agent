#!/usr/bin/env python3
"""plans/research-loop-parts/ 的机器检查。

在仓库根跑：python3 plans/research-loop-parts/check_docs.py
只用标准库，只读文件，一处都不改。有错项时退出码 1，全过退出码 0。
警告不影响退出码。

六项检查：
  1. sync-inbox.md 的问题编号有没有重号，当前最大编号是几
  2. HANDOFF.md 里有没有把下一个问题编号写死的句子
  3. 全目录 .md 里有没有工具调用的标记残留
  4. 冻结三份对各自冻结 commit 的 diff 有没有越过「## 要同步到别处的」标题
  5. 非冻结份里已裁口径的字样残留（白名单见 check_docs_whitelist.txt）
  6. 22 份 part 的三个固定标题齐不齐
"""

import os
import re
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
WHITELIST_FILE = os.path.join(DIR, "check_docs_whitelist.txt")

# 三份冻结的 part 和各自的冻结 commit
FROZEN = [
    ("03-ledgers.md", "884ac0b"),
    ("04-handoffs-and-sessions.md", "9b78d7c"),
    ("05-rl-cli.md", "77213e5"),
]
FROZEN_NAMES = {name for name, _ in FROZEN}

SYNC_HEADING = "## 要同步到别处的"

# 不是 part 的三份
NON_PART = {"HANDOFF.md", "README.md", "sync-inbox.md"}

# 每份 part 定稿要有的三个标题
PART_HEADINGS = [
    "和别的 part 的接口",
    "源文档没写清的",
    "第二轮模拟里归到这一份的摩擦",
]

# 已裁口径的字样
RETIRED_WORDS = [
    "公共规矩八条",
    "公共母版八条",
    "推送表",
    "触发桌面通知",
    "notify.reminder_days",
    "read:notes",
]

# 工具调用残留标记（行首，允许前面有空白）
RESIDUE_RE = re.compile(r"^\s*(</content>|</invoke>|<content>|<invoke)")


def repo_root():
    """仓库根：先问 git，问不出来就按目录结构推。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=DIR, capture_output=True, text=True, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except OSError:
        pass
    return os.path.dirname(os.path.dirname(DIR))


ROOT = repo_root()


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().split("\n")


def md_files():
    return sorted(f for f in os.listdir(DIR) if f.endswith(".md"))


def part_files():
    return sorted(
        f for f in md_files()
        if f not in NON_PART and re.match(r"^\d\d-", f)
    )


class Result:
    def __init__(self, title):
        self.title = title
        self.errors = []
        self.warnings = []
        self.infos = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def report(self):
        if self.errors:
            head = "错 %d 项" % len(self.errors)
        elif self.warnings:
            head = "警告 %d 项" % len(self.warnings)
        else:
            head = "过"
        print("[%s] %s" % (head, self.title))
        for m in self.infos:
            print("    · %s" % m)
        for m in self.errors:
            print("    错  %s" % m)
        for m in self.warnings:
            print("    警  %s" % m)
        print("")


# ---------------------------------------------------------------- 检查 1

def check_numbers():
    """sync-inbox.md 的问题编号：重号报错，打印当前最大编号。

    定义处有两种写法：
      - 顶格的「- 问题 N：」或「- 问题 N（…）：」
      - 缩进的「  N. 」列表，且这个列表不是从 1 起（从 1 起的是「要改的地方」清单，
        那是本段内部的条目号，不是全局问题号）
    """
    r = Result("检查 1：sync-inbox.md 问题编号")
    path = os.path.join(DIR, "sync-inbox.md")
    if not os.path.exists(path):
        r.error("找不到 sync-inbox.md")
        return r
    lines = read_lines(path)

    defs = []  # (编号, 行号, 写法)

    # 顶格的「- 问题 N：」/「- 问题 N（」；「- 问题 1 附带」「- 问题 30 已落」这类后续行不算定义处
    top_re = re.compile(r"^- 问题 (\d+)(?=[：（])")
    for i, line in enumerate(lines, 1):
        m = top_re.match(line)
        if m:
            defs.append((int(m.group(1)), i, "问题 N"))

    # 缩进的编号列表，按「一段连续的缩进编号行」分组
    item_re = re.compile(r"^  (\d+)\. ")
    blocks = []
    cur = []
    for i, line in enumerate(lines, 1):
        m = item_re.match(line)
        if m:
            cur.append((int(m.group(1)), i))
        elif cur and not line.startswith("  ") and line.strip():
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    for block in blocks:
        if block[0][0] == 1:
            continue  # 从 1 起的是段内条目号，跳过
        for num, i in block:
            defs.append((num, i, "  N. "))

    if not defs:
        r.error("一个问题编号定义处都没扫到，正则和文件对不上了")
        return r

    seen = {}
    for num, i, kind in sorted(defs, key=lambda d: d[1]):
        seen.setdefault(num, []).append((i, kind))
    for num in sorted(seen):
        places = seen[num]
        if len(places) > 1:
            r.error("问题 %d 重号，定义处在第 %s 行" % (
                num, "、".join(str(p[0]) for p in places)))

    nums = sorted(seen)
    r.info("扫到 %d 个问题编号定义处，当前最大编号是 %d" % (len(defs), nums[-1]))
    gaps = [n for n in range(1, nums[-1] + 1) if n not in seen]
    if gaps:
        r.info("1 到 %d 之间没有定义处的编号：%s" % (
            nums[-1], "、".join(str(n) for n in gaps)))
    else:
        r.info("1 到 %d 连续，没有缺号" % nums[-1])
    return r


# ---------------------------------------------------------------- 检查 2

def check_handoff_hardcoded_number():
    """HANDOFF.md 里不许把下一个问题编号写死。"""
    r = Result("检查 2：HANDOFF.md 有没有把下一个问题编号写死")
    path = os.path.join(DIR, "HANDOFF.md")
    if not os.path.exists(path):
        r.error("找不到 HANDOFF.md")
        return r
    pats = [
        ("下一个新问题编号", re.compile(r"下一个新问题编号")),
        ("下一个是 <数字>", re.compile(r"下一个是\s*[0-9０-９]+")),
    ]
    for i, line in enumerate(read_lines(path), 1):
        for name, pat in pats:
            if pat.search(line):
                r.error("第 %d 行有「%s」：%s" % (i, name, line.strip()[:120]))
    if not r.errors:
        r.info("没有写死的编号句；真源是 sync-inbox.md 里现有的最大编号")
    return r


# ---------------------------------------------------------------- 检查 3

def check_tool_residue():
    """全目录 .md 扫工具调用的标记残留。"""
    r = Result("检查 3：工具调用标记残留")
    count = 0
    for fn in md_files():
        for i, line in enumerate(read_lines(os.path.join(DIR, fn)), 1):
            if RESIDUE_RE.match(line):
                r.error("%s:%d %s" % (fn, i, line.strip()))
                count += 1
    if not count:
        r.info("%d 份 .md 里一个残留标记都没有" % len(md_files()))
    return r


# ---------------------------------------------------------------- 检查 4

def git_show(commit, relpath):
    out = subprocess.run(
        ["git", "show", "%s:%s" % (commit, relpath)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        return None, out.stderr.strip()
    return out.stdout.split("\n"), None


def git_diff(commit, relpath):
    out = subprocess.run(
        ["git", "diff", "--no-color", "-U0", commit, "--", relpath],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        return None, out.stderr.strip()
    return out.stdout.split("\n"), None


def heading_line(lines):
    for i, line in enumerate(lines, 1):
        if line.startswith(SYNC_HEADING):
            return i
    return None


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def check_frozen():
    """冻结三份：只许「## 要同步到别处的」标题之后的行有改动。"""
    r = Result("检查 4：冻结三份的改动有没有越过「%s」" % SYNC_HEADING)
    for fn, commit in FROZEN:
        path = os.path.join(DIR, fn)
        relpath = os.path.relpath(path, ROOT)
        if not os.path.exists(path):
            r.error("%s：文件不在了" % fn)
            continue

        new_lines = read_lines(path)
        new_head = heading_line(new_lines)
        if new_head is None:
            r.error("%s：工作树这一版找不到「%s」标题" % (fn, SYNC_HEADING))
            continue

        old_lines, err = git_show(commit, relpath)
        if old_lines is None:
            r.error("%s：git show %s 失败（%s）" % (fn, commit, err))
            continue
        old_head = heading_line(old_lines)
        if old_head is None:
            r.error("%s：冻结版 %s 里找不到「%s」标题" % (fn, commit, SYNC_HEADING))
            continue

        diff, err = git_diff(commit, relpath)
        if diff is None:
            r.error("%s：git diff %s 失败（%s）" % (fn, commit, err))
            continue

        hunks = 0
        bad_old = []
        bad_new = []
        for line in diff:
            m = HUNK_RE.match(line)
            if not m:
                continue
            hunks += 1
            o_start = int(m.group(1))
            o_count = 1 if m.group(2) is None else int(m.group(2))
            n_start = int(m.group(3))
            n_count = 1 if m.group(4) is None else int(m.group(4))
            if o_count:
                for ln in range(o_start, o_start + o_count):
                    if ln < old_head:
                        bad_old.append(ln)
            if n_count:
                for ln in range(n_start, n_start + n_count):
                    if ln < new_head:
                        bad_new.append(ln)

        if bad_old:
            r.error("%s：冻结版（%s）标题之前第 %s 行被动过" % (
                fn, commit, "、".join(str(x) for x in bad_old[:20])))
        if bad_new:
            r.error("%s：工作树标题之前第 %s 行有改动" % (
                fn, "、".join(str(x) for x in bad_new[:20])))
        if not bad_old and not bad_new:
            r.info("%s 对 %s：%d 处改动全在标题（第 %d 行）之后" % (
                fn, commit, hunks, new_head))
    return r


# ---------------------------------------------------------------- 检查 5

def load_whitelist():
    """白名单：一行一条，格式 文件名:匹配片段。# 开头是注释。"""
    wl = {}
    if not os.path.exists(WHITELIST_FILE):
        return wl, "找不到 %s" % os.path.basename(WHITELIST_FILE)
    for raw in read_lines(WHITELIST_FILE):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        fn, frag = line.split(":", 1)
        fn = fn.strip()
        if not frag.strip():
            continue
        wl.setdefault(fn, []).append(frag)
    return wl, None


def check_retired_words():
    """非冻结份里已裁口径的字样残留；命中白名单的不算。警告，不算错。"""
    r = Result("检查 5：已裁口径的字样残留（非冻结份）")
    wl, err = load_whitelist()
    if err:
        r.error(err)
        return r
    used = set()
    hits = 0
    for fn in md_files():
        if fn in FROZEN_NAMES:
            continue
        frags = wl.get(fn, [])
        for i, line in enumerate(read_lines(os.path.join(DIR, fn)), 1):
            words = [w for w in RETIRED_WORDS if w in line]
            if not words:
                continue
            matched = [f for f in frags if f in line]
            if matched:
                for f in matched:
                    used.add((fn, f))
                continue
            hits += 1
            r.warn("%s:%d 有「%s」：%s" % (
                fn, i, "、".join(words), line.strip()[:110]))
    total = sum(len(v) for v in wl.values())
    r.info("白名单 %d 条，命中 %d 条" % (total, len(used)))
    stale = [(fn, f) for fn, fs in wl.items() for f in fs if (fn, f) not in used]
    for fn, f in stale:
        r.info("白名单过期条目（文件里已经没有这一行了）：%s:%s" % (fn, f[:60]))
    if not hits:
        r.info("白名单之外没有残留")
    return r


# ---------------------------------------------------------------- 检查 6

def check_part_headings():
    """22 份 part 各自要有三个固定标题；缺的报警告。"""
    r = Result("检查 6：22 份 part 的三个固定标题")
    parts = part_files()
    if len(parts) != 22:
        r.warn("part 份数是 %d，不是 22：%s" % (len(parts), "、".join(parts)))
    for fn in parts:
        text = "\n".join(read_lines(os.path.join(DIR, fn)))
        missing = [
            h for h in PART_HEADINGS
            if not re.search(r"^#{1,6} .*" + re.escape(h), text, re.M)
        ]
        if missing:
            r.warn("%s 缺标题：%s" % (fn, "、".join(missing)))
    if not r.warnings:
        r.info("%d 份 part 三个标题都齐" % len(parts))
    return r


# ----------------------------------------------------------------- main

def main():
    print("检查目录：%s" % DIR)
    print("仓库根：%s" % ROOT)
    print("")
    results = [
        check_numbers(),
        check_handoff_hardcoded_number(),
        check_tool_residue(),
        check_frozen(),
        check_retired_words(),
        check_part_headings(),
    ]
    for r in results:
        r.report()
    errs = sum(len(r.errors) for r in results)
    warns = sum(len(r.warnings) for r in results)
    print("合计：错 %d 项，警告 %d 项" % (errs, warns))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
