#!/usr/bin/env python3
"""Machine checks for plans/research-loop-parts/.

Run from the repo root: python3 plans/research-loop-parts/check_docs.py
Uses only the standard library, only reads files, changes nothing. Exit code 1 if
anything fails, 0 if everything passes. Warnings do not affect the exit code.

Six checks:
  1. Whether sync-inbox.md's issue numbers have duplicates, and what the current max is
  2. Whether HANDOFF.md has a sentence that hardcodes the next issue number
  3. Whether any .md file across the tree has a leftover tool-call marker
  4. Whether the diff of each of the three frozen parts against its own frozen commit
     goes past the "## To sync elsewhere" heading
  5. Whether any non-frozen part still has wording from a cut scope (whitelist in
     check_docs_whitelist.txt)
  6. Whether all 22 parts have their three fixed headings
"""

import os
import re
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
WHITELIST_FILE = os.path.join(DIR, "check_docs_whitelist.txt")

# The three frozen parts and each one's frozen commit
FROZEN = [
    ("03-ledgers.md", "884ac0b"),
    ("04-handoffs-and-sessions.md", "9b78d7c"),
    ("05-rl-cli.md", "77213e5"),
]
FROZEN_NAMES = {name for name, _ in FROZEN}

SYNC_HEADING = "## 要同步到别处的"

# The three that are not parts
NON_PART = {"HANDOFF.md", "README.md", "sync-inbox.md"}

# The three headings each finalized part must have
PART_HEADINGS = [
    "和别的 part 的接口",
    "源文档没写清的",
    "第二轮模拟里归到这一份的摩擦",
]

# Wording from a cut scope
RETIRED_WORDS = [
    "公共规矩八条",
    "公共母版八条",
    "推送表",
    "触发桌面通知",
    "notify.reminder_days",
    "read:notes",
]

# Leftover tool-call marker (start of line, leading whitespace allowed)
RESIDUE_RE = re.compile(r"^\s*(</content>|</invoke>|<content>|<invoke)")


def repo_root():
    """Repo root: ask git first; if that fails, infer from the directory structure."""
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
            head = "%d errors" % len(self.errors)
        elif self.warnings:
            head = "%d warnings" % len(self.warnings)
        else:
            head = "pass"
        print("[%s] %s" % (head, self.title))
        for m in self.infos:
            print("    · %s" % m)
        for m in self.errors:
            print("    ERR  %s" % m)
        for m in self.warnings:
            print("    WARN %s" % m)
        print("")


# ---------------------------------------------------------------- check 1

def check_numbers():
    """Issue numbers in sync-inbox.md: report an error on duplicates, print the current max.

    A definition site has two forms:
      - Column-0 "- Issue N:" or "- Issue N (...):"
      - An indented "  N. " list, where the list does not start from 1 (a list starting
        from 1 is a "things to change" list, which is a within-section item number, not
        a global issue number)
    """
    r = Result("Check 1: sync-inbox.md issue numbers")
    path = os.path.join(DIR, "sync-inbox.md")
    if not os.path.exists(path):
        r.error("sync-inbox.md not found")
        return r
    lines = read_lines(path)

    defs = []  # (number, line number, form)

    # Column-0 "- Issue N:" / "- Issue N (" -- follow-up lines like "- Issue 1 also carries" or "- Issue 30 already landed" do not count as a definition site
    top_re = re.compile(r"^- 问题 (\d+)(?=[：（])")
    for i, line in enumerate(lines, 1):
        m = top_re.match(line)
        if m:
            defs.append((int(m.group(1)), i, "issue N"))

    # Indented numbered lists, grouped by "a contiguous run of indented numbered lines"
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
            continue  # a list starting from 1 is a within-section item number, skip it
        for num, i in block:
            defs.append((num, i, "  N. "))

    if not defs:
        r.error("found zero issue-number definition sites; the regex no longer matches the file")
        return r

    seen = {}
    for num, i, kind in sorted(defs, key=lambda d: d[1]):
        seen.setdefault(num, []).append((i, kind))
    for num in sorted(seen):
        places = seen[num]
        if len(places) > 1:
            r.error("issue %d is duplicated, defined at line %s" % (
                num, ",".join(str(p[0]) for p in places)))

    nums = sorted(seen)
    r.info("found %d issue-number definition sites, current max number is %d" % (len(defs), nums[-1]))
    gaps = [n for n in range(1, nums[-1] + 1) if n not in seen]
    if gaps:
        r.info("numbers between 1 and %d with no definition site: %s" % (
            nums[-1], ",".join(str(n) for n in gaps)))
    else:
        r.info("1 through %d are contiguous, no missing numbers" % nums[-1])
    return r


# ---------------------------------------------------------------- check 2

def check_handoff_hardcoded_number():
    """HANDOFF.md must not hardcode the next issue number."""
    r = Result("Check 2: whether HANDOFF.md hardcodes the next issue number")
    path = os.path.join(DIR, "HANDOFF.md")
    if not os.path.exists(path):
        r.error("HANDOFF.md not found")
        return r
    pats = [
        ("下一个新问题编号", re.compile(r"下一个新问题编号")),
        ("下一个是 <数字>", re.compile(r"下一个是\s*[0-9０-９]+")),
    ]
    for i, line in enumerate(read_lines(path), 1):
        for name, pat in pats:
            if pat.search(line):
                r.error("line %d has '%s': %s" % (i, name, line.strip()[:120]))
    if not r.errors:
        r.info("no hardcoded number sentence; the real source is the current max number in sync-inbox.md")
    return r


# ---------------------------------------------------------------- check 3

def check_tool_residue():
    """Scan every .md file in the tree for leftover tool-call markers."""
    r = Result("Check 3: leftover tool-call markers")
    count = 0
    for fn in md_files():
        for i, line in enumerate(read_lines(os.path.join(DIR, fn)), 1):
            if RESIDUE_RE.match(line):
                r.error("%s:%d %s" % (fn, i, line.strip()))
                count += 1
    if not count:
        r.info("zero leftover markers across %d .md files" % len(md_files()))
    return r


# ---------------------------------------------------------------- check 4

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
    """The three frozen parts: only lines after the "## To sync elsewhere" heading may change."""
    r = Result("Check 4: whether changes to the three frozen files cross '%s'" % SYNC_HEADING)
    for fn, commit in FROZEN:
        path = os.path.join(DIR, fn)
        relpath = os.path.relpath(path, ROOT)
        if not os.path.exists(path):
            r.error("%s: file is gone" % fn)
            continue

        new_lines = read_lines(path)
        new_head = heading_line(new_lines)
        if new_head is None:
            r.error("%s: heading '%s' not found in this working-tree version" % (fn, SYNC_HEADING))
            continue

        old_lines, err = git_show(commit, relpath)
        if old_lines is None:
            r.error("%s: git show %s failed (%s)" % (fn, commit, err))
            continue
        old_head = heading_line(old_lines)
        if old_head is None:
            r.error("%s: heading '%s' not found in frozen version %s" % (fn, commit, SYNC_HEADING))
            continue

        diff, err = git_diff(commit, relpath)
        if diff is None:
            r.error("%s: git diff %s failed (%s)" % (fn, commit, err))
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
            r.error("%s: line %s before the heading was touched in the frozen version (%s)" % (
                fn, commit, ",".join(str(x) for x in bad_old[:20])))
        if bad_new:
            r.error("%s: line %s before the heading has changes in the working tree" % (
                fn, ",".join(str(x) for x in bad_new[:20])))
        if not bad_old and not bad_new:
            r.info("%s vs %s: all %d changes are after the heading (line %d)" % (
                fn, commit, hunks, new_head))
    return r


# ---------------------------------------------------------------- check 5

def load_whitelist():
    """Whitelist: one entry per line, format filename:matched fragment. Lines starting with # are comments."""
    wl = {}
    if not os.path.exists(WHITELIST_FILE):
        return wl, "%s not found" % os.path.basename(WHITELIST_FILE)
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
    """Leftover wording from a cut scope in non-frozen parts; a whitelist hit does not count. Warning, not an error."""
    r = Result("Check 5: leftover wording from settings already cut (non-frozen files)")
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
            r.warn("%s:%d has '%s': %s" % (
                fn, i, ",".join(words), line.strip()[:110]))
    total = sum(len(v) for v in wl.values())
    r.info("allowlist has %d entries, %d matched" % (total, len(used)))
    stale = [(fn, f) for fn, fs in wl.items() for f in fs if (fn, f) not in used]
    for fn, f in stale:
        r.info("stale allowlist entry (this line is no longer in the file): %s:%s" % (fn, f[:60]))
    if not hits:
        r.info("no leftovers outside the allowlist")
    return r


# ---------------------------------------------------------------- check 6

def check_part_headings():
    """Each of the 22 parts must have its three fixed headings; report a warning for any missing."""
    r = Result("Check 6: the three fixed headings across the 22 parts")
    parts = part_files()
    if len(parts) != 22:
        r.warn("part count is %d, not 22: %s" % (len(parts), ",".join(parts)))
    for fn in parts:
        text = "\n".join(read_lines(os.path.join(DIR, fn)))
        missing = [
            h for h in PART_HEADINGS
            if not re.search(r"^#{1,6} .*" + re.escape(h), text, re.M)
        ]
        if missing:
            r.warn("%s missing headings: %s" % (fn, ",".join(missing)))
    if not r.warnings:
        r.info("all three headings present across %d parts" % len(parts))
    return r


# ----------------------------------------------------------------- main

def main():
    print("check dir: %s" % DIR)
    print("repo root: %s" % ROOT)
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
    print("total: %d errors, %d warnings" % (errs, warns))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
