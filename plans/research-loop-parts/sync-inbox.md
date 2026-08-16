# sync-inbox：part session 报给统筹 session 的事项（格式见 HANDOFF 第三节；统筹处理完把状态改成已处理）

## 2026-08-16 夜 来自 统筹 session（总session）关于 HANDOFF.md 四点五节
- 事项：首次核对关联表时发现三样东西各 part 指的定义处不一致，原表没说死。一次问一个，gyb 裁了再往各 part 传。
- 问题 1：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩，定义处归 `01-gyb.md`（gyb 身份规矩）、`05-rl-cli.md`（命令签名）、`06-hooks-and-permissions.md`（钩子）三处各占一段，还是只归一处？现在 `02`、`10` 指 `01`，`03`、`06` 指 `05`，`04`、`14`、`22` 指 `01` 和 `06`。——已裁 2026-08-17：归 `01`，原话「这个归01吧」。已处理：`01` 第二节补 `--force` 拒收那句并记裁决；`03`/`06`/`14`/`22` 指向改成 `01`；HANDOFF 四点五节改；两份源文档补那句；`04` 已改（rl-part-04，`2c42b92`）；`05` 交 rl-part-05。
- 问题 2：推送表（哪些事件推桌面通知）和 `rl notify` 是一件事还是两件事？原表把推送表归 `01`、notify 归 `05`；`07`、`10`、`11`、`20`、`25` 指 `01`，`09`、`22`、`23`、`24` 指 `05`。——已裁 2026-08-17：一件事，归 `01`，原话「算一件事」「给rl notify指到01吧」。已处理：`01` 第五节补一句并记裁决；`09`/`22`/`23`/`24` 指向改 `01`；HANDOFF 四点五节改；`05`「rl notify」一节缩成一句指 `01`、命令表只留签名行，rl-part-05 已改 `f283974`（`05` 那节里 `01` 没有的句子由 rl-part-05 定稿时报上来再搬进 `01`）。
- 问题 3：阈值表定义处按原表是 `08-trees-init-and-host.md`，但 `04`、`14`、`21`、`23`、`05`、`24` 六份各指了别处（见 HANDOFF 四点五节 `08` 那一行）。是照 `08` 传，还是阈值表另立一处？——已裁 2026-08-17：照 `08`，原话「按照08吧」。已处理：`14`/`21`/`23`/`24` 指向改 `08` 第三节；`04` 已指 `08`；`05` 交 rl-part-05；HANDOFF 改。
- 问题 4（2026-08-17 加，来自 03 事项 6）：runs 发射版去掉 `artifact_dir` 之后，「产物目录是 `<artifact_root>/<run_id>/`」这条约定的定义处归 `08-trees-init-and-host.md`（`artifact_root` 在它那）还是 `12-role-run.md`（run 的产物）？现在 03、12、21、23 和两份源文档都写了这一句，等裁了再定谁是那一处。——已裁 2026-08-17：归 `08`，原话「问题4 给8」。已处理：`08` 第一节写成定义处并记裁决；`03`/`12`/`21`/`23` 那句加「约定定义在 08 第一节」；HANDOFF 记。
- 问题 5（2026-08-17 加，来自 04 事项 3）：04 定稿带出一条新的入账校验「`session_id` 对应的 sessions 账最新版是 `closed` 的会话再写任何账，rl 拒收并提示重新加载角色登记」。定义处按 HANDOFF 判断规矩 3 找不到：入账校验在 `03-ledgers.md`，命令在 `05-rl-cli.md`，事情本身写在 `04-handoffs-and-sessions.md` 第七节 `rl session end` 那条。归哪一份？——已裁 2026-08-17：归 `03`，原话「问题5 给3」。已处理：`03`「账本的总规矩」加一段并记裁决；`04` 第七节那句加指向交 rl-part-04；HANDOFF 记。
- 问题 6（2026-08-17 加，来自 05 事项 8）：05 定稿裁「reviewer 按 `common/` 问题清单派 sonnet subagent 逐题查，查出的 `rl issue open --to <owner>` 落账」，可 `14-role-reviewer.md` 第八节和公共规矩第 6 条写的是「reviewer 不开 issue、不派活，卡住也只写进清单交给 gyb」，角色 json 的 `ledger_writes` 也没有 issues。两处不一致：reviewer 查出的问题是开 issue 落账（第八节和 json 跟着改），还是照旧只写进清单交 gyb？——已裁 2026-08-17（待落地，gyb 要求 6–29 全收齐再一起改）：A，照旧只写清单，gyb 用自己的权限开 issue，原话「全给我审查，然后我用我的权限放到issue里面」。
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
  7. `rl handoff estimate` 往 `attempts.step_table` 写东西，`04` 转移表没它的行，`04:77` 又说改单子内容一律是表里的行。给 estimate 加一行，还是那句把 estimate 排除？——已裁 2026-08-17（待落地）：A，转移表加 `in_progress`→`in_progress` 内容追加行（holder 填分步表），原话「冒烟也是正式动作」。
  8. 快车道补单写序是环：`03:208` scratch 的 `merged` 版必填 `handoff_id`（补单先存在），`04:60` 开补单前提「关联的 scratch 行状态是 merged」（merged 先存在）；`05:64` `open --quick-lane --ql QL` 收 ql_tag，`04` handoffs 字段表没有存它的字段。哪个先写、单子上存不存 ql_tag？——已裁 2026-08-17（待落地）：A，先开补单（前提改成关联 scratch 行状态是 `open`），拿到编号再 `ql close --merged --handoff ID`；handoffs 加一栏存 `ql_tag`，两边互指。原话「A」。
  9. `batch` 谁分配：`03:19` 说 rl 在锁里分，`04:26`/`05:64` 是调用者 `--batch B` 传的可选字段；`05:64` 说 launch_order 开单从父单抄 batch，`04` 字段表只写「可选」；batch 也没有格式。——已裁 2026-08-17（待落地）：A，调用者自由文本、可选，rl 不分配（03 锁那句去掉 `batch`）；launch_order 从父单抄的规矩照旧。原话「A」。
  10. amend 能改哪些字段：doctor 第 2 项用 `amend --decision ID@V` 换悬空引用，`04` 两行 amend 都不许改 decision_refs、`05` amend 签名也没 `--decision`；doctor 第 5 项修法带 `--code-path`，`04:66`（等验收态 amend）只许补 report_paths/output_paths。——已裁 2026-08-17（待落地）：A，转移表放宽跟修法走：两行 amend 都允许换 `decision_refs`/`evaluation_refs`（05 签名加 `--decision ID@V`）；`done_pending_review` 行 amend 允许改 `code_paths`。原话「A」。
  11. issue 追问：doctor 第 11 项让开 issue 的角色 `rl issue reply` 追问、issue 回到 open；`03:92` 说 reply 只有 assignee 或 gyb 能写、`03:74` reply 字段挂在 answered 版。要不要追问这条路、怎么写？——已裁 2026-08-17（待落地）：B，不加追问；一条 issue 一问一答，回答不管用就 close 再开一条新的引旧编号；doctor 第 11 项修法那半句改掉。原话「B」。
  12. `run list` 默认口径：`03:124`「每张单最新一次退出状态为 ok 的行」vs `05:73`「最新尝试且 ok」——最新一跑失败时一个列上一条 ok、一个一条不出。——已裁 2026-08-17（待落地）：B，只看最新一次尝试且 ok，失败不出；03:124 改成 05 的写法。原话「B」。
  13. 「handoffs 上的 actual_seconds」：`03:118`、`04:41` 都这么写，`04` handoffs 字段表没这一栏。handoffs 记不记（从 runs 抄一份）还是不记、看去 runs？——已裁 2026-08-17（待落地）：B，handoffs 字段表加 `actual_seconds`（在 `attempts` 那一次尝试上），`rl run finish` 时 rl 自动从 runs 抄、人不填；预计和实际同一张单对着看。原话「B」。
  14. closed 会话再写账拒收（`03:15`）没给退出码：2（校验拒收）还是 3（无权）？gyb 能不能 `--force` 越过它？——已裁 2026-08-17（待落地）：A，退出码 3，`--force`/`--as-gyb --force` 都越不过，唯一出路是重新加载角色。原话「A」。
  15. `fix_for` 填什么：`03:43` 说 doctor 修法命令一律带 `--fix-for <扫描项名字>`，`05` doctor 表只有序号没名字、十九条修法命令一条没带 `--fix-for`、`--ack ITEM ID` 也按项号。填项号？命令带不带 `--fix-for`？——已裁 2026-08-17（待落地）：B，`fix_for` 栏删掉，公共骨架可选栏只剩 `force_reason`、`via`；修法命令不带 `--fix-for`；03 事项 5 那句「七样加两个可选」相应改。原话「B」。
  16. `04:9` 快车道补单是 deploy 开给 deploy，`05:87` 有 `ql open --role analysis`。analysis 的快车道有没有补单？（可能归 `07`，先记着。）——已裁 2026-08-17（待落地）：A，没有补单；analysis 快车道只能 `--dropped`，要留就走正常路重做；`ql close --merged` 只对 deploy 开；07「没写清」第 5 条据此销。原话「A」。
  17. `adopted`：`04:61`、`04:95` 认领时「账行标 adopted」，handoffs 和 runs 字段表都没这一栏。哪本账的字段？——已裁 2026-08-17（待落地）：C，两边都标：handoffs 的 `start` 那一版加 `adopted: true`；runs 加一版 `adopted`（记新 holder 会话与 ts）。原话「C」。
  18. sessions `amend` 版和「校验按 status 查」（`03:13`）没接上：amend 行填哪个 status、要不要跟着填该 status 的必填项、能不能 amend 已 closed 的会话（doctor 第 19 项抓的往往是关掉的）。——已裁 2026-08-17（待落地）：A，amend 版 `status` 与其他栏照抄最新版、只换 `model`；closed 会话也能 amend（写者是 gyb 裸终端或该角色的活会话，不触问题 14 那条）。原话「A」。
  19. `04:69` 给 reclaim 写 `rejected`→`todo` 的权，`04` 第八节四类处置没有 rejected 这一类（等验收和待干只列不动）。reclaim 动不动 rejected 的单？——已裁 2026-08-17（待落地）：B，reclaim `--apply` 把超阈值的 `rejected` 单推回 `todo`（actor gyb、`via=reclaim`），04 第八节四类处置加成五类，转移表那行照旧。原话「B」。
  20. `04:71` withdraw 行「有 holder 时通知 holder」——按不变量只有 in_progress 有 holder，从 todo/stuck/等验收/rejected 收回时通知没人收。用 `last_holder`？——已裁 2026-08-17（待落地）：B，照字面，只在 `in_progress` 收回时通知 holder；其他状态不通知；04:71 那句改成「从 `in_progress` 收回时……」。原话「B」。
  21. `04:73` reissue 行「到＝同状态（接替）」，动作却是旧单 withdrawn、新开一张。「到」栏怎么写？——已裁 2026-08-17（待落地）：A，新单一律从 `todo` 起、同新建拉起；表里写实：旧单→`withdrawn`，新单→`todo`（`supersedes` 指旧单）。原话「A」。
  22. `03:104` runs 主键说「快车道用 ql_tag」，`03:213` 又说快车道数字不进 runs——同一份里两句。HANDOFF 原留给 07/23 裁；03 已定稿，gyb 直接定？——已裁 2026-08-17（待落地）：A，不进 runs；03:104 删「快车道用 `ql_tag`」；07/23 引用处同改。原话「A」。
  23. `rl inbox` 读过即关通知 issue、`rl doctor --ack` 写 ack 文件，`05:100` 却把它俩列进「查询命令、不进 ledger_writes」。「查询顺带自动写」怎么定性？——已裁 2026-08-17（待落地）：B 的方向：`rl inbox` 只读不关，通知类 issue 由收件人做完了自己 `rl issue close`（issues 写权 close 那条补「通知类 issue 的 assignee 也能关」）；`rl doctor --ack/--unack` 算写命令、只有 gyb 能敲。原话「只有做完了的时候才关，巡检要我本人确认」。
  24. `loop/.doctor-acks.jsonl` 不算九本账（`05:212`）：03 总规矩（只增不改、锁、进 git、脏树白名单）管不管它、谁能 ack？——已裁 2026-08-17（待落地）：B，`.doctor-acks.jsonl` 是普通文件，03 总规矩不管它；谁能 ack 按问题 23：只有 gyb。原话「B」。
  25. 退出码只有 0/2/3/4：查不到编号、内部错误、参数写错落哪个码？——已裁 2026-08-17（待落地）：要求是 agent 分得出发生了什么。落法：加退出码 5「用法错」（参数写错、编号不存在），内部错误 1；所有非零退出标准错误第一行固定格式给原因种类（`--json` 时 `error.kind`），四码变六码（0/1/2/3/4/5），定义处 03、05 照抄。原话「我想让agent有办法识别发生了什么就行」。
  26. doctor 第 17 项要 applied_to 同时含母版和文档，`03:152`「母版和文档都算」（有一样就行）。哪个？——已裁 2026-08-17（待落地）：B，至少一个即可，doctor 第 17 项改成「applied_to 为空」才报。原话「我觉得。有一些改的方法，不一定会改公共规矩，如果是这样的话就选b。」
  27. `05:27` 说施工计划（b）（c）（d）三条（豁免收窄加 --force --reason、--as-gyb 一律 --quote、grants 只收裸终端）gyb 还没逐条裁，05 的 actor 一节和 01 第二节都建在它们上面。认不认？认了销这句、施工计划第一节那三条标日期。——已裁 2026-08-17（待落地）：(b)(c) 认；(d) 不认——grants 可以在角色会话里 `--as-gyb --quote` 替 gyb 写、不限裸终端。改：01 第二节、05 actor 一节、设计文档原则 1 末句「授权（grants）只收裸终端写的行」、施工计划第一节 (d)、`decisions.gyb.jsonl` 只收裸终端那条不受影响。原话「3 不是，可以替我写」。
  28. （待 gyb 过目，rl-part-05 定，`c2f69c8`）「run 的 inbox 不查过版」这条例外删掉，run 的 inbox 第 3 项照查过版决定（发射单从父单继承 decision_refs）。——2026-08-17 gyb 改了上位规矩（待落地）：角色会话被拉起时不自动查收件箱，先干拉它起来的那张单；「所有角色上线第一个动作是 `rl inbox`」这句作废（10–14 各份、01、12:19、两份源文档原则 6 补的「上线第一动作」都要改）。原话「每个角色创建时候，不要自动查收件箱。比如说idea层创建了一个新的idea，他要发给部署层，那么就创建一个新的部署层的角色，这个角色就应该先执行刚才idea给他的工作。」收件箱什么时候看：C，都不自动看，`rl inbox` 是谁需要谁敲的查询命令，gyb 要它看就说一声；SKILL.md 里不再写「上线先 inbox」。原话「C」。问题 28 本身：gyb 又裁（2026-08-17 晨）run 不查 inbox——run 只关注自己那张发射单，一般不会有没带单子的 run 会话；rl-part-05 在 `c2f69c8` 删掉的「run 的 inbox 例外」要改回并扩大成「run 不查 inbox」，`12:19` 同改。原话「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」。
  29. （待 gyb 过目，rl-part-05 定，`c2f69c8`）`rl status --json` 的 `holder_alive` = holder 会话在 sessions 账最新版是否 `open`；`age_hours` 从单子当前状态那一版的 `ts` 起算。——已过目 2026-08-17：认。原话「A」。
- 甲的回报：rl-part-04 八条已改 `bc9bc90`；rl-part-05 十六条已改 `c2f69c8`（第 13 条第 27 行等问题 27）。
- 裁决原文：（待）
- 要改的地方：每条裁了按定义处改，再传引用处；04 的交 rl-part-04、05 的交 rl-part-05、03 的统筹直接改；两份源文档对应句子回写。
- 状态：7–29 已全部裁（2026-08-17，rl-hub-v2 逐条问的），待落地；甲已全部落地

## 2026-08-17 晨 来自 rl-hub-v2 关于 04/05 收问题 6–29 的裁决
- 事项：gyb 说「你现在就交给04和05让他们改了」。rl-hub-v2 已 SendMessage 打包发出：04 十一条（问题 7/8/9/10/13/14/17/18/19/20/21 加问题 28 的 inbox 措辞），05 十九条（问题 6/7/8/9/10/11/12/14/15/16/17/18/23/24/25/26/27/28/29）。每条附裁决原话与改法，消息全文在 rl-hub-v2 会话记录，要点与落点在 HANDOFF 第八节的表。
- 统筹拟的措辞（问题 25，等 03 定义处照抄）：退出码 1 内部错误、5 用法错；所有非零退出标准错误第一行固定原因种类 2 validation / 3 forbidden / 4 lock_timeout / 5 usage / 1 internal，`--json` 时放 `error.kind`。rl-part-05 若改措辞会报回来，03 要跟它一字不差。
- 要改的地方：等两个 session 回「收 N–M，commit <hash>」，统筹记进 README 进度表与本段；03 与其余各份、两份源文档仍按 HANDOFF 第八节清单由统筹落。
- 状态：待处理（等 rl-part-04、rl-part-05 回 commit）
