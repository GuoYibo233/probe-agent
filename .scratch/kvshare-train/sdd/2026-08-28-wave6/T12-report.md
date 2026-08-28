# T12 实现者报告——第二轮文档回写

工单:`.scratch/kvshare-train/issues/12-docs-writeback-round2.md`
spec:`.scratch/kvshare-train/spec.md` §16.7(清单)、§16.10(静默失败点 #28-#34)
分支:`ticket/2026-08-28-wave6/T12`(base `ed88ad7`,head `b43ede0`)
工作树:`/home/y-guo/reproduce/new1-wt/2026-08-28-wave6-T12`(收尾已删除,分支保留)

## 一、做了什么(对照工单逐条要求)

先按工单指示读了 `git log --oneline 7668166..HEAD`(合并后的 34 条提交)与五张工单
(07-11)的 Comments,确认合并后的代码状态(而不是工单原文)——收账过程中有几处
偏离工单原文(如工单 10 的 `loop` 探针按决定 32 改成了"三块各跑一组取大者",
不是工单原写的"只跑损失位最多那组"),写文档前都对着当前代码(`--help` 输出 +
`grep -n "add_argument"` 直接核对默认值)校准过。

1. **`stage-commands.md` §3**:
   - 参数表加四行:`--gen-eval`/`--gen-bs`/`--gen-eval-at`、
     `--align-tok-tol`/`--align-bf16-mean-tol`/`--align-bf16-max-tol`/`--align-baseline-factor`、
     `--align-rule`/`--align-rel-tol`(注明 ctool 只有这两个新增旗)、`--mem-probe-pick`
     (三种取值各一句判据);另加一行 `--overlong`(三个评测脚本,三种取值各写清楚
     判据与对应计数键)。
   - `train_causal_share.py` 真实命令块后加一段"学习率扫描"小节,给
     `sweep-lr plan --write` 与 `sweep-lr report --runs ... --out ...` 各一条命令。
   - §3 输出清单加三行:`sweep-lr` 的 `SWEEP_REPORT.json/.md`、各格 `--mem-probe`
     产生的 `mem_probe`/`mem_probe_summary` 事件、三个评测脚本报告新增的
     `overlong_mode` 与计数键。
   - §3.1 ③ 排卡规则改成引用 `mem_probe_summary.worst_gb`(具名字段而不是笼统的
     "最满块探针"),1.1 倍余量与②的碎片折扣仍是两条分开写的判据,没有合并成一个公式。
   - §3.2 补一句学习率扫描 run_id 是四段 `ks828<tag>_gptoss_cgen_lr<lr>`,
     产物 `pipeline/runs/sweep/`,不进矩阵、不进 `summarize_matrix`。
   - §7 第 517 行附近旧探针字段 `longest_event` 的排卡说明改成
     `mem_probe_summary` 的 `worst_gb`,并写清 `scope=full`/`scope=run` 的含义与
     `--smoke`/`--max-events` 下 `scope=run` 不能代表全量的限制(对应静默点 #36)。

2. **`invariants.md`**:更新"cgen/cparam 选 best"那一行,加一句现役训练器的
   `--gen-eval`(默认 200,0 关闭)/`--gen-eval-at`(默认 `last`)口径与决定 28;
   §3 新增两行——"显存探针挑块方式默认值"(`--mem-probe-pick` 默认 `cost`)与
   "对齐判据默认值"(`--align-rule` 默认 `abs`,四个粗筛门槛默认值等于第一轮常量);
   §4 新增一行"评测端超长事件默认处理"(`--overlong` 默认 `left`)。

3. **`extending.md`**:
   - §5 静默失败点表加 #28 到 #34 七条,按合并后的代码逐条核对触发条件(见下节"怎么验证的"),
     行号第一列改成 `#N` 格式(与代码注释里"静默失败点 #31"/"#32"/"#33"的引用方式一致,
     原表 1-27 号是裸数字,新加的七条统一带 `#`——这条不一致之处记在下面"自查发现与存疑")。
   - §3"换实现先例"段(第 123 行)把"四个评测脚本一字不改"改成"判分一字不改,
     输入构造第二轮加了 `--overlong` 一个开关(默认 `left` 时逐字段不变)",并补一句
     第二轮四个开关都是参数、默认值等于推荐值、不新增格。
   - §3.4 run_id 三段形状那条(第 167 行附近)补一句学习率扫描 run_id 是四段。

4. **`MAP.md`**:训练段表加 `sweep_lr.py` 一行(标"(扫描)");`cgen`/`cparam`
   两行补新开关一句;`share_data.py` 行补五个新函数
   (`full_token_ids`/`n_full_tokens`/`event_full_texts`/`select_keys`/`epoch_minibatches`);
   评测段三个脚本(`eval_tool.py`/`eval_causal_call.py`/`eval_causal_param.py`)
   行都补 `--overlong` 一句。

5. **`run.py`**:只改了工单点名的七条任务的 `notes` 字符串——
   `train-cgen`/`train-cparam` 补 `--gen-eval`、`--align-rule`、`--mem-probe-pick`
   三句;`train-ctool` 补 `--align-rule` 一句;`eval-tool-causal`/`eval-ccall`/
   `eval-cparam` 补 `--overlong` 一句;`eval-tool-mbert` 写"mbert 头只支持
   `--overlong left`"。`stage`/`py`/`script`/`gpu`/`args`/`desc` 等其余键一个未动
   (`git diff run.py` 核对过,只有 `notes=[...]` 列表变了)。

6. **`gates.md`**:G13(对齐检查)那一行补一句——smoke 门只读 `ALIGN_CHECK.json`
   的 `PASS`,`rule` 字段(第二轮新写的 `abs`/`rel`/`both`)进 JSON 但不影响这道门。

7. **收尾三处小改**:`extending.md` 第 123 行(见第 3 条已合并说明);`stage-commands.md`
   §7(见第 1 条已合并说明);`pipeline/eval/ACCEPT_EVAL.md` 加一节"§0 第二轮更正",
   说明本文档记的是 2026-07-31 代码状态,第二轮起 `REPLAY_REPORT.json` 无论 `--overlong`
   传哪个值都会多写 `overlong_mode` 与四个计数键(`n_oow`/`n_skipped_bounds`/
   `n_dropped_events`/`n_dropped_bounds`),不再要求"逐字节相同",新判据是
   "除这几个新键外其余现有键不变"。

不改任何 `.py` 逻辑,不改任何测试文件(`git diff --stat` 只有七份文档/`run.py`
的 notes,没有别的文件)。

## 二、怎么验证的

**每个参数默认值都直接对着 `--help` 或源码 `add_argument` 核对过**,不是照抄
工单/spec 原文。核对用的命令与关键输出(用主仓 `cprobe-env` 的解释器跑工作树里的脚本):

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python3 pipeline/eval/eval_causal_call.py --help
  → --overlong {left,skip,drop-event}  默认 left(--help 文案里写了"逐字节不变")
/home/y-guo/reproduce/new1/cprobe-env/bin/python3 pipeline/train/train_causal_share.py --help
  → --gen-eval / --gen-bs / --gen-eval-at{all,last} / --mem-probe-pick{tokens,cost,loop}
    / --align-rule{abs,rel,both} / --align-rel-tol / --align-tok-tol /
    --align-bf16-mean-tol / --align-bf16-max-tol / --align-baseline-factor 全部在列
/home/y-guo/reproduce/new1/cprobe-env/bin/python3 pipeline/train/train_causal_tool.py --help
  → --align-rule{abs,rel,both} / --align-rel-tol 在列,没有那四个粗筛门槛旗
grep -n "add_argument(.--(overlong|gen-eval|...)" pipeline/train/*.py pipeline/eval/*.py
  → train_causal_share.py:880  --gen-eval    default=200
    train_causal_share.py:882  --gen-bs      default=8
    train_causal_share.py:884  --gen-eval-at default="last"
    train_causal_share.py:889  --mem-probe-pick default="cost"
    train_causal_share.py:904/908/910/912/914 四个粗筛门槛 default=2e-5/3e-4/2e-2/1e-1/3.0
    train_causal_share.py:917/920  --align-rule default="abs" / --align-rel-tol default=1e-5
    train_causal_tool.py:342/345   --align-rule default="abs" / --align-rel-tol default=1e-5
    eval_causal_call.py:484 / eval_causal_param.py:323 / eval_tool.py:324
      --overlong default="left"
```

以上默认值与我写进文档的完全一致。

`pipeline/eval/eval_tool.py --help` 另确认了 `--overlong` 只对 `--head causal`
生效、mbert 头传非 `left` 直接 `SystemExit`,与 `run.py` 里 `eval-tool-mbert`
新加的那句 notes 一致。

`share_data.py` 的五个新函数用 `grep -n "^def full_token_ids\|^def n_full_tokens\|..."`
核对了函数名与所在行,函数体/docstring 直接读过(`share_data.py:71-151`、`:453-464`),
`epoch_minibatches` 的 `random.Random(seed + ep).shuffle` 与训练循环旧写法逐字对照过。

`extending.md` §5 新增的 #28-#34 每条都在合并后的代码里找到了对应位置:

```
grep -n "静默失败点 #\|静默点 #" pipeline/train/*.py pipeline/eval/*.py
  train_causal_share.py:496  spec 16.5,静默失败点 #31(探针随机数状态)
  train_causal_share.py:527  opt.state.clear()  # #32:lr=0 的 step 仍写状态,清掉
  eval_tool.py:450           静默失败点 #33(overlong_mode 缓存冒充)
```
代码本身已经用注释标了 #31/#32/#33,证实我核对的触发条件与实现一致。
#34 直接读了 `train_causal_tool.py:93-96`(先按 `label in label2id` 过滤再取
最后一行)与 `share_data.py:87-101` 的 `event_full_texts`(不过滤,直接取
`sent_idx` 最大那行),两处规则确认不同。#28/#29/#30 分别核对了
`select_keys` 的 `n_excluded_by_ctool` 计数、`_attn_ctx` 的调用点位置
(`grep -n "_attn_ctx("` 只命中 `_forward_packed` 函数体内一处)、
`pack_event` 的 `row[:6]` 拆包写法。

**验收命令**(工单点名的三条 + selfcheck):

```
$ python3 run.py selfcheck
selfcheck: 77 任务 / 4 配方 / 3 预设, 全部就位
```
(工作树本身缺各 venv 的软链接——`cprobe-env`/`mbert-env`/`envs/appworld` 等都是
gitignored、`git worktree add` 不会带过来——先临时软链主仓对应目录跑通
selfcheck,验证完就把这些软链接删掉了,`git status --short` 现在只剩七份改动的文档。)

```
$ grep -c "overlong" .claude/skills/probe-pipeline/references/stage-commands.md MAP.md run.py
stage-commands.md:2  MAP.md:4  run.py:6         # 三处均命中,符合验收①
$ grep -n "#34" .claude/skills/probe-pipeline/references/extending.md
300:| #34 | ...                                  # 命中,符合验收②
$ grep -c "worst_gb" .claude/skills/probe-pipeline/references/stage-commands.md
3
$ grep -c "runs/sweep" .claude/skills/probe-pipeline/references/stage-commands.md
5                                                 # 两个都命中,符合验收③
```

没有改 `.py` 逻辑与测试,所以没有跑单元测试;`run.py` 的改动只是字符串,用
`ast.literal_eval` 把七条任务的 `notes` 列表抠出来打印过一遍,确认拼接后的
中文句子没有丢空格(过程中真的抓到过几处 Python 相邻字符串字面量拼接漏空格的
问题,已修——见下节)。

## 三、commit 清单

- `b43ede0` T12: 第二轮文档回写——stage-commands/invariants/extending/gates/MAP/run.py/ACCEPT_EVAL
  (79 行插入、16 行删除,七个文件:`stage-commands.md`、`invariants.md`、
  `extending.md`、`gates.md`、`MAP.md`、`run.py`、`pipeline/eval/ACCEPT_EVAL.md`)
- `4f10aec` T12: 自查修复——extending §5 #35/#36 空指改指 spec 16.10
  (自查阶段发现的问题,见下节;`stage-commands.md`+`invariants.md` 两处各改一句)

## 四、自查发现与存疑

- **发现并修复**:`run.py` 里我按该文件原有风格把长句拆成多个相邻字符串字面量
  跨物理行写(Python 会自动拼接、不插入空格),第一版有五处漏写行尾空格,拼接后
  会变成"判reldiff_hidden"、"--gen-eval-at{all,last}"、".meta.json的 excluded_idx"
  这种词粘连。用 `ast` 把 `TASKS` 字典里七条任务的 `notes` 抠出来实际求值打印后
  发现的,已经全部修掉并重新用同样的方法复核过一遍,现在七条 notes 逐句读起来
  都通顺。`MAP.md` 里 cgen/cparam 两行结尾也有一次"少了收尾前的空格"(`cost）|`
  少了空格),同样已修。
- **存疑,主会话裁决**:extending.md §5 静默失败点表原来 1-27 号在"#"列都是裸
  数字(`| 26 |`),我新加的 28-34 号为了让 `grep "#34"` 这条验收命中、也为了跟
  代码注释里"静默失败点 #31"这种引用方式一致,改成了带 `#` 前缀(`| #34 |`)。
  这让表格前 27 行与后 7 行"#"列的格式不统一。工单验收明确要求 `grep -n "#34"`
  命中,而表格本来的裸数字写法命中不了这条(我试过,`grep "#34"` 在裸数字版本下
  是空的),两者二选一之下我选了改格式让验收通过,但没有回头把 1-27 号也统一
  改成带 `#`(那超出了工单"加 #28 到 #34"的范围,属于自己发挥)。这处前后不一致
  是否要后续统一,留给主会话判断。
- **存疑,已就手修正**:spec 16.10 原文实际列了 #28 到 #36 共九条(顺序是 28,29,
  30,31,32,33,35,36,34),但工单第 5 步明确写的是"加 #28 到 #34",验收 grep
  也只查 `"#34"`。我照工单字面意思只加了 28-34 七条,#35(ctool 的 `--overlong`
  会改变 `n_events_scored`、矩阵混档口径)和 #36(`mem_probe_summary` 的
  `scope=run` 不能代表全量)**没有**写进 extending.md §5 的表。第一版里我在
  `invariants.md`/`stage-commands.md` 三处写了"见 extending §5 #35"/"#36"
  这样的交叉引用,但 extending.md 本身没有这两条——自查时发现是空指,已在
  `4f10aec` 里改成指 `spec 16.10 #35`/`#36`(那两条内容确实在 spec 里,指
  过去是准的)。是否要在后续工单里把 #35/#36 也正式补进 extending.md §5 的表
  (本单范围之外),留给主会话判断。
