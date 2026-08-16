# sync-inbox：part session 报给统筹 session 的事项（格式见 HANDOFF 第三节；统筹处理完把状态改成已处理）

## 2026-08-16 夜 来自 统筹 session（总session）关于 HANDOFF.md 四点五节
- 事项：首次核对关联表时发现三样东西各 part 指的定义处不一致，原表没说死。一次问一个，gyb 裁了再往各 part 传。
- 问题 1：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩，定义处归 `01-gyb.md`（gyb 身份规矩）、`05-rl-cli.md`（命令签名）、`06-hooks-and-permissions.md`（钩子）三处各占一段，还是只归一处？现在 `02`、`10` 指 `01`，`03`、`06` 指 `05`，`04`、`14`、`22` 指 `01` 和 `06`。
- 问题 2：推送表（哪些事件推桌面通知）和 `rl notify` 是一件事还是两件事？原表把推送表归 `01`、notify 归 `05`；`07`、`10`、`11`、`20`、`25` 指 `01`，`09`、`22`、`23`、`24` 指 `05`。
- 问题 3：阈值表定义处按原表是 `08-trees-init-and-host.md`，但 `04`、`14`、`21`、`23`、`05`、`24` 六份各指了别处（见 HANDOFF 四点五节 `08` 那一行）。是照 `08` 传，还是阈值表另立一处？
- 问题 4（2026-08-17 加，来自 03 事项 6）：runs 发射版去掉 `artifact_dir` 之后，「产物目录是 `<artifact_root>/<run_id>/`」这条约定的定义处归 `08-trees-init-and-host.md`（`artifact_root` 在它那）还是 `12-role-run.md`（run 的产物）？现在 03、12、21、23 和两份源文档都写了这一句，等裁了再定谁是那一处。
- 问题 5（2026-08-17 加，来自 04 事项 3）：04 定稿带出一条新的入账校验「`session_id` 对应的 sessions 账最新版是 `closed` 的会话再写任何账，rl 拒收并提示重新加载角色登记」。定义处按 HANDOFF 判断规矩 3 找不到：入账校验在 `03-ledgers.md`，命令在 `05-rl-cli.md`，事情本身写在 `04-handoffs-and-sessions.md` 第七节 `rl session end` 那条。归哪一份？
- 问题 1 附带（2026-08-17 加，来自 03 事项 3）：「角色带 `--force` 一律拒收，退出码 3；`--as-gyb --quote --force --reason` 算 gyb 身份照写」这一句，等问题 1 裁了定义处之后写进那一份。
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
- 状态：已处理 2026-08-17（1、2、4、5 里的 `20`/`21`/`22`/`01` 与两份源文档由统筹改，源文档「接单」「会话生命周期」两段和施工计划第三节、第四节表一并回写；`05-rl-cli.md` 第 170 行在 rl-part-05 手上，已 SendMessage 交代；事项 3 立为第一段问题 5 等 gyb；04 文末「要同步到别处的」标已同步交 rl-part-04 自己做）
