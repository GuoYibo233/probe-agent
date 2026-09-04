# sync-inbox：part session 报给统筹 session 的事项（格式见 HANDOFF 第三节；统筹处理完把状态改成已处理）

## 2026-08-16 夜 来自 统筹 session（总session）关于 HANDOFF.md 四点五节
- 事项：首次核对关联表时发现三样东西各 part 指的定义处不一致，原表没说死。一次问一个，gyb 裁了再往各 part 传。
- 问题 1：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩，定义处归 `01-gyb.md`（gyb 身份规矩）、`05-rl-cli.md`（命令签名）、`06-hooks-and-permissions.md`（钩子）三处各占一段，还是只归一处？现在 `02`、`10` 指 `01`，`03`、`06` 指 `05`，`04`、`14`、`22` 指 `01` 和 `06`。——已裁 2026-08-17：归 `01`，原话「这个归01吧」。已处理：`01` 第二节补 `--force` 拒收那句并记裁决；`03`/`06`/`14`/`22` 指向改成 `01`；HANDOFF 四点五节改；两份源文档补那句；`04` 已改（rl-part-04，`2c42b92`）；`05` 交 rl-part-05。
- 问题 2：推送表（哪些事件推桌面通知）和 `rl notify` 是一件事还是两件事？原表把推送表归 `01`、notify 归 `05`；`07`、`10`、`11`、`20`、`25` 指 `01`，`09`、`22`、`23`、`24` 指 `05`。——已裁 2026-08-17：一件事，归 `01`，原话「算一件事」「给rl notify指到01吧」。已处理：`01` 第五节补一句并记裁决；`09`/`22`/`23`/`24` 指向改 `01`；HANDOFF 四点五节改；`05`「rl notify」一节缩成一句指 `01`、命令表只留签名行，rl-part-05 已改 `f283974`（`05` 那节里 `01` 没有的句子由 rl-part-05 定稿时报上来再搬进 `01`）。
- 问题 3：阈值表定义处按原表是 `08-trees-init-and-host.md`，但 `04`、`14`、`21`、`23`、`05`、`24` 六份各指了别处（见 HANDOFF 四点五节 `08` 那一行）。是照 `08` 传，还是阈值表另立一处？——已裁 2026-08-17：照 `08`，原话「按照08吧」。已处理：`14`/`21`/`23`/`24` 指向改 `08` 第三节；`04` 已指 `08`；`05` 交 rl-part-05；HANDOFF 改。
- 问题 4（2026-08-17 加，来自 03 事项 6）：runs 发射版去掉 `artifact_dir` 之后，「产物目录是 `<artifact_root>/<run_id>/`」这条约定的定义处归 `08-trees-init-and-host.md`（`artifact_root` 在它那）还是 `12-role-run.md`（run 的产物）？现在 03、12、21、23 和两份源文档都写了这一句，等裁了再定谁是那一处。——已裁 2026-08-17：归 `08`，原话「问题4 给8」。已处理：`08` 第一节写成定义处并记裁决；`03`/`12`/`21`/`23` 那句加「约定定义在 08 第一节」；HANDOFF 记。
- 问题 5（2026-08-17 加，来自 04 事项 3）：04 定稿带出一条新的入账校验「`session_id` 对应的 sessions 账最新版是 `closed` 的会话再写任何账，rl 拒收并提示重新加载角色登记」。定义处按 HANDOFF 判断规矩 3 找不到：入账校验在 `03-ledgers.md`，命令在 `05-rl-cli.md`，事情本身写在 `04-handoffs-and-sessions.md` 第七节 `rl session end` 那条。归哪一份？——已裁 2026-08-17：归 `03`，原话「问题5 给3」。已处理：`03`「账本的总规矩」加一段并记裁决；`04` 第七节那句加指向交 rl-part-04；HANDOFF 记。
- 问题 6（2026-08-17 加，来自 05 事项 8）：05 定稿裁「reviewer 按 `common/` 问题清单派 sonnet subagent 逐题查，查出的 `rl issue open --to <owner>` 落账」，可 `14-role-reviewer.md` 第八节和公共规矩第 6 条写的是「reviewer 不开 issue、不派活，卡住也只写进清单交给 gyb」，角色 json 的 `ledger_writes` 也没有 issues。两处不一致：reviewer 查出的问题是开 issue 落账（第八节和 json 跟着改），还是照旧只写进清单交 gyb？——已裁 2026-08-17（已落地：14/09 与两份源文档 rl-hub-v3 `70c766b`）：A，照旧只写清单，gyb 用自己的权限开 issue，原话「全给我审查，然后我用我的权限放到issue里面」。
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
- 状态：已处理 2026-08-17（1/2/3/5/6/7/8 与 20/21/22 抄的转移表行、22 的 done 签名、两份源文档由统筹改；4 由 rl-part-04 改 `42b6594`；9 的 30 未写，记进 README 30 那行给写它的人；8 与 `14` 第八节「不开 issue」冲突，立为第一段问题 6 等 gyb）

## 2026-08-17 夜 来自 rl-hub 关于 03/04/05 三份互查（四路 opus 审读，rl-hub 逐条对原文核过）
- 事项：三份定稿后互查，58 条发现分三堆。甲：引用处没跟定义处、同步没传到位——`03` 的 rl-hub 已改（`701c95d` 及本段同 commit），`04` 八条交 rl-part-04、`05` 十六条交 rl-part-05（两条 SendMessage 全文见 rl-hub 会话记录；要点：04 补 sessions amend 版/六条子命令/字段表照 03 重抄/inbox 五项/accept 关 answered issue/lock 定义处 03/覆盖说明八本账改法/schema_version 从 1 起；05 改 release [--note]/amend 加 --notebook --figure/open 谁能调补快车道/session end 补全部/grant add 加 --text/feedback accept --text 必带/eval retire gyb/scratch list 与 inbox 查谁都行/补 last_activity 现算写法/accept 关 issue/接口一节三处「要 X 收」过期/第 137 行照抄过时句/第 27 行等问题 27/run list --decision --line 反查与 started_at 等由 rl 填/status --json 两键怎么算/锁与写序与退出码与 reclaim 各加一句定义处）。乙：真空白或两说，要 gyb 裁，列在下面 7–27。丙：审读报了但不是矛盾的（withdraw [--quote] 方括号；doctor 扫 handoff_id 为空 vs 必填；started_at/rules_version 无参数由 rl 填；issue reply/close 写权 03 按行 05 按 json 两层都查），不动。
- 要 gyb 裁的（编号接第一段的 1–6）：
  7. `rl handoff estimate` 往 `attempts.step_table` 写东西，`04` 转移表没它的行，`04:77` 又说改单子内容一律是表里的行。给 estimate 加一行，还是那句把 estimate 排除？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，转移表加 `in_progress`→`in_progress` 内容追加行（holder 填分步表），原话「冒烟也是正式动作」。
  8. 快车道补单写序是环：`03:208` scratch 的 `merged` 版必填 `handoff_id`（补单先存在），`04:60` 开补单前提「关联的 scratch 行状态是 merged」（merged 先存在）；`05:64` `open --quick-lane --ql QL` 收 ql_tag，`04` handoffs 字段表没有存它的字段。哪个先写、单子上存不存 ql_tag？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，先开补单（前提改成关联 scratch 行状态是 `open`），拿到编号再 `ql close --merged --handoff ID`；handoffs 加一栏存 `ql_tag`，两边互指。原话「A」。
  9. `batch` 谁分配：`03:19` 说 rl 在锁里分，`04:26`/`05:64` 是调用者 `--batch B` 传的可选字段；`05:64` 说 launch_order 开单从父单抄 batch，`04` 字段表只写「可选」；batch 也没有格式。——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，调用者自由文本、可选，rl 不分配（03 锁那句去掉 `batch`）；launch_order 从父单抄的规矩照旧。原话「A」。
  10. amend 能改哪些字段：doctor 第 2 项用 `amend --decision ID@V` 换悬空引用，`04` 两行 amend 都不许改 decision_refs、`05` amend 签名也没 `--decision`；doctor 第 5 项修法带 `--code-path`，`04:66`（等验收态 amend）只许补 report_paths/output_paths。——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，转移表放宽跟修法走：两行 amend 都允许换 `decision_refs`/`evaluation_refs`（05 签名加 `--decision ID@V`）；`done_pending_review` 行 amend 允许改 `code_paths`。原话「A」。
  11. issue 追问：doctor 第 11 项让开 issue 的角色 `rl issue reply` 追问、issue 回到 open；`03:92` 说 reply 只有 assignee 或 gyb 能写、`03:74` reply 字段挂在 answered 版。要不要追问这条路、怎么写？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，不加追问；一条 issue 一问一答，回答不管用就 close 再开一条新的引旧编号；doctor 第 11 项修法那半句改掉。原话「B」。
  12. `run list` 默认口径：`03:124`「每张单最新一次退出状态为 ok 的行」vs `05:73`「最新尝试且 ok」——最新一跑失败时一个列上一条 ok、一个一条不出。——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，只看最新一次尝试且 ok，失败不出；03:124 改成 05 的写法。原话「B」。
  13. 「handoffs 上的 actual_seconds」：`03:118`、`04:41` 都这么写，`04` handoffs 字段表没这一栏。handoffs 记不记（从 runs 抄一份）还是不记、看去 runs？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，handoffs 字段表加 `actual_seconds`（在 `attempts` 那一次尝试上），`rl run finish` 时 rl 自动从 runs 抄、人不填；预计和实际同一张单对着看。原话「B」。
  14. closed 会话再写账拒收（`03:15`）没给退出码：2（校验拒收）还是 3（无权）？gyb 能不能 `--force` 越过它？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，退出码 3，`--force`/`--as-gyb --force` 都越不过，唯一出路是重新加载角色。原话「A」。
  15. `fix_for` 填什么：`03:43` 说 doctor 修法命令一律带 `--fix-for <扫描项名字>`，`05` doctor 表只有序号没名字、十九条修法命令一条没带 `--fix-for`、`--ack ITEM ID` 也按项号。填项号？命令带不带 `--fix-for`？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，`fix_for` 栏删掉，公共骨架可选栏只剩 `force_reason`、`via`；修法命令不带 `--fix-for`；03 事项 5 那句「七样加两个可选」相应改。原话「B」。
  16. `04:9` 快车道补单是 deploy 开给 deploy，`05:87` 有 `ql open --role analysis`。analysis 的快车道有没有补单？（可能归 `07`，先记着。）——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，没有补单；analysis 快车道只能 `--dropped`，要留就走正常路重做；`ql close --merged` 只对 deploy 开；07「没写清」第 5 条据此销。原话「A」。
  17. `adopted`：`04:61`、`04:95` 认领时「账行标 adopted」，handoffs 和 runs 字段表都没这一栏。哪本账的字段？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：C，两边都标：handoffs 的 `start` 那一版加 `adopted: true`；runs 加一版 `adopted`（记新 holder 会话与 ts）。原话「C」。
  18. sessions `amend` 版和「校验按 status 查」（`03:13`）没接上：amend 行填哪个 status、要不要跟着填该 status 的必填项、能不能 amend 已 closed 的会话（doctor 第 19 项抓的往往是关掉的）。——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，amend 版 `status` 与其他栏照抄最新版、只换 `model`；closed 会话也能 amend（写者是 gyb 裸终端或该角色的活会话，不触问题 14 那条）。原话「A」。
  19. `04:69` 给 reclaim 写 `rejected`→`todo` 的权，`04` 第八节四类处置没有 rejected 这一类（等验收和待干只列不动）。reclaim 动不动 rejected 的单？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，reclaim `--apply` 把超阈值的 `rejected` 单推回 `todo`（actor gyb、`via=reclaim`），04 第八节四类处置加成五类，转移表那行照旧。原话「B」。
  20. `04:71` withdraw 行「有 holder 时通知 holder」——按不变量只有 in_progress 有 holder，从 todo/stuck/等验收/rejected 收回时通知没人收。用 `last_holder`？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，照字面，只在 `in_progress` 收回时通知 holder；其他状态不通知；04:71 那句改成「从 `in_progress` 收回时……」。原话「B」。
  21. `04:73` reissue 行「到＝同状态（接替）」，动作却是旧单 withdrawn、新开一张。「到」栏怎么写？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，新单一律从 `todo` 起、同新建拉起；表里写实：旧单→`withdrawn`，新单→`todo`（`supersedes` 指旧单）。原话「A」。
  22. `03:104` runs 主键说「快车道用 ql_tag」，`03:213` 又说快车道数字不进 runs——同一份里两句。HANDOFF 原留给 07/23 裁；03 已定稿，gyb 直接定？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：A，不进 runs；03:104 删「快车道用 `ql_tag`」；07/23 引用处同改。原话「A」。
  23. `rl inbox` 读过即关通知 issue、`rl doctor --ack` 写 ack 文件，`05:100` 却把它俩列进「查询命令、不进 ledger_writes」。「查询顺带自动写」怎么定性？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B 的方向：`rl inbox` 只读不关，通知类 issue 由收件人做完了自己 `rl issue close`（issues 写权 close 那条补「通知类 issue 的 assignee 也能关」）；`rl doctor --ack/--unack` 算写命令、只有 gyb 能敲。原话「只有做完了的时候才关，巡检要我本人确认」。
  24. `loop/.doctor-acks.jsonl` 不算九本账（`05:212`）：03 总规矩（只增不改、锁、进 git、脏树白名单）管不管它、谁能 ack？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，`.doctor-acks.jsonl` 是普通文件，03 总规矩不管它；谁能 ack 按问题 23：只有 gyb。原话「B」。
  25. 退出码只有 0/2/3/4：查不到编号、内部错误、参数写错落哪个码？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：要求是 agent 分得出发生了什么。落法：加退出码 5「用法错」（参数写错、编号不存在），内部错误 1；所有非零退出标准错误第一行固定格式给原因种类（`--json` 时 `error.kind`），四码变六码（0/1/2/3/4/5），定义处 03、05 照抄。原话「我想让agent有办法识别发生了什么就行」。
  26. doctor 第 17 项要 applied_to 同时含母版和文档，`03:152`「母版和文档都算」（有一样就行）。哪个？——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：B，至少一个即可，doctor 第 17 项改成「applied_to 为空」才报。原话「我觉得。有一些改的方法，不一定会改公共规矩，如果是这样的话就选b。」
  27. `05:27` 说施工计划（b）（c）（d）三条（豁免收窄加 --force --reason、--as-gyb 一律 --quote、grants 只收裸终端）gyb 还没逐条裁，05 的 actor 一节和 01 第二节都建在它们上面。认不认？认了销这句、施工计划第一节那三条标日期。——已裁 2026-08-17（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：(b)(c) 认；(d) 不认——grants 可以在角色会话里 `--as-gyb --quote` 替 gyb 写、不限裸终端。改：01 第二节、05 actor 一节、设计文档原则 1 末句「授权（grants）只收裸终端写的行」、施工计划第一节 (d)、`decisions.gyb.jsonl` 只收裸终端那条不受影响。原话「3 不是，可以替我写」。
  28. （待 gyb 过目，rl-part-05 定，`c2f69c8`）「run 的 inbox 不查过版」这条例外删掉，run 的 inbox 第 3 项照查过版决定（发射单从父单继承 decision_refs）。——2026-08-17 gyb 改了上位规矩（已落地 2026-08-17：底座 03 `81377ac`/`884ac0b`、04 至 `9b78d7c`、05 至 `77213e5`，引用处 rl-hub-v3 `70c766b`）：角色会话被拉起时不自动查收件箱，先干拉它起来的那张单；「所有角色上线第一个动作是 `rl inbox`」这句作废（10–14 各份、01、12:19、两份源文档原则 6 补的「上线第一动作」都要改）。原话「每个角色创建时候，不要自动查收件箱。比如说idea层创建了一个新的idea，他要发给部署层，那么就创建一个新的部署层的角色，这个角色就应该先执行刚才idea给他的工作。」收件箱什么时候看：C，都不自动看，`rl inbox` 是谁需要谁敲的查询命令，gyb 要它看就说一声；SKILL.md 里不再写「上线先 inbox」。原话「C」。问题 28 本身：gyb 又裁（2026-08-17 晨）run 不查 inbox——run 只关注自己那张发射单，一般不会有没带单子的 run 会话；rl-part-05 在 `c2f69c8` 删掉的「run 的 inbox 例外」要改回并扩大成「run 不查 inbox」，`12:19` 同改。原话「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」。
  29. （待 gyb 过目，rl-part-05 定，`c2f69c8`）`rl status --json` 的 `holder_alive` = holder 会话在 sessions 账最新版是否 `open`；`age_hours` 从单子当前状态那一版的 `ts` 起算。——已过目 2026-08-17：认。原话「A」。
- 甲的回报：rl-part-04 八条已改 `bc9bc90`；rl-part-05 十六条已改 `c2f69c8`（第 13 条第 27 行等问题 27）。
- 裁决原文：（待）
- 要改的地方：每条裁了按定义处改，再传引用处；04 的交 rl-part-04、05 的交 rl-part-05、03 的统筹直接改；两份源文档对应句子回写。
- 状态：7–29 已全部裁（2026-08-17，rl-hub-v2 逐条问的）；已全部落地（底座三份见第八节，引用处 rl-hub-v3 `70c766b`）；甲已全部落地

## 2026-08-17 晨 来自 rl-hub-v2 关于 04/05 收问题 6–29 的裁决
- 事项：gyb 说「你现在就交给04和05让他们改了」。rl-hub-v2 已 SendMessage 打包发出：04 十一条（问题 7/8/9/10/13/14/17/18/19/20/21 加问题 28 的 inbox 措辞），05 十九条（问题 6/7/8/9/10/11/12/14/15/16/17/18/23/24/25/26/27/28/29）。每条附裁决原话与改法，消息全文在 rl-hub-v2 会话记录，要点与落点在 HANDOFF 第八节的表。
- 统筹拟的措辞（问题 25，等 03 定义处照抄）：退出码 1 内部错误、5 用法错；所有非零退出标准错误第一行固定原因种类 2 validation / 3 forbidden / 4 lock_timeout / 5 usage / 1 internal，`--json` 时放 `error.kind`。rl-part-05 若改措辞会报回来，03 要跟它一字不差。
- 要改的地方：等两个 session 回「收 N–M，commit <hash>」，统筹记进 README 进度表与本段；03 与其余各份、两份源文档仍按 HANDOFF 第八节清单由统筹落。
- 04 已回：`a7d1ec9`，十一条加问题 28 全落，无相反裁决；顺带改了接口一节快车道那条；问题 19 走现有 rejected→todo 行没另加行。它提醒：`20`/`21`/`22` 抄的转移表行（新 estimate 行、start 行 adopted、withdraw 行通知、reissue 行到栏、两条 amend 行）要统筹同步。
- 05 已回：`1b37593`，十九条全落。它定的三处，03 定义处要一字不差跟上（新统筹落 03 时照抄）：（1）问题 9：05「锁与写序」那句「锁里分配的编号包括 ql_tag、run_id、batch」已去掉 batch，03:19 同改；（2）问题 25 种类词照统筹拟的（validation/forbidden/lock_timeout/usage/internal），03 退出码表照抄；（3）问题 17：不另设 `rl run adopt`，`rl handoff start` 认领时顺带给 runs 写 adopted 版，03 runs 写三版（launched/finished/adopted）；另 fix_for 删后可选栏是「force_reason、via」两个，03:43 同改。
- 问题 30（2026-08-17 晨，质量检查抓出的两说）：sessions amend 版谁能写——已裁：B，gyb 或该角色自己的活会话都能；05 第 40 行谁能调栏「amend gyb」→「amend gyb 或该角色活会话」，04 第 158 行同改，04 第 133 行不动；03:176 落地时同写。原话「B」。
- 质量检查（三路 opus 审 + 统筹逐条核，结果记 HANDOFF 第八节）后的补改：05 `2c965d9`（五处，含统筹漏发的问题 19）、`2dcdd23`（三处）；04 `cec2cc9`（八处）。只剩问题 30（sessions amend 谁能写）等 gyb，裁了发 04 第 158 行、05 第 40 行。
- 问题 30 已落：04 `9b78d7c`、05 `ddafd84`。
- 03 已落 `81377ac`（2026-08-17，rl-part-03 会话）：问题 9/12/13/14/15/16/17/18/22/23/24/25/26/27/30 与 HANDOFF 第八节质量检查补的两处（grants 段、issues 自动关）全进正文；05 定的四处逐字 diff 过一样（锁那句、退出码表与原因种类句、runs 三版、可选栏两个）；sessions 表与 04 一字不差；03:9 白名单写成「九本账的 jsonl」并明写 ack 文件另算。裁决记录一节逐条带原话；「要同步到别处的」列了本份定义处变了、引用处要跟的清单（09/07 写了两遍处、两份源文档、12/21/23、`04:133`「裸终端」措辞）。
- 问题 31（2026-08-17，来自 03 落地）：runs 的 `relink` 版（doctor 第 6 项修法，只改 `handoff_id`）`status` 填什么——03 总规矩说校验按 `status` 查，runs 只给了 `launched`/`finished`/`adopted` 三个值。（a）照 sessions 的 `amend` 版：`status` 与其他栏照抄最新版、只换 `handoff_id`；（b）另加一个 `relink` 值。——已裁 2026-08-17：(a)，原话「a」。03 runs 一段已改（见下一条 commit）；`05:73` runs 那行已补「`relink` 版 `status` 与其他栏照抄最新版、只换 `handoff_id`」，rl-part-05 `77213e5`。
- 状态：已处理 2026-08-17（04 `a7d1ec9`+`cec2cc9`+`9b78d7c`、05 `1b37593`+`2c965d9`+`2dcdd23`+`ddafd84`、03 `81377ac`，底座三份这一轮齐了；其余各份、两份源文档按 HANDOFF 第八节由统筹落；问题 31 已落 03 `884ac0b`、05 `77213e5`）

## 2026-08-17 夜 来自 rl-hub-v3 关于问题 6–31 往引用处传播（一轮 workflow：五组 opus 施工 + 五路 opus 审 + 一路漏网扫描，统筹逐条裁）
- 事项：底座三份冻结后，问题 6–31 的裁决从 03/04/05 传进 `00`/`01`/`02`/`06`–`14`/`20`–`25`、两份源文档、README、HANDOFF 四点五节。审出的漏改与措辞不齐统筹已亲自补（各份文末裁决记录里标「rl-hub-v3 审后补」）。顺手对齐了 05 定稿那一轮漏传的几处（`20` `decision stale` 签名、`13` 杂账中间版措辞、施工计划命令表四处、`01`「没写清」第 5 条标已定）。
- 审出的两说，统筹不裁、攒着等 gyb（接着 inbox 编号）：
  32. ——已裁 2026-08-18（a），原话「a」；已落地 2026-08-18（08 第六节补说明、06 交 rl-part-06 补同一句说明、三句本身不改）。原题：宿主脏树白名单的字面盖住了 doctor 的 ack 文件：`06` 第三节 CLAUDE.md 三句之一和 `08` 抄的同句写「`loop/*.jsonl` 和 `loop/.lock` 不算脏树」，`03` 总规矩按问题 24 已收窄成「九本账的 jsonl 和 `loop/.lock` 不算脏树，`loop/.doctor-acks.jsonl` 不归总规矩管」。白话场景：gyb 敲 `rl doctor --ack` 之后 ack 文件变了，宿主发射门禁按现在的白名单不会拦；要是白名单也收窄成只放九本账，ack 一次就得多 commit 一次才能发射。两个选项：（a）宿主白名单照旧用 `loop/*.jsonl` 字面，ack 文件顺带不算脏，`03` 那句只是说账本规矩不管它、不是说白名单不放它；（b）宿主白名单收窄成九本账 + `.lock`，ack 文件算脏树，改 `06`/`08` 三句。
  33. ——已裁 2026-08-18（a），原话「选a」；已落地 2026-08-18（14 第一节结掉标注、第八节补半句；25 补半句；30 步 5 标已裁；06 json 不动）。原题：reviewer 派 sonnet subagent 算不算「派活」：05 定稿（gyb「全推荐」）让 reviewer 按 `common/` 问题清单派 sonnet subagent 一人一题逐条查；`14` 第八节写「reviewer 不开 issue、不派活」，角色 json 五栏 `dispatches_to` 是无（`06` 同）。问题 6 只裁了开 issue 那一半（只写清单，gyb 自己开）。白话场景：reviewer 会话起一群 sonnet 逐题查是「派活」吗？两个选项：（a）不算——`dispatches_to` 记的是派给别的角色、会开工单的那种；sonnet 逐题查是 reviewer 自己干活的方式，json 不动，`14` 第八节「不派活」后补半句「派 sonnet subagent 逐题查不算」；（b）算——`14` 第八节和 json `dispatches_to` 改成「sonnet subagent（只为问题清单）」，`06` 抄的那份同改。
- 状态：传播已落地（commit 见 git log `research-loop sync:` 2026-08-17 夜两条）；问题 32、33 已裁并落地 2026-08-18（rl-hub-v4）。

## 2026-08-18 来自 rl-part-02 关于 02-decisions.md
- 事项：`02-decisions.md` 定稿，commit `7549704`；八条「没写清」和两处「原文不一致」全裁完；牵连别处的六条如下，全部只是同步、不改 02 本身。
- 裁决原文：gyb 逐题答「甲 甲 乙」「4 甲 5甲 6甲」「甲 甲」（问题一至八；题面见 02 文末裁决记录）。
- 要改的地方：
  1. 决定行按编号前缀落文件（一裁）：凡写「gyb 的决定落 gyb 那本」「按 actor 落文件」的引用处改成「按编号前缀落文件，`actor` 另记」；`03` 词表 `loop/decisions.<actor>.jsonl` 的 `<actor>` 读作前缀里的角色名（03 冻结，冻结后待议，只是读法说明）。
  2. decisions 行新增 `op` 字段（`add`/`update`/`confirm`/`retire`/`merge`），confirm 不算改版（三裁）：凡写「引用版本比最新版小就是过时」的地方（`04` 派活单「依据过时」、`05` `rl status` 段 6 / `rl inbox` 过版项、`07`/`09`/`23` 若有）改成「比最新一个非 confirm 版小才算过时」；`04`/`05` 冻结，冻结后待议。
  3. `rl decision show --with-runs`（五裁）：`05` 命令表若照抄「沿 parent_id 链反查」，改成「先按 `decision_refs` 找起点单子再沿 `parent_id` 收」；05 冻结，冻结后待议。
  4. `30` 测试第 3 条加两例：confirm 之后不标过版；merge 后旧决定废除版 `root_id` 不动。
  5. 「发射单不引决定」这句凡在引用处（`11`、`12`、`23` 若有）出现的，删掉或改成「发射单从父单抄 `decision_refs`，run 不查 inbox」（八确认）。
  6. `README.md` 进度表 02 那行：由「8 留给 gyb / 未开」改成「定稿 `7549704`」（README 我没动，留给统筹）。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

## 2026-08-18 来自 rl-part-00 关于 00-overview.md

- 事项：架构总说明不写——施工步 2 的 `research-loop/ARCHITECTURE.md` 裁掉，定稿的拆分文档本身就是架构说明。
- 裁决原文：「那个旧的说明已经可以不要了 毕竟都变成新的了」「是的 那些分的就是说明，总的没用」
- 要改的地方：`30-build-steps-verify-tests.md`：施工步骤表步 2 改成「不做（2026-08-18 gyb 裁），编号保留」；`08-trees-init-and-host.md`：「两处原文不一致」段里插件目录要补的三样去掉 `ARCHITECTURE.md`。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

- 事项：一切默认英语，任何 part 里不写语言相关的约束。
- 裁决原文：「所有的东西都默认用英语，插件本体里面用英语写，然后不要出现语言相关的约束，就默认只有英语就可以了，不需要强调任何语言」
- 要改的地方：`09-common-and-feedback.md`：「中文底稿给 gyb 过，正式版是英文」去掉语言字样，「没写清」里英文措辞那条销掉（`rule-NN` 编号不变这一句保留）；`30-build-steps-verify-tests.md`：步 6 那行「（英文，……）」去掉「英文」。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

- 事项：拆分文档定稿为准，两份源文档从此不再回写。
- 裁决原文：「b」（选项 b：拆分文档为准，源文档从此不再回写，开头加一句「已被拆分文档取代，只留作历史」）
- 要改的地方：`HANDOFF.md`：传播规矩里「回写两份源文档」去掉；两份源文档 `plans/2026-08-16-research-loop-next-steps.md`、`plans/2026-08-16-research-loop-build-plan.md`：开头各加一句「已被 plans/research-loop-parts/ 取代，只留作历史（2026-08-18）」，之后不再回写任何裁决。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

- 事项：（a）到（i）九条全裁完——（a）（e）（f）（g）（h）（i）六条 2026-08-18 一并认，不写回退清单。
- 裁决原文：「a」（选项 a：六条一并裁「认」，九条全已裁，不需要回退清单）
- 要改的地方：`22-pair-idea-analysis.md`：「没写清」里「（e）待裁」改成「（e）2026-08-18 gyb 认：分析单开单时口径可以是 proposed，交活才要全 approved」；`HANDOFF.md`：「（a）到（i）gyb 还没裁」改成已全裁。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

- 事项：总验收怎么算过——gyb 每看完一对产出说一句「过 / 不过」加一句原因，记进 `00` 裁决记录，五对都过才算过。
- 裁决原文：「总验收是b」
- 要改的地方：`30-build-steps-verify-tests.md`：步 8 总验收验收栏「gyb 自己看」后面补上面这句。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

- 事项：第三轮模拟先不跑，等整套拆分文档定稿、施工完成之后再说。
- 裁决原文：「第三轮先不跑，等整个plan完事，施工完成后再说」
- 要改的地方：`30-build-steps-verify-tests.md`：「第三轮模拟要不要跑」那句改成「先不跑，施工完成后再说」；`HANDOFF.md`：第三轮那句同改。
- 状态：已处理 2026-08-18（rl-hub-v4 传，commit 见 git log `research-loop sync:` 2026-08-18）

## 2026-08-18 来自 rl-hub-v4 关于 02 定稿动到冻结三份的几句（冻结后待议）
- 事项：`02-decisions.md` 定稿（`7549704`）的三条裁决，引用处落在冻结的 `03`/`05` 里，按冻结规矩不改、攒着问 gyb 要不要解冻。
- 裁决原文：gyb 2026-08-18 对 02 答「甲」（按编号前缀落文件）、「乙」（confirm 不算改版、加 `op`）、「甲」（`--with-runs` 第一跳按 `decision_refs`）。
- 要改的地方（都是引用处照抄定义处，字面上过时、意思上没有相反裁决）：
  34. 冻结后待议：（a）`05:47` `rl decision add` 那行「落 actor 自己那本（角色会话 `--as-gyb` 落角色那本）」→「落编号前缀那本：角色会话开的用那个角色的前缀（`--as-gyb` 也一样，`actor` 记 gyb），裸终端开的用 `gyb` 前缀」；（b）`05:48` update/confirm 那行「写完当场列出引旧版而没到终态的单子和 holder」只对 update 成立，confirm 不打印、不算改版；（c）`05:50` `--with-runs`「沿 parent_id 链反查」→「先按 `decision_refs` 找起点单子再沿 `parent_id` 收」；（d）`03:49` 词表 `loop/decisions.<actor>.jsonl` 的 `<actor>` 读作编号前缀里的角色名，只是读法说明，可不动字。`04` 里没找到写「比最新版小就是过时」的句子，不需要动。
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(e) `05:25`「`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行」与 `02` 定稿的编号前缀规矩打架——改成「`decisions.gyb.jsonl` 只装裸终端新开的决定及其全部后续版本（后续版本可以来自角色会话 `--as-gyb --quote`，`session_id` 照记那个会话），开新条的前缀判据见 `02` 第二节」。
- 状态：等最后一期（2026-08-18 gyb 说「你先不要改，等最后一期改」：冻结三份动不动，攒到全部 part 定稿之后一起裁；此前读 `05` 命令表时以 `02` 定稿为准）

## 2026-08-18 03:36 来自 rl-part-06 关于 06-hooks-and-permissions.md
- 事项：06 定稿，十一条「没写清」加一处「两处原文不一致」共十二条 gyb 2026-08-18 全裁完，牵连别处的十条见下；完整清单在 06 文末「要同步到别处的」。
- 裁决原文：问题一「有的时候会用到仓库外的东西，建议弄一个白名单，白名单下的文件都允许修改」；问题二「问题2现在就测一下」（已测通过：头部钩子命令带参数原样到达）；问题三「选a」；问题四「让idea能写gyb」；问题五「5a」；问题六「6 c」；问题七到十二各「a」。
- 要改的地方：
  - `08-trees-init-and-host.md`：阈值表加钩子路径白名单配置项（默认为空，列在里面的路径钩子一律放行）；hooks/ 那行可注「共用脚本带角色参数 2026-08-18 已实测」。
  - `30-build-steps-verify-tests.md`：待验证第 2 条改「已测通过（2026-08-18），主案定，备案删」；第 1 条并入「${CLAUDE_PLUGIN_DATA} 在本机解析到哪，宿主不给就插件在用户目录下自定数据目录」；第 6 条可注「一次 PreToolUse 观察里没有模型标识，正式结论仍等测」。
  - `09-common-and-feedback.md`：rule-08 补「用 Bash 往四个角色目录和 loop/ 写等于绕钩子，不许，要写就用 Write/Edit，账本一律走 rl」；母版加「一个会话只加载一个角色，要换角色另开会话」；第四节补「角色 json 改动同母版流程：feedback 记一条、单独 commit、rules_version 加一」；第七节「notes/ 只有 gyb 写」改「gyb 和 idea 写」。
  - `10-role-idea.md`：json 副本 writes「无目录」改 `notes/`；第 13 行「writes 一栏是空的」照改；reads 按新写法展开（清单抄 06 idea 表）；SKILL.md 加两句纪律（Bash 绕钩子、一会话一角色）。
  - `11-role-deploy.md`：json 副本 reads 去括号备注、dispatches_to 改「run、gpu-runner」、备注移到表下；SKILL.md 加两句纪律。
  - `12-role-run.md`：json 副本 reads 改「handoffs、issues、runs、experiments/、ops/gpu_state.md」，「只读自己那张 launch_order」「只读归自己的 issue」移到表下；SKILL.md 加两句纪律。
  - `13-role-analysis.md`：json 副本 reads 核对无句子；SKILL.md 加两句纪律。
  - `14-role-reviewer.md`：json 副本 reads 从「一切」展开成清单（抄 06 reviewer 表）；第 117 行测试 13 描述对齐「三样都查」；SKILL.md 加两句纪律。
  - `05-rl-cli.md`（冻结后待议）：doctor 加一项「陈旧会话状态文件」（sessions 已销号或超过一天没动，修法删文件，归 gyb 推）；第 100 行「机器检查只查写命令」与 06「三样都查」不一致。
  - `04-handoffs-and-sessions.md`（冻结后待议）：销号钩子动作清单加「删本会话的状态文件」。
- 状态：已处理 2026-08-18（rl-hub-v4 传，08/30/09/10–14 与 01 已改，commit 见 git log `research-loop sync:`；04/05 两处见下一段问题 35）

## 2026-08-18 来自 rl-hub-v4 关于 06 定稿动到冻结 04/05 的两处（冻结后待议）
- 事项：`06-hooks-and-permissions.md` 定稿（`d430192`）的两条裁决，引用处落在冻结的 `04`/`05` 里，按冻结规矩不改，和问题 34 一起等最后一期。
- 裁决原文：gyb 2026-08-18 对 06 答「5a」（会话状态文件销号钩子顺手删、删不掉的 doctor 扫）、问题十二「a」（测试 13 三样都查）。
- 要改的地方：
  35. 冻结后待议：（a）`05` doctor 表加一项「陈旧会话状态文件」——sessions 账已销号或超过一天没动的状态文件，修法删文件、归 gyb 推（十九项变二十项，`03`/`05` 提到「十九项」的句子跟着改）；（b）`05:100` 附近「机器检查只查 SKILL.md 里出现的写命令在不在 `ledger_writes` 里」与 `06`「三样都查」不一致，改成三样；（c）`04` 销号钩子的动作清单加「删本会话的状态文件」。（d）`06` 追裁（`f820504`）：会话状态文件路径改 `loop/.sessions/<session_id>.json`——`05:15` actor 判定那句的路径 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json` 同改；（e）`03` 总规矩「普通文件不算九本账」的清单（`.lock`、`.doctor-acks.jsonl`）加 `loop/.sessions/`，`04` 提到状态文件路径的地方同改。
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(f) `05:233` 接口一节「钩子只挂 Write 和 Edit、只拦两类事」「`test_skill_refs` 只查写命令」同句连带改：钩子管 Write/Edit/Bash 三工具、`test_skill_refs` 三样都查，与 (a)(b) 同源（`06` 定稿）。(g) 落 (a) 和问题 43(a) 时 doctor 项号规矩：删的留空号不重排、新加接末尾编号，既有按项号写的引用（`05:237`、`01:156`、`30:225` 这类）不跟着漂（HANDOFF 第五节 2026-08-21 记）。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `06` 定稿为准）

## 2026-08-18 03:41 来自 rl-part-06 关于 06-hooks-and-permissions.md
- 事项：定稿后追问一条——会话状态文件放哪。
- 裁决原文：「这个放到记忆那个文件夹下面可以吗。如果是tmp的话就弄个tmp的子文件夹」「a」（a 是「放 loop/ 下子文件夹」）。
- 要改的地方：`08-trees-init-and-host.md`：`rl init` 建的东西加 `loop/.sessions/`，`.gitignore` 加一行 `loop/.sessions/`，第一节「读到会话状态文件就拒收」指的路径改成 `loop/.sessions/<session_id>.json`；`30-build-steps-verify-tests.md`：第 1 条刚并进去的「`${CLAUDE_PLUGIN_DATA}` 解析到哪」半条撤销；`03-ledgers.md`、`04-handoffs-and-sessions.md`（冻结后待议，可并进问题 35）：普通文件清单加 `loop/.sessions/`、状态文件路径同改。
- 状态：已处理 2026-08-18（rl-hub-v4 传：08 第一节、30 第 1 条、01 接口一节已改；03/04/05 并进问题 35 (d)(e)）

## 2026-08-18 04:58 来自 rl-part-09 关于 09-common-and-feedback.md
- 事项：09 定稿，「没写清」剩下的八条加第一节表里问题清单文件名一处共九条 gyb 2026-08-18 全裁完（三轮各三个、全答「a」），牵连别处的见下；完整清单在 09 文末「要同步到别处的」，裁决原文在「裁决记录（日期）」。
- 裁决原文：九问全「a」。要点：（1）规格模板五栏 = 8 月 15 日角色定义五栏（角色设定、使用场景、可用工具、限制条件、输出样式），是 SKILL.md 骨架，「可用工具」栏只指到角色 json；（2）rule-NN/principle-NN 编号不变，废掉留空号、新加往后排；（3）`rl decision retire` 必须带理由，谁废都要，理由记进决定行；（4）feedback `target` 只认路径/带前缀编号，表的某一行填文件路径、行写进 text；（5）`rejected` 是终态，再提开新一条；（6）run 的 `reads` 补 feedback；（7）`rules_version` 整数从 1 起、`GLOBAL-RULES.md` 头部一行是唯一真源、`rl feedback accept` 加一并写回那一行；（8）`rl grant revoke` 列出 grantee 还活着的会话让 gyb 挑要不要收、不自动收、撤销后再读算越权 reviewer 按时间戳查；（9）问题清单文件名 `common/REVIEW-CHECKLIST.md`。
- 要改的地方：
  - `02-decisions.md`：`rl decision retire` 带理由，理由记进那一版决定行；行上记理由的栏是新加还是复用 `force_reason` 归 02 定；替 gyb 废除的原话按 `--as-gyb --quote` 既有规矩。
  - `06-hooks-and-permissions.md`：run 那张 json 表 `reads` 加 feedback（「handoffs、issues、runs、feedback、`experiments/`、`ops/gpu_state.md`」）；可注 SKILL.md 骨架是 `common/SPEC-TEMPLATE.md` 五栏。
  - `12-role-run.md`：json 副本 `reads` 同 06 加 feedback。
  - `10-role-idea.md` 到 `14-role-reviewer.md`：SKILL.md 按 `common/SPEC-TEMPLATE.md` 五栏写，「可用工具」栏只指到角色 json；`14` 把判断类检查问题清单带上文件名 `common/REVIEW-CHECKLIST.md`。
  - `08-trees-init-and-host.md`：插件树 `common/` 那行加「判断类检查问题清单 `REVIEW-CHECKLIST.md`」，`rules_version` 可注「整数，头部一行」。
  - `30-build-steps-verify-tests.md`：步 5「判断类检查的问题清单（文件名待定……）」改 `common/REVIEW-CHECKLIST.md`；测试 17 若列 accept 动作，加「写回母版头部 rules_version 那一行」。
  - `00-overview.md`：索引 09 那行可加「判断类检查清单」，不改也不打架。
  - `05-rl-cli.md`（冻结后待议）：`rl decision retire ID [--source ...]` 签名加理由项（必填）；`rl feedback accept`「自动把 rules_version 加一」补「并写回 `common/GLOBAL-RULES.md` 头部那一行」；`rl grant revoke` 一节补「列出 grantee 还活着的会话和加载时间，gyb 挑要不要收，不自动收」；doctor 末段判断类清单可带文件名。
  - `03-ledgers.md`（冻结后待议）：grants 段加撤销后处置两句（列会话让 gyb 挑；撤销后再读算越权按时间戳查）；feedback 段 `target` 加「表的某一行填文件路径、行写进 text」、`status` 加「rejected 终态、再提开新一条」；`rules_version` 可注整数。
  - `04-handoffs-and-sessions.md`（冻结后待议）：sessions 开始版 `rules_version` 补「从 `common/GLOBAL-RULES.md` 头部那一行读」；`rl grant revoke` 列会话后收会话走 `rl session end`。
- 状态：已处理 2026-08-18（rl-hub-v5 传：02 三处、06 两处、12 reads、10–14 五栏骨架句、14 清单文件名、08 插件树行、30 步 5 与测试 17、00 索引行；理由落哪一栏立问题 36；03/04/05 立问题 37 等最后一期）

## 2026-08-18 来自 rl-hub-v5 关于 09 定稿带出的一条空白（等 gyb）
- 事项：`09` 裁了「废除一条决定必须带理由，理由记进那一版决定行」，但理由记在决定行的哪一栏，定义处 `02` 没有现成的栏，`09` 说归 `02` 定；统筹不自己定，等 gyb。
- 裁决原文：gyb 2026-08-18 答「c」（一轮三问，原话「c b a」，第一个是本题）。
- 问题 36：废除一条决定时那句理由，记在决定这一版的哪里？选项：（a）决定行新加一栏专门装「为什么废」，只有废除那一版填——利：查起来一眼看到，理由和正文分开；弊：九本账公共骨架之外多一个只有一种动作用的栏。（b）复用已有的可选栏 `force_reason`（本来是「越权硬写时的理由」）——利：不加栏；弊：一栏装两种意思，事后分不清是硬写理由还是废除理由。（c）理由写进这一版的正文 `text`（废除版正文就是理由）——利：不加栏、不混用，废除版本来正文没别的用处；弊：`text` 一栏在别的版是「决定内容」，废除版变成「废除理由」，读的人要知道这个约定。推荐（c）：不动行格式、不混用别的栏，约定一句就够。
- 要改的地方：裁了改 `02` 第二节字段表和第五节那段，「等 gyb 裁」标注去掉；`05` 签名怎么带理由并进问题 37。
- 状态：已裁并落地 2026-08-18（rl-hub-v5：`02` 第五节表、表下一段、接口一节命令表三处改成「理由就是废除版的正文 `text`」，裁决记录补一行；`05` 签名并进问题 37(a)）

## 2026-08-18 来自 rl-hub-v5 关于 09 定稿动到冻结三份的几处（冻结后待议）
- 事项：`09-common-and-feedback.md` 定稿（`aaca3c9`）九条裁决里有五条的引用处落在冻结的 `03`/`04`/`05` 里，按冻结规矩不改，和问题 34、35 一起等最后一期。
- 裁决原文：gyb 2026-08-18 对 09 九问全答「a」（原话见 `09` 裁决记录）。
- 要改的地方（都是引用处照定义处补，意思上没有相反裁决）：
  37. 冻结后待议：（a）`05` `rl decision retire ID [--source ...]` 签名加理由项（必填；问题 36 已裁 c：理由就是废除版的正文 `text`，签名照 `update` 那样带 `--text`——旗子名是统筹按 `update` 类推的写法，最后一期改 `05` 时由 gyb 过目）；（b）`05` `rl feedback accept` 那句「自动把 `rules_version` 加一」补「并写回 `common/GLOBAL-RULES.md` 头部那一行」；（c）`05` `rl grant revoke` 一节补「列出 grantee 还活着的会话和各自加载时间，让 gyb 挑要不要收，不自动收」；（d）`05` doctor 一节末段「判断类检查的问题清单」可带文件名 `common/REVIEW-CHECKLIST.md`；（e）`03` grants 段（与 `09` 第七节写了两遍）加「撤销时刻之后再读算越权，reviewer 按时间戳查；撤销时 rl 列出还活着的会话让 gyb 挑」；（f）`03` feedback 段 `target` 那句加「表的某一行填那张表所在文件的路径，哪一行写进 `text`」、`status` 那句加「`rejected` 是终态，再提开新一条」、`rules_version` 可注「整数」；（g）`04` sessions 账开始版 `rules_version` 补「从 `common/GLOBAL-RULES.md` 头部那一行读」；`rl grant revoke` 列会话之后收会话走 `rl session end`。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `09` 定稿为准）

## 2026-08-18 06:15 来自 rl-part-08 关于 08-trees-init-and-host.md
- 事项：`08` 定稿（commit `eb02403`），「没写清」九条全裁；待验证第 8 条当场测完，钩子挂法要改；配置新加三键；十二条同步条目全在 `08` 文末「要同步到别处的」，此处只列要点。
- 裁决原文：第 8 条——gyb「A 然后现在就测8」「剩下的建议我确认」；Bash 进钩子——gyb「你就说我也定了，让统筹给06 00也改了」；账路径「定死吧」；中断模板/跑法/门禁/播模板/幂等「第一个选 A 第二个选A 这个要init的时候问的」「A A A」。测试记录 `~/.claude/jobs/caef83fb/tmp/verify8/RESULT.md`。
- 要改的地方：`06-hooks-and-permissions.md`：钩子一份放插件级 `hooks/hooks.json`，脚本先看 `agent_type`（认识的按角色、不认识的最严）没有才按会话状态文件；状态文件由钩子在加载角色 skill 时写、`agent_type` 非空不写；skill 头部不再声明钩子、「参数报角色名」作废；加一段五份角色 agent 定义只塑形不带钩子；匹配范围加 Bash（解析重定向/tee/sed -i/mv/cp 并 realpath），「Bash 绕钩子不许」句相应改。`00-overview.md`：原则 2 改「钩子管 Write、Edit、Bash」；索引 `08` 覆盖栏加 `agents/`。`30`：第 8 条状态改已测（主案、备案一都不成立，走插件级钩子按 `agent_type` 判角色）、第 2 条备注被取代、「没写清」第 5 条改「建 agents/ 不建 workflows/」、步 1 交付加 agents/ 五份、步 7 交付与验收加 `run.py` 门禁白名单加 `loop/*.jsonl`/`loop/.lock` 且 selfcheck 过。`12`：Phase 6b 宿主销号调 `launcher.abort_cmd`（new1 `run.py gpu-jobs finish`）留空跳过。`13`：init 播三样。`07`/`05` 接口一节补 `launcher.abort_cmd`、`repo_run`、`host_ledgers`。冻结三份等最后一期：`04`（派活用插件角色 agent 类型起 subagent；subagent 的 session_id 与父会话相同、登记那句等第 5 条测完定）、`05`（`rl init` 幂等/逐项问/不动宿主代码；`rl run finish` 调 abort_cmd；doctor 对账按 `host_ledgers` 的 `kind: runs`）、`03`（词表九名旁注「位置钉死，配置里没有账路径」）。
- 状态：已处理 2026-08-18（rl-hub-v5 传：06 六处改写、00 原则 2 与裁决 5 与索引与第八节、30 四处、12 两处、13 一处、07 一处、10–14 各一句；纪律句改法与 agent 定义母版流程立问题 38 等 gyb；03/04/05 三条立问题 39 等最后一期）

## 2026-08-18 来自 rl-hub-v5 关于 08 定稿带出的两条空白（等 gyb）
- 事项：`08` 定稿把 Bash 裁进钩子匹配范围、加了 `agents/` 层五份角色 agent 定义，两处后果 `08` 说归 `06`/`09` 定，统筹不自己定，等 gyb。
- 裁决原文：gyb 2026-08-18 答 38-1「b」、38-2「a」（一轮三问，原话「c b a」，后两个是本段）。
- 问题 38（两小问）：
  - 38-1. 钩子现在也看 Bash 命令里能解析出的写目标（重定向、`tee`、`sed -i`、`mv`/`cp`），原来那句「用 Bash 往四个角色目录和 `loop/` 写等于绕钩子，不许」的纪律怎么改？选项：（a）删掉，钩子管了就不用纪律——利：少一句；弊：钩子解析不出的写法（脚本内部写文件、`python -c`、heredoc）没人管。（b）改成「钩子拦不到的写法一律不许往四个角色目录和 `loop/` 写；要写就用 Write/Edit 或走 `rl`」——利：钩子和纪律接上，没有缝；弊：想不出。推荐（b），强烈推荐。落点：`06` 第三层那句、`09` rule-08、`10`–`14` 两句纪律里的第一句。
  - 38-2. 五份角色 agent 定义（`agents/<role>.md`，提示词加预加载 skill 加工具面）改一处，走不走母版流程（记 feedback、单独 commit、`rules_version` 加一）？选项：（a）走，和角色 json 一样——利：所有会话行为的来源都进版本号，reviewer 能对；弊：小改也要走一遍。（b）不走，随手改——利：省事；弊：agent 定义改了没人知道，和「角色 json 改一栏算改母版」那条裁决不一致。推荐（a），强烈推荐。落点：`06` agents/ 那段、`09` 第四节。
- 状态：已裁并落地 2026-08-18（rl-hub-v5：38-1 `06` 第三层那句、`09` rule-08、`10`–`14` 两句纪律第一句、`06` 接口一节；38-2 `06` agents/ 那段、`09` 第四节；各份裁决记录补行）

## 2026-08-18 来自 rl-hub-v5 关于 08 定稿动到冻结三份的几处（冻结后待议）
- 事项：`08-trees-init-and-host.md` 定稿（`eb02403`）有三条的引用处落在冻结的 `03`/`04`/`05` 里，按冻结规矩不改，和问题 34、35、37 一起等最后一期。
- 裁决原文：gyb 2026-08-18 对 08「定死吧」「A A A」「剩下的建议我确认」（原话见 `08` 裁决记录）。
- 要改的地方：
  39. 冻结后待议：（a）`04` `dispatch=auto` 起 subagent 时用插件的角色 agent 类型（`agents/<role>.md`），不用 general-purpose；第四节「subagent 加载角色 skill 那一刻和普通 session 一样登记进 sessions 账」那句——subagent 的 `session_id` 与父会话相同、钩子输入多 `agent_id`/`agent_type`、状态文件不写，subagent 算不算一次 sessions 行、`session_id` 记什么，等待验证第 5 条测完再定；（b）`05` `rl init` 一行补「重跑无副作用；逐项问配置；不动宿主代码和仓库 `.claude/`」；`rl run finish` 一节补「中断收尾里宿主销号调 `launcher.abort_cmd`，留空跳过」；doctor「两本 runs 账对账」按 `host_ledgers` 里 `kind: runs` 找宿主账；接口一节 `08` 那条键清单加 `launcher.abort_cmd`、`repo_run`、`host_ledgers`；（c）`03` 词表九个文件名旁注「位置钉死，配置里没有账路径（2026-08-18 gyb 裁，`08` 第一节）」。
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(a) 后半（subagent 算不算一次 sessions 行、`session_id` 记什么）依赖待验证第 5 条，最后一期时还没测完就明记挂起，别硬落。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `08` 定稿为准）

## 2026-08-21 04:00 来自 rl-part-01 关于 01-gyb.md
- 事项：01 定稿。「没写清」八条全清（第 5、7、8 条此前已由 05 定稿覆盖，第 8 条今天确认同值不需同步）；今天新裁六条，其中「桌面通知不做」「定期提醒不做」两条牵连面大，完整清单在 01 文末「要同步到别处的」，裁决原文在「裁决记录（日期）」。
- 裁决原文：要点五条。（1）「收拾」use case 只指 status 段 7、9 加 reclaim 预览，段 6 挪进「收回、改版重派」；原话「A 这个回收是一个完全单独的命令，大部分情况下自动找全部」。（2）use case 表加一行「回问题单」倒推 status 段 2；原话「那么就加入回问题单子」。（3）桌面通知这一版整个不做，推送表五档、`rl notify` 一并销，等 gyb 的事只维护 `rl status` 一个出口；原话「收件箱这个算了 先不做，就维护一个我要看的东西就行，我自己记得定期手动看」。（4）定期提醒也不做，`notify.reminder_days` 删；原话「那这个砍了吧」。（5）reviewer：gyb 口头交代审哪条决定、reviewer 照交代 focus 登记；gyb 看完清单后动作各落各的账不新加登记；原话「都按推荐来」。
- 要改的地方（详见 01「要同步到别处的」）：
  - `05-rl-cli.md`（冻结，只报不催）：「rl notify」一节与签名行删；接口一节待验证 6、7 两条标已销。
  - `04-handoffs-and-sessions.md`（冻结，只报不催）：第 164 行「定时提醒每 `notify.reminder_days` 天叫他一次」改「gyb 自己记得定期手动跑」。
  - `08-trees-init-and-host.md`：阈值表删 `notify.reminder_days`；入口 skill 领路「收到定期提醒」条触发词改 gyb 自己定期开工；`research-loop.json` 键表如列 `notify.*` 同删。
  - `09-common-and-feedback.md`（连带冻结的 `03` 写了两遍处）：「assignee 是 gyb 的那一版触发桌面通知」改「进 `rl status` 段 2」；三条阈值那句删 `notify.reminder_days`。
  - `30-build-steps-verify-tests.md`：待验证第 6、7 条销，失败备案转正。
  - `00-overview.md`（已定稿）：原则 6 推论「桌面通知只是……写成一张表」半句冲突，怎么改归 00 裁。
  - 引用处措辞：`07:141`、`10:177`、`11:170`、`20:121`、`25:76`「桌面通知推送表/哪几段推送」改「桌面通知这一版不做」；`22:59` 整句、`24:27/47/66`「触发桌面通知」同口径改。
  - `14-role-reviewer.md`：开工登记那句补「照 gyb 口头交代登记」。
- 状态：已处理 2026-08-21（rl-hub-v5 传：08 阈值行删与领路句、09 两处与接口两行、30 待验证 6/7 销、00 原则 6 半句统筹改、14 口头交代句、07/10/11/20/22/24/25 措辞七处；05/04/03 三条立问题 40 等最后一期）

## 2026-08-21 04:29 来自 rl-part-07 关于 07-quick-lane.md
- 事项：07 定稿。「没写清」八条全裁（第 2、5 条此前已销），「两处原文不一致」一处定稿，另立两条纲领：快车道对主程序在验证完之前不存在、修好账上报过的 issue 必须回复关掉不许静默修。完整清单在 07 文末「要同步到别处的」，裁决原文在「裁决记录（日期）」。
- 裁决原文：要点六条。（1）总纲，原话「对于主程序，快车道的东西在验证完之前是不存在的，验证好之后一口气合并到主要的地方」。（2）问题 1/3/4/9/10 原话「A」：analysis 开张行只填 `dir`；补单报告目录用 `experiments/<ql_tag>/` 且单号事后不改名；补单 `code_paths` 必填；`decisions.deploy` 的 file 来源按普通规矩填主仓库路径（补决定发生在合并之后）；快车道不归研究线、`rl status` 按线分组时单独列一堆。（3）问题 6/7/8 gyb 确认「可以」：`--from` 转进的单子离开待干、就是出口的补单不另开，合回追加一版直达 `done_pending_review`、放弃退回 `todo` 去标记；宿主 gpu-runner 不进插件的账（不登记 sessions、不写杂账）；`rl ql close` 两条路都删工作树与同名分支。（4）不一致处定稿：开单动作 deploy 做，owner 记 gyb。（5）公共规矩，原话「我希望这个是个规则，而不是什么补丁特例」：凡修的东西是账上报过的 issue，修完必须回复并关掉，不许静默修——定义处归 09。（6）错误处理机制维持现状（发射员落 issue 后销号、修好拉起新发射员），原话「那就选A吧」，正文无改动。
- 要改的地方（详见 07「要同步到别处的」）：
  - `03-ledgers.md`（冻结，只报不催）：scratch 表 `open` 版必填改「deploy 填 `worktree`、`base_commit`、`branch`；analysis 只填 `dir`」。
  - `04-handoffs-and-sessions.md`（冻结，只报不催）：快车道新建行前提加「`code_paths` 非空」；转移表补 `--from` 转进与出口两行；「owner 就是开单角色」通则加快车道补单例外（开单 deploy、owner 记 gyb）；sessions 账补「宿主 gpu-runner 不登记」。
  - `05-rl-cli.md`（冻结，只报不催）：`rl ql close` 补「两条路都删工作树与同名分支」；`rl ql open --from` 补「单子标 `quick_lane` 并离开待干」；转进单出口那一步的子命令名归 05 定。
  - `01-gyb.md`：`rl status` 段 9／`--group-by line` 补「没关的快车道不归线，单独列一堆」。
  - `09-common-and-feedback.md`：公共规矩加一条「凡修的东西是账上报过的 issue，修完必须回复并关掉那条 issue，不许静默修」。
  - `11-role-deploy.md`：部署报告目录约定补「快车道补单的报告目录用 `experiments/<ql_tag>/`，拿到单号之后不改名」。
- 状态：已处理 2026-08-21（rl-hub-v5 传：01 段 9 不归线、09 公共规矩加 rule-09（连带八条改九条扫 00/06/11/30/README/HANDOFF）、11 报告目录句与 owner 不一致收口；03/04/05 六条立问题 41 等最后一期）

## 2026-08-21 来自 rl-hub-v5 关于 01 定稿动到冻结三份的几处（冻结后待议）
- 事项：`01-gyb.md` 定稿（`cd569ab`）「桌面通知不做」「定期提醒不做」两条裁决的引用处落在冻结的 `03`/`04`/`05` 里，按冻结规矩不改，和问题 34、35、37、39 一起等最后一期。
- 裁决原文：gyb 2026-08-21「收件箱这个算了 先不做，就维护一个我要看的东西就行，我自己记得定期手动看」「那这个砍了吧」。
- 要改的地方：
  40. 冻结后待议：（a）`05`「rl notify」一节（含 `rl notify --text` 签名行）删，命令表如有该行同删；接口一节待验证清单句里第 6、7 条标已销；（b）`04` 第 164 行附近「定时提醒每 `notify.reminder_days`（默认 7）天叫他一次」半句删，改「gyb 自己记得定期手动跑」；（c）`03:92` issues 入账规则「`assignee` 是 `gyb` 的那一版（含首次开单）触发桌面通知」改「进 `rl status` 段 2」（`03` 与 `09` 写了两遍处）。
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：问题 40 原来只盖住三处，评审又扫出三处同源残留——(d) `05:58` issue 命令行「`--to gyb`（开单或改派）触发通知」改「进 `rl status` 段 2」（`09:119` 同句 2026-08-21 已改，写了两遍处）；(e) `04:221` 阈值清单删 `notify.reminder_days` 一项；(f) `05:235` 接口一节阈值清单删 `notify.reminder_days`。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `01` 定稿为准）

## 2026-08-21 来自 rl-hub-v5 关于 07 定稿动到冻结三份的几处（冻结后待议）
- 事项：`07-quick-lane.md` 定稿（`7a01842`）六条裁决的引用处落在冻结的 `03`/`04`/`05` 里，按冻结规矩不改，等最后一期。
- 裁决原文：gyb 2026-08-21（原话见 `07` 裁决记录；总纲「快车道对主程序在验证完之前不存在，出口一口气合并落账」）。
- 要改的地方：
  41. 冻结后待议：（a）`03` scratch 表 `open` 版必填改「deploy 填 `worktree`、`base_commit`、`branch`；analysis 只填 `dir`」；（b）`04` 转移表快车道「（新建）→ done_pending_review」行前提加「`code_paths` 非空」；（c）`04` 转移表补两行——「`todo` 的单 `rl ql open --from` 标 `quick_lane`、离开待干不占 holder」「`quick_lane` 标记的单出口追加一版直达 `done_pending_review`（前提同快车道新建行）／放弃退回 `todo` 去标记」；（d）`04`「owner 就是开单角色」通则加例外「快车道补单开单动作 deploy、owner 记 gyb」；（e）`04` sessions 账补「宿主 gpu-runner 不登记 sessions 账」；（f）`05` `rl ql close` 补「`--merged` 和 `--dropped` 都删工作树与同名分支」、`rl ql open --from` 补「单子标 `quick_lane` 并离开待干」、转进单出口那一步的子命令名归 `05` 定；（g）`05:236` 接口「公共规矩八条」改九条（rule-09 修必销案，2026-08-21 立）。
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(h) `05` `rl status` 段 9／`--group-by line` 那里补「没关的快车道不归线，单独列一堆」（`07` 定稿，`01` 已落，`05:163`/`05:166` 当时漏攒）；(i) (d) 那条评审核对 `04` 现文可能已有同义句，落地时先核对、已有就只核不加；(j) (f) 里「转进单出口那一步的子命令名归 `05` 定」读作「最后一期改 `05` 时由 gyb 定」——冻结规矩不给 rl-part-05 派活。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `07` 定稿为准）

## 2026-08-21 来自 rl-part-10 关于 10-role-idea.md
- 事项：`10-role-idea.md` 定稿（`96459b4`），十一条「没写清」全部处理（十条 gyb 裁、第 10 条按 2026-08-18 已有裁决销），两处原文不一致收口；牵连非冻结五份的六处如下，冻结三份的另立下一段。
- 裁决原文：gyb 2026-08-21「砍掉，默认能读」「不用申请」（notes/ 获准机制整套砍掉）；「我有时候会手动要求更改的」（amend 补用例）；「只在交代里说」（测试标准）；「允许，两边都算」（跨根单归线）；「你干完自己算数」（--manual 单验收）；「只报你，你裁了才动」（reviewer 清单）；「只列本会话手上的」「单列一项」（inbox 两处不一致收口）。
- 要改的地方：
  42. （a）`06-hooks-and-permissions.md`：idea json `reads` 表下备注「`notes/` 要 gyb 发 `read:notes` 才读」删（10 的 json 副本未动，等 `06` 改了传回）；（b）`08-trees-init-and-host.md`：`rl init` 逐项问里「问 gyb 一次要不要当场给 idea 发 `read:notes`」删；（c）`01-gyb.md`：gyb use case 表「批 `read:notes`」的活删，「授权只有 gyb 能写」段里 `read:notes` 例子随 grants 账存废定（存废见 43(c)）；（d）`20-pair-idea-deploy.md`：「怎么测试、什么算成功」只在起下游 subagent 的交代里说、不写进单子；`--manual` 单默认 gyb 自己验收；（e）`14-role-reviewer.md`、`25-pair-reviewer-idea.md`：reviewer 拿 grant 当「idea 有没有读过 notes/」凭据的核对项删；idea 读完清单不自行处置、只报 gyb 裁了才动；（f）`11` 到 `14` 收件箱段：过版项口径统一「本会话手上单子引的过版决定」、feedback 裁决单列一项。
- 状态：已处理 2026-08-21（rl-hub-v6：(a) `06` 已改、json 副本已传回 `10`；(b) `08` 已改；(c) `01` 获准段、第 3 件事、接口行已改，use case 表查无「批 `read:notes`」行、授权段无 `read:notes` 例子；连带 `00` 砍掉手续清单、`02` doctor 段与接口两处、`09` grants 两段与接口三行统筹补扫已改；(d) `20` 正文两处已改、`21` 抄的转移表 accept 行同步补备注、跨根归线裁决连带记进 `20`/`21`/`22`/`23` 裁决记录；(e) `25` 已改并销「没写清」第 7 条，`14` 已 SendMessage 交代 rl-part-14；(f) 已 SendMessage 交代 rl-part-11 到 14——`11`/`13` 正文五样已与口径一致、`12` run 不查 inbox 不涉、`14` 「四类…再加」句要改；`24` 接口「列哪四类」顺手收成五类）
- 补记 2026-08-21（评审修复，gyb 授权）：(e) 交代 rl-part-14、(f) 交代 rl-part-12/14 的部分，文件本体一直没落（评审核实）；清单已重发给 rl-part-12/14，按回执制（HANDOFF 第四节 2026-08-21 立）等它们的回执段。
- 回执 2026-08-21（rl-hub-v6 核）：(f) 的 rl-part-12 侧随 `c214ebf` 收口——核对结论是不涉（run 不查 inbox，`12` 正文本来就没有收件箱段）；(e) 与 (f) 的 rl-part-14 侧仍等回执。

## 2026-08-21 来自 rl-part-10 关于 10 定稿动到冻结三份的几处（冻结后待议）
- 事项：`10-role-idea.md` 定稿（`96459b4`）裁决的引用处落在冻结的 `03`/`04`/`05` 里，按冻结规矩不改，等最后一期。
- 裁决原文：同上一段。
- 要改的地方：
  43. 冻结后待议：（a）`05` doctor 十九项里「决定来源指向 notes/ 但 grants 查不到 `read:notes`」一项删；（b）`05` `rl status --group-by line` 改「跨根的单在每条相关线里都出现」；（c）`05` `rl grant` 子命令与 `03` grants 账的存废（permission 第一版只有 `read:notes` 一种，机制砍掉后账里没有内容）请统筹按定义处问 gyb；（d）`03` `line` 字段语义改「`decision_refs` 可分属不同根决定，跨根的单在每条相关线的视图里都出现」；（e）`04` 转移表 `done_pending_review`→`accepted` 行「验收人是 owner」补备注「`dispatch=manual` 的单默认 gyb 自己验收，`fyi` 照发」。
  （统筹补扫 2026-08-21 rl-hub-v6：(a) 的连带还有两处——`05` `rl init` 签名行里「问一次要不要给 idea 发 `read:notes`」那半句、`05` 接口一节「`read:notes` 的申请走法」一行，同属获准机制砍掉，最后一期一起删。）
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(d) 的 `line` 是 handoffs 字段，定义处是 `04`（`03` 里没有这个字段），落点从 `03` 改 `04`——`04` 字段表 `line` 的语义句照 (d) 的内容改。
  - 补记 2026-09-05（rl-hub-v6）：(c) 的存废施工期按代裁 D-01 留位不建立——账本清单保留 grants 行标 `PENDING(issue 43c)`，不写 schema、不写 `rl grant` 子命令、相关测试用例跳过（`plans/2026-09-04-research-loop-proxy-decisions.md`）；存废本身仍等最后一期 gyb 裁，本段状态不变。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `10` 定稿为准）

## 2026-08-21 来自 rl-part-11 关于 11-role-deploy.md
- 事项：`11-role-deploy.md` 定稿（`5e8dffa`），七条「没写清」全部 gyb 裁毕，「两处原文不一致」此前已由 `07` 收口未再问；牵连非冻结五份的四处如下，冻结三份的另立下一段。
- 裁决原文：gyb 2026-08-21「照单子的编号起名」（正常工单报告目录）；「工单格式里加一个位置」（方向名 track 从工单继承）；「全收」（code_paths 含宿主文件）；「开场话把单子内容全抄一遍」（派活提示）；「不能先合并好再记上去吗」加确认「就这么定：先合并再补记」（快车道出口顺序）；「直接报给 gyb 让他修」（done_pending_review 报告丢了，kind 取既有 `cannot`）；「报位置、留着不动，处置由你定」（收回后的半截产物）。
- 要改的地方：
  44. （a）`07-quick-lane.md`：出口顺序改「gyb 先 merge → deploy 开补单、补 `decisions.deploy` → `rl ql close --merged --handoff ID`」，决定来源和报告路径的存在性检查一律按主树查，「主分支上永远只有走过工单的代码」句认下合并到补单之间的短窗口；（b）`10-role-idea.md`、`20-pair-idea-deploy.md`：idea 开工单时填方向名一栏，deploy 开发射单照抄；（c）`25-pair-reviewer-idea.md`：reviewer 的代码清单按全量口径读（含 `experiments/` 外宿主文件）；（d）`12-role-run.md`、`21-pair-deploy-run.md`：派活开场提示全抄单子内容（run 被拉起时开场话里有全貌；裁的场景是 deploy 派 run，别的通道要不要照此由统筹定）。
- 状态：已处理 2026-08-21（rl-hub-v6：(a) `07` 出口顺序本来就是先 merge 后补单——2026-08-17 问题 8 已定，这次按确认补记，存在性按主树句、短窗口句已补进正文；(b) `10` 「工单怎么开」补 `track` 句，`20` 记裁决记录，`21` track 行改「从父单抄」；(c) `25` 记裁决记录，`14` 的代码清单口径已 SendMessage 交代 rl-part-14；(d) `21` 记裁决记录、`12` 已 SendMessage 交代；「别的通道要不要照此」不归统筹定，立问题 46 等 gyb）
- 补记 2026-08-21（评审修复，gyb 授权）：(d) 交代 rl-part-12 的部分文件本体没落（评审核实）；清单已重发，按回执制等回执。
- 回执 2026-08-21（rl-hub-v6 核）：(d) 的 rl-part-12 侧已落——`c214ebf` 把「开场话抄单」记进 `12` 文末裁决记录备查行，这段的事项全部收口。

## 2026-08-21 来自 rl-part-11 关于 11 定稿动到冻结三份的几处（冻结后待议）
- 事项：`11-role-deploy.md` 定稿（`5e8dffa`）裁决的引用处落在冻结的 `03`/`04`/`05` 里，按冻结规矩不改，等最后一期。
- 裁决原文：同上一段。
- 要改的地方：
  45. 冻结后待议：（a）`04` handoffs 字段表 `work_order` 加 `track` 一栏（idea 开单时填），`launch_order` 开单从父单抄 `track`；（b）`04` withdraw 一侧补一句「收回时 holder 把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定」；（c）`05` `rl handoff open --type work_order` 要能收方向名，`launch_order` 自动从父单抄之后发射单侧的方向名参数改可省；（d）`03` `code_paths` 字段说明补「全收：这张单改过的代码路径不论在不在 `experiments/` 里都列，宿主文件也算」。
  - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(e) (d) 的 `code_paths` 是 handoffs 字段，定义处是 `04`（`03` 里没有这个字段），落点从 `03` 改 `04`；(f) (a) 的 `track` 与 `04` attempts 里已有的 `track` 同名同义——`work_order` 加顶层 `track`（idea 开单填），`launch_order` 不另加顶层栏，开单时从父单顶层 `track` 抄进第一次尝试的 `attempts[].track`，两处一个意思。
- 状态：等最后一期（gyb 2026-08-18：冻结三份先不改，攒到全部 part 定稿之后一起裁；此前以 `11` 定稿为准）

## 2026-08-21 来自 rl-hub-v6 关于派活开场话的适用范围（等 gyb）
- 事项：`11` 定稿裁了「deploy 派 run 的开场话把单子内容全抄一遍」，rl-part-11 提出别的派活通道（idea 派 deploy、idea 派 analysis）要不要照此，统筹不代裁，攒着等 gyb。
- 裁决原文：（待 gyb；`11` 那条的原话是「开场话把单子内容全抄一遍」，裁的场景是 deploy 派 run）
- 要改的地方：
  46. 若推广到所有派活通道：`20`、`22` 各补一句「派活开场提示全抄单子内容」，`10` 的交代句同步；若只限 deploy 派 run：维持现状（`21` 裁决记录与 `12` 已落）。
- 补记 2026-09-05（rl-hub-v6）：施工期代裁 D-02 按推荐取了「推广到所有派活通道」，已落进插件施工步 6 的说明书（`plans/2026-09-04-research-loop-proxy-decisions.md`，gyb 待审）；gyb 审 D-02 就是答这道题，认可后分册侧照 46 的清单落，状态先不动。
- 状态：等 gyb

## 2026-08-21 来自 rl-part-13 关于 13-role-analysis.md
- 事项：评审修复清单六条已落，commit `e31d4ca`。第 6 条只落了一半：`ledger_writes` 的 issues 已加 close（限自己开的），「use case 表补对应行」落不了，13 这份没有 use case 表，已回报 reviee。核对时 `06` 的 analysis json（reads 加 scratch、issues 加 close）还没改，等 reviee 落 `06` 侧。
- 状态：已处理（评审修复确认 2026-08-21：13 不补 use case 表，json 副本加表下备注就是落点；`06` 侧同日由评审修复落）

## 2026-08-21 来自 评审修复会话（gyb 授权） 关于 冻结三份的评审补扫
- 事项：`plans/2026-08-21-research-loop-parts-review.md` 坐实的问题里落在冻结 `03`/`04`/`05` 正文、且不属于问题 34/35/37/39/40/41/43/45 任何一段的，编成问题 47 攒着等最后一期。34/35/39/40/41/43/45 各段 2026-08-21 追加的「统筹补扫」行也是这次评审补的。
- 裁决原文：（gyb 2026-08-21 授权评审修复代裁，逐条依据写在行内；最后一期落地时 gyb 可逐条否）
- 要改的地方：
  47. 冻结后待议：（a）`03:242`「合回六步的顺序（先开补单再 `ql close --merged`）」——`07` 里没有「六步」这个说法，改成「合回的出口顺序（gyb 先 merge → deploy 开补单、补 `decisions.deploy` → `ql close --merged --handoff ID`），见 `07` 出口一节」（问题 44(a) 已确认此序）。（b）`04` 第六节销号钩子那段补一句跨账写序：「先逐张 release 交回（release 行的 `session_id` 记本会话，此刻 sessions 还没 `closed`，写得进），最后落 sessions 的 `closed` 版（含 `released_handoffs` 清单）」——`03:15` 已明写此序并说「`04` 第六节定的顺序」，`04` 补上这句指向才成立。（c）`03:196` scratch 段「analysis 和 reviewer 默认不读这本账」改成「这本账日常不进审读顺序：deploy 和 analysis 只在快车道里读写自己那条 `ql_tag` 的行，reviewer 审快车道时才读（reads 清单里有）」——`06` 定稿的 json 里 reviewer 的 reads 有 scratch、analysis 的 ledger_writes 有 scratch 全部（`07:64` 同句 2026-08-21 已按此改，写了两遍处）。（d）`03:4` 与 `03:240`「`rl status`……在 `05-rl-cli.md`」各补半句「（十段内容定义处是 `01`，`05` 是命令表）」。（e）`04:220`「`rl status` 的十段全文……写在 `05-rl-cli.md`」同补这半句。（f）`04:209` 括号里那串「……待同步」补「（已同步 2026-08-17 夜 rl-hub-v3 `70c766b`，见文末「要同步到别处的」末条）」——正文标注与文末已同步标注打架，以文末为准。
- 状态：等最后一期（2026-08-21 评审修复立）

## 2026-08-21 来自 rl-part-12 关于 12-role-run.md
- 事项：评审修复清单六条已落，commit `c214ebf`。六条是：钩子三工具口径三处、`track` 从父单抄两处、母版九条、认领时点两句对齐 rl 自动判、`stuck` 只限三种 `failed` 且 `anomaly` 照走 6a、`rl inbox` 过版项口径核对不涉（run 不查 inbox）。顺带把 `11` 定稿「开场话抄单」记了备查行。
- 状态：已处理 2026-08-21（rl-hub-v6 核 2026-08-21：`c214ebf` 的 diff 与六条逐一对上；机器检查 `12` 的警告已消，裁决记录引旧字样那行进白名单 `5f23ec1`；段 42(f) 与段 44(d) 的 rl-part-12 侧随之收口）

## 2026-09-05 来自 施工统筹会话 关于 施工期代裁动到冻结三份的几处（冻结后待议）
- 事项：2026-09-05 施工骨架版（`plans/2026-09-04-research-loop-work-guide.md`）时，冻结三份没写的两处由统筹按 gyb 2026-09-04 的代裁授权定了，记在 `plans/2026-09-04-research-loop-proxy-decisions.md`；代码按代裁写，正文等最后一期，gyb 可逐条否。
- 裁决原文：（代裁，gyb 待审；依据写在 D-10、D-11 的理由栏）
- 要改的地方：
  48. 冻结后待议：（a）`03:145` feedback 行格式 `id` 一栏「反馈编号」补形状「形如 `fb-0001`」（D-11，照 `iss-0031` 类推）；（b）`04` handoffs 字段表 `work_order` 顶层 `track` 一栏（问题 45(a)(f) 加的）标「开单时必填」，转移表「（新建）→ todo」行 `work_order` 的前提加 `track`（D-10，依据 `04:43` 发射单第一次尝试 `track` 必填、`11:76` 发射单从父单抄）。
- 状态：等最后一期（代裁 2026-09-05，gyb 审 D-10、D-11 之后定）
