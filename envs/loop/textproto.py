"""闭环文本协议层:在线喂探针的前缀必须与训练样本逐字节同源。

唯一正确来源是 envs/collect/build_dataset.py —— 本文件只 re-export 它的
assemble/clip/SENT_RE/常量,不复制任何拼接逻辑;唯一新增物是流式专用的
增量句界检测器 BoundaryTracker。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
from build_dataset import (  # noqa: E402,F401
    HIST_ROUNDS, MIN_THINK, RESULT_CAP, SENT_RE, assemble, boundaries, clip,
)


class BoundaryTracker:
    """增量句界检测:每次 feed() 喂当前全量思考文本,返回上次之后新出现的
    切点(字符偏移,前缀=text[:p])。

    切点语义与 build_dataset.boundaries 一致(SENT_RE 匹配末端 + 前缀去空白
    >= MIN_THINK//2),两处刻意不同:不做 MAX_BOUNDS 抽样(线上每个句边界都探,
    训练的 w=1/m 事件等权就是按这个部署分布设计的);"全文末尾"这个切点由
    生成结束时 finalize() 补,流中不发。流式护栏:只认后面已有实字符跟着的
    切点 —— 空白区可能还在生长,贴着流前沿的匹配留到下个 chunk 再确认。
    """

    def __init__(self):
        self.text = ""
        self.emitted = set()

    def feed(self, text):
        self.text = text
        out = []
        for m in SENT_RE.finditer(text):
            p = m.end()
            if p >= len(text) or p in self.emitted:
                continue
            if len(text[:p].strip()) < MIN_THINK // 2:
                continue
            self.emitted.add(p)
            out.append(p)
        return out

    def finalize(self):
        """生成自然结束:补全文末尾切点(build_dataset 的 {len(text)} 项)。"""
        p = len(self.text)
        if p and p not in self.emitted \
                and len(self.text.strip()) >= MIN_THINK // 2:
            self.emitted.add(p)
            return [p]
        return []
