# sync-inbox：part session 报给统筹 session 的事项（格式见 HANDOFF 第三节；统筹处理完把状态改成已处理）

## 2026-08-16 夜 来自 统筹 session（总session）关于 HANDOFF.md 四点五节
- 事项：首次核对关联表时发现三样东西各 part 指的定义处不一致，原表没说死。一次问一个，gyb 裁了再往各 part 传。
- 问题 1：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩，定义处归 `01-gyb.md`（gyb 身份规矩）、`05-rl-cli.md`（命令签名）、`06-hooks-and-permissions.md`（钩子）三处各占一段，还是只归一处？现在 `02`、`10` 指 `01`，`03`、`06` 指 `05`，`04`、`14`、`22` 指 `01` 和 `06`。——已裁 2026-08-17：归 `01`，原话「这个归01吧」。已处理：`01` 第二节补 `--force` 拒收那句并记裁决；`03`/`06`/`14`/`22` 指向改成 `01`；HANDOFF 四点五节改；两份源文档补那句；`04` 已改（rl-part-04，`2c42b92`）；`05` 交 rl-part-05。
- 问题 2：推送表（哪些事件推桌面通知）和 `rl notify` 是一件事还是两件事？原表把推送表归 `01`、notify 归 `05`；`07`、`10`、`11`、`20`、`25` 指 `01`，`09`、`22`、`23`、`24` 指 `05`。——已裁 2026-08-17：一件事，归 `01`，原话「算一件事」「给rl notify指到01吧」。已处理：`01` 第五节补一句并记裁决；`09`/`22`/`23`/`24` 指向改 `01`；HANDOFF 四点五节改；`05`「rl notify」一节缩成一句指 `01`、命令表只留签名行，rl-part-05 已改 `f283974`（`05` 那节里 `01` 没有的句子由 rl-part-05 定稿时报上来再搬进 `01`）。
- 问题 3：阈值表定义处按原表是 `08-trees-init-and-host.md`，但 `04`、`14`、`21`、`23`、`05`、`24` 六份各指了别处（见 HANDOFF 四点五节 `08` 那一行）。是照 `08` 传，还是阈值表另立一处？——已裁 2026-08-17：照 `08`，原话「按照08吧」。已处理：`14`/`21`/`23`/`24` 指向改 `08` 第三节；`04` 已指 `08`；`05` 交 rl-part-05；HANDOFF 改。
- 问题 4（2026-08-17 加，来自 03 事项 6）：runs 发射版去掉 `artifact_dir` 之后，「产物目录是 `<artifact_root>/<run_id>/`」这条约定的定义处归 `08-trees-init-and-host.md`（`artifact_root` 在它那）还是 `12-role-run.md`（run 的产物）？现在 03、12、21、23 和两份源文档都写了这一句，等裁了再定谁是那一处。
- 问题 5（2026-08-17 加，来自 04 事项 3）：04 定稿带出一条新的入账校验「`session_id` 对应的 sessions 账最新版是 `closed` 的会话再写任何账，rl 拒收并提示重新加载角色登记」。定义处按 HANDOFF 判断规矩 3 找不到：入账校验在 `03-ledgers.md`，命令在 `05-rl-cli.md`，事情本身写在 `04-handoffs-and-sessions.md` 第七节 `rl session end` 那条。归哪一份？
- 问题 1 附带（2026-08-17 加，来自 03 事项 3）：「角色带 `--force` 一律拒收，退出码 3；`--as-gyb --quote --force --reason` 算 gyb 身份照写」这一句，等问题 1 裁了定义处之后写进那一份。——已写进 `01` 第二节 2026-08-17。
- 备案（2026-08-17，gyb 提的，不是问题）：「gyb」当机器标识符太怪，考虑改成 `admin` 或 `sudo`。gyb 定：现在不改，全部 part 定稿之后最后一次扫。到时候只改机器看得见的四种（旗子 `--as-gyb`、actor/owner/assignee 取值 `gyb`、`decisions.gyb.jsonl`、`01-gyb.md` 文件名），白话里指人的不动；名字到时候再定。gyb 原话「我觉得现在先不改吧 等最后改一下就行」。
- 裁决原文：（待）
- 要改的地方：裁了之后改 HANDOFF 四点五节对应行，再往指错的 part 传。
- 状态：等 gyb

## 2026-08-17 来自 rl-part-03 关于 03-ledgers.md
- 事项：sessions 账的 `last_activity` 裁成不落账、查询时现算；04 抄了 sessions 行格式，要跟着改。
- 裁决原文：「我觉得用 b 可以 很对」（b 指：不落账，rl 查 `rl session show` / `rl status` / `rl reclaim` 时扫九本账取该 `session_id` 的最大 `ts`；sessions 账不为刷时间戳追加版本）。
- 要改的地方：`04-handoffs-and-sessions.md`：sessions 字段表 `last_activity` 那一栏「rl 每次替这个会话写任何账时顺带刷新，是 sessions 账上的一版还是内存索引施工时定，对外语义是『最后一次写账时间』」改成「不落账，rl 查询时现算，取九本账里该 `session_id` 的最大 `ts`（含 sessions 账自己的行）；sessions 账不为刷新它追加版本；对外语义仍是『最后一次写账时间』」；04 的「源文档没写清的」第 6 条据此销掉。
- 状态：已处理 2026-08-17（两份源文档由统筹 session 改了，commit 9aa0f2c；04 在 rl-part-04 手上，已 SendMessage 交代它改）

## 2026-08-17 来自 rl-part-03 关于 03-ledgers.md（定稿，commit a5d05d4，一次性报九条；last_activity 那条前面已处理）
- 事项 1：feedback 的 `verdict_text` 两版都必填。
- 裁决原文：「都必填」。
- 要改的地方：`09-common-and-feedback.md` feedback 行格式那一句 `verdict_text` 后补「`accepted` 和 `rejected` 两版都必填：采纳的写采纳成什么样，不采纳的写为什么」，与 03 字段表一字不差。
- 事项 2：scratch 中间版 `status` 仍是 `open`；校验头尾查、中间不查；`branch` 改成 deploy 的 `open` 版必填。
- 裁决原文：「可以」（中间版仍 open）；「可以 那就头尾查 中间不查」。
- 要改的地方：`07-quick-lane.md` 第 60 行「格式松，入账校验只校验骨架和快车道标签」改成「中间版格式松，只校验骨架和 `ql_tag`；`open`、`merged`、`dropped` 三版按表查必填」；scratch 表「中间版」那一行改成「中间版（`status` 仍是 `open`）」，`open` 那一行 `branch` 改成「`branch`（deploy）」；07 自己「没写清」第 1 条裁 analysis 的 `base_commit`、`branch` 填什么。设计文档「账本」一节杂账「格式松、只校验骨架和快车道标签」改成「中间版格式松；开张、合回、放弃三版各有必填」。
- 事项 3：角色会话带 `--force` 一律拒收，退出码 3；`--as-gyb --quote --force --reason` 算 gyb 身份照写。
- 裁决原文：「你说得对」（对建议：角色一律拒收退出码 3 附开 issue 给 gyb 的命令）。
- 要改的地方：`--force --reason` 的定义处（01/05/06 哪一处，本邮箱第一段问题 1 待裁）补这一句；`05-rl-cli.md` 退出码 3 那一行加「含角色带 `--force`」。
- 事项 4：`loop/` 九本账进 git，每次 commit 顺手带上，不另设 commit 动作。
- 裁决原文：「A」（路 A：进 git，每次 commit 顺手带上）。
- 要改的地方：`08-trees-init-and-host.md` init 那一段补「`loop/` 进 git，每次 commit 顺手带上，不另设 commit 动作；`.gitignore` 不排除 `loop/`」，08「没写清」第 5 条销掉。
- 事项 5：公共骨架可选字段是 `fix_for` 和 `force_reason` 两个。
- 裁决原文：「都加」。
- 要改的地方：设计文档「账本」一节「七样加一个可选的 `fix_for`」改成「七样加两个可选：`fix_for`、`force_reason`」。
- 事项 6：runs 发射版去掉 `artifact_dir`，产物目录走 `<artifact_root>/<run_id>/` 约定；收尾版留 `data_path`（`ok` 时必填，是产物目录里给 analysis 算数用的文件或子目录）。
- 裁决原文：「我感觉很轻松能从data_path 找出artifact_path啊，而且artifact path定义有点暧昧 能不能不要了」「选A吧那就」。
- 要改的地方：`05-rl-cli.md` `rl run add` 签名去掉 `--artifact-dir`；`12-role-run.md` 第 70 行发射版必填清单去掉 `artifact_dir`、第 62 行补「产物目录是 `<artifact_root>/<run_id>/`」、第 80 行看门狗「产物目录多久没新文件」按约定找；`21-pair-deploy-run.md` 第 77 行、`23-pair-run-analysis.md` 第 17 行发射版字段清单去掉 `artifact_dir`，23 第 38 行和「没写清」第 1 条改写；设计文档 run 一节收尾版四样补 `data_path`。「`<artifact_root>/<run_id>/`」这条约定归 08 还是 12 请统筹定。
- 事项 7（不用同步，备案）：`schema_version` 共用一个数从 1 起；编号从 1 起四位起步自然进五位；`log_tail` 存文本；`applies_to` 自由文本但要写具体程序或参数——别的 part 都只指回 03。
- 状态：已处理 2026-08-17（09/07/08/12/21/23 与两份源文档由统筹改；05 两处交 rl-part-05；事项 3 的定义处并入问题 1、事项 6 的约定归属立为问题 4，都在第一段等 gyb）

## 2026-08-17 来自 rl-part-04 关于 04-handoffs-and-sessions.md
- 事项：`04-handoffs-and-sessions.md` 定稿，commit `130ec90`。「没写清」八条和正文三处不一致全部裁完；`03` 转来的 `last_activity` 裁决已照改。牵连别处的五条一次性列在这里（也在 `04` 文末「要同步到别处的」）。
- 裁决原文：「不用」（progress_note）；「全部」（销号交回）；「我想这个问题应该取决于再干能不能成功吧，如果是啥外部元素，重试能成功那可以再来，但是如果代码有问题得给代码先修了啊」（dispatch）；「留着吧」（last_holder）；「a」（session end --session 不拦）；「删了吧」（release 行 gyb）；「可以 发」（reject 发 fyi）；「不杀」（reclaim）；「按照施工计划吧」（stuck 只改派 issue）。
- 要改的地方：
  1. `20-pair-idea-deploy.md` 第 26 行「`progress_note`（进 `todo` 且不是新建时必填）」改成「`progress_note`（只在 `in_progress` → `todo` 那一版必填；`rejected` → `todo` 不要求）」。
  2. `20-pair-idea-deploy.md` 第 58 行、`21-pair-deploy-run.md` 第 134 行、`22-pair-idea-analysis.md` 第 79 行抄的转移表 `in_progress` → `todo` 行：「谁能写」栏改成「销号钩子、`reclaim`、owner」（删单列的 gyb）；「之后谁拉起」栏改成「owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent），owner 无活会话时进 `rl status` 的「等 gyb 拉起」」。
  3. 新增一条入账校验「sessions 账最新版是 `closed` 的 `session_id` 再写任何账，rl 拒收并提示重新加载角色登记」，定义处按判断规矩 3 找不到（`03` 入账校验 / `05` 命令），请问 gyb 归哪一份。
  4. `01-gyb.md` 第 148 行「按裁决以施工计划的表为准」（fyi 只在 accept 发）改成「2026-08-17 gyb 裁：验收和打回都发 fyi」；`20`、`21`、`22` 抄的转移表 `done_pending_review` → `rejected` 行前提栏「`reason` 非空」后加「；gyb 越过 owner 时 rl 给 owner 发 `fyi`」。
  5. `01-gyb.md` 第 45 行、`05-rl-cli.md` 第 170 行标的 reclaim 杀不杀不一致，两处「按裁决以施工计划的表为准」改成「2026-08-17 gyb 裁：默认不杀，`--kill` 才杀」。
- 状态：已处理 2026-08-17（1、2、4、5 里的 `20`/`21`/`22`/`01` 与两份源文档由统筹改，源文档「接单」「会话生命周期」两段和施工计划第三节、第四节表一并回写；`05-rl-cli.md` 第 170 行在 rl-part-05 手上，已 SendMessage 交代；事项 3 立为第一段问题 5 等 gyb；04 文末「要同步到别处的」五条已标，rl-part-04 已停）

## 2026-08-17 来自 rl-part-05 关于 05-rl-cli.md
- 事项：`05-rl-cli.md` 定稿，commit `656c8a9`。「没写清」十三条和正文一处不一致（inbox 第 3 项）全部裁完；rl-hub 转来的 03/04/sync-inbox 问题 1 三处已改进正文。牵连别处的九条如下，原文和裁决全文见 05 文末「裁决记录」和「要同步到别处的」。
- 裁决原文：「可以」「都同意」「doctor不太关键，先全都按照你推荐的来吧，很费劲的就不用了，我想的是脚本检查和subagent检查结合，比如说写好问题，然后让很多sonnetsubagent去逐个检查」「A」「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」。
- 要改的地方：
  1. `01-gyb.md` 第二节（定义处）：补「`--force` 只越过完整性前提，越不过转移表外的转移，表外转移对 gyb 同样退出码 2，硬改状态走 `withdraw` 再重开」；推送表第 4 条补「在单子落 todo 那刻（open/release/reject/reissue）和 `session end` 销号时查 owner 有无活会话并推」；`rl notify` 补「gyb 也可手动调，不进账」。
  2. `02-decisions.md`：`rl decision stale` 签名改成 `[--handoff ID] [--all]`，去掉 `--mine`。
  3. `03-ledgers.md`：公共骨架可选栏加 `via`（值 `session_end`、`reclaim`，标自动写的行）；sessions 账加 `amend` 版，只许改 `model`（doctor 第 19 项 `model=unknown` 的修法）；handoffs 的 `actual_seconds` 只从 runs 的 `finish` 版来，`done` 不填。
  4. `04-handoffs-and-sessions.md`：`rl handoff done` 签名去掉 `--actual-seconds`；转移表 `in_progress`→`todo` 由销号钩子写的行 actor 记会话角色、`via=session_end`，由 reclaim 写的 actor 记 gyb、`via=reclaim`；`--force` 越不过表外转移。
  5. `08-trees-init-and-host.md`：阈值表加 `lock.timeout_seconds` 默认 10 秒（退出码 4 等多久）；`rl init` 读到会话状态文件拒收退出码 3、只在裸终端跑；`loop/.doctor-acks.jsonl` 由 doctor 首次 `--ack` 时建，不算九本账，`rl init` 不建。
  6. `09-common-and-feedback.md`：`common/` 加一份判断类检查的问题清单文件（名字归 09 定），reviewer 按它派 sonnet subagent 逐题查。
  7. `12-role-run.md`：看门狗（独立进程）只许调 rl 查询命令、不留痕，判定由 run 会话转写进账。
  8. `14-role-reviewer.md`：reviewer 加一项职责：按 `common/` 问题清单派 sonnet subagent 一人一题逐条查，查出的 `rl issue open --to <owner>` 落账（判断类检查不进 doctor，doctor 只留脚本十九项）。
  9. `30-build-steps-verify-tests.md`：待验证第 4 条备案「`rl init` 检查调用者不是任何角色」升正案；第 10 条备案「doctor 列 `model=unknown`」已收成 doctor 第 19 项；`rl session amend`、`rl doctor --ack/--unack/--list-acks`、`lock.timeout_seconds` 要有测法。
- 状态：待处理
