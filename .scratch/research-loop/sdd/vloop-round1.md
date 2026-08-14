# §V 验证循环第一轮（2026-08-14）

执行形态：一个 workflow，12 个 agent——V1 五个 sonnet 天真执行者（router/idea/
deploy/run/oversight 各一，上下文只有本层 SKILL.md + 预埋沙盒，禁读源码/表/spec）、
V3 一个 sonnet 越权探针（14 项非法动作清单）、V2 五跳 sonnet 接力
（deploy→run→deploy→run→idea，prompt 零任务细节、全靠账本落盘接力）、
一个 opus 对抗复核（先试图驳回、复跑证据、V2 沙盒纯盘上审计）。
沙盒构建脚本：`$CLAUDE_JOB_DIR/tmp/seed_v_sandboxes.py`（round1）。

原始 findings 50 条 → opus 复核后 **45 confirmed / 6 refuted**（驳回的六条全是
执行者漏读了自己可读范围内的文档，各附驳回依据）。完整裁决书（45 条全文 +
驳回依据 + V2 盘上审计）：`sdd/vloop-round1-verdict.json`。

V2 盘上审计：trace_check 干净，但 **chain_completed=False**——四号环节
（部署层自决）只留在 blocked 行的自由文本里（grant_ref=D002、decision_ref=null、
decisions 账零新行），恰好踩中确认清单里最重的 R6 洞；且种子把任务钉死
--mode fail 导致回退重试同样失败，happy path（报告→核查→收官→story）本轮
没走到，round 2 种子要修。

## 确认 findings 的聚类（详情见 verdict json）

- **R6 洞（blocker ×3：v1-deploy-2 / v2-hop3-1 / v2-audit gap1）**：非 r5-choice
  的 blocked 行带 --grant 答复合法通过但不产 decisions 行，全 plugin 无任何
  文档化命令序列能给 kind=failure/other 的自决留 R6 痕。
- **跳层升级无机验（blocker v3-1）**：`blocked open --layer run --to-layer user`
  直接落账进用户队列，failures.md:51 的"不许跳层"无机器锚点。
- **run 层记账步骤无命令（blocker ×3：v1-run-2 / v2-hop2-1 / v2-hop4-2）**：
  jobs 台账两个必加键无字段名无写入者，执行者手编键名（沙盒里已留下
  sampler_verdict 等自造键）；采样器判定枚举对"发射前被拒"无值，两个执行者
  各猜一头。
- **error_classify 缺表即裸崩（blocker ×2：v1-run-1 / v2-hop2-3）**：R8 强制
  第一步在裸工程上直接 traceback。
- **evidence_lint 与 run_id 形状（blocker v1-oversight-2）**：工程没有成文的
  run_id 命名规则（v2-hop1-1），随手起的 run-101 形状不在豁免正则内，核查报告
  提 run 必红。裁决：linter 不动，补命名规则成文（见 #154）。
- **oversight 缺 regression 职责文档（blocker v1-oversight-5）**、**idea 层
  无答复待决条的文档（blocker v1-idea-1）**、**deploy 层无故障处理文档
  （blocker v1-deploy-1 / v2-hop3-2）**：三个层各缺一块承重文档。
- **record.py 丢 commit（v2-audit-1）**：RUNMETA 里有真 commit，落 runs 行
  写死 null，发射前 commit 纪律在数字账上断线。
- 其余 25 条 friction/note：文档措辞、表 _note 占位符、缺工作示例、缺文件名
  约定等，逐条见 verdict json。

## 处置

七条设计裁决落 audit-merge.md 自决点 #151–157；全部修复开两张补丁工单
`issues/17-vloop-code.md`（代码+表+schema+测试）与 `issues/18-vloop-docs.md`
（文档，Blocked by 17），走 ticket-run。修完起 round 2（新种子：合规 run_id、
回退预案改成真能成功的形态、接力链延长到 happy path 收官），循环到连续一轮
零 confirmed。
