# 2026-09-05 research-loop 施工的多会话协议：一个统筹会话加四个 fork 出来的助手会话怎么分工、怎么用 git、怎么发消息

来历：2026-09-05 gyb 说要把统筹会话 fork 成几份当助手、互相发消息协作，统筹会话给出分工建议之后，gyb 直接用 `/fork` 开了四个助手。五个会话改的是同一棵 new1 工作树（new1 的 `.claude/settings.json` 把后台会话的 worktree 隔离关掉了），所以分工按目录切，谁也不合并谁的分支。施工的内容照 `plans/2026-09-04-research-loop-work-guide.md` 第五节的步骤和第七节的纪律，本文件只管五个会话之间的规矩。

## 一、五个会话各做什么、只写哪些路径

| 会话（ListAgents 里的名字） | 做哪几步 | 只写这些路径 | 等谁 |
|---|---|---|---|
| 统筹：`research-loop directory structure [37c253]` | 步 1 清空建树；步 A 对照单；30 分册的三处过时句；代裁记录、任务清单、收尾汇报 | `plans/` 下的所有文件、`MAP.md`、`research-loop/README.md`、`research-loop/.claude-plugin/plugin.json` | 不等人 |
| 底座：`research-loop directory structure ⑂ 你是底座 [06c460]` | 步 3a 表和 schema、步 3b 实现、步 4 交流机制 | `research-loop/` 下的 tables、schemas、scripts、bin、hooks、monitors、tests（`tests/test_skill_refs.py` 除外） | 转移表和受欠账影响的 schema 等统筹的对照单；身份判定的子会话分支等验证对待验证第 5 条的结论；别的先做 |
| 文本：`research-loop directory structure ⑂ 你是文本 [5b85b0]` | 步 5 母版底稿、步 6 五份 SKILL.md、五份 agent 定义、入口 skill、测试 13、压力场景 | `research-loop/` 下的 common、skills、agents、`tests/test_skill_refs.py` | 测试 13 和压力场景等底座落地；母版和说明书草稿不等 |
| 验证：`research-loop directory structure ⑂ 你是验证 [ef8a8d]` | 步 0 的待验证第 5、9 条；底座的钩子落地之后在真会话里触发一次 deny 和一次销号 | 沙盒放自己的临时目录；结果写新文件 `plans/2026-09-05-research-loop-verify.md` | 第一件事不等人；第二件事等底座步 4 的 commit |
| 评审：`research-loop directory structure ⑂ 你是评审 [ae6513]` | 盯底座、文本、验证、统筹的每个 commit（验证的 verify.md 查每条结论有没有实测记录撑着），查五样：只搬运不发明（每条逻辑指回分册号和行号）、冻结三份没动、待裁标记的格式、只 add 了自己的路径、检查器先于被检查物；回报发给作者和统筹 | 不写仓库里任何文件 | 等 commit 出现 |

插件本体（`research-loop/` 下一切）一律英文，来源标注写 `06 L178`，待裁标记写 `PENDING(issue 43c)` 或者 `PENDING(part 22 L113)`（代裁 D-09）。角色说明书里指向的角色 json 文件名固定为 `research-loop/tables/roles/<role>.json`，五个 role 是 idea、deploy、run、analysis、reviewer；子命令名以底座落地的 `bin/rl` 为准，文本会话看 git log 和文件，不发消息问内容。

## 二、git 五条，每个会话都守

1. 只 `git add` 自己路径下的文件，禁止 `git add -A`、`git commit -a`。别人的未提交文件当没看见，尤其是另一个会话现在还没提交的 `plans/STATUS_20260904_2149_kvshare-train.md`。
2. 一件事一个 commit，做完立刻提交，不留过夜的脏文件。施工的 commit 前缀 `research-loop v2:`，统筹改 `plans/` 的前缀 `research-loop plan:`。
3. 禁止 `git stash`，禁止对别人的文件 `checkout`、`reset`、`rm`。stash 会把别的会话正在改的东西一起收走。
4. 提交撞上 index.lock 就等几秒重试，不删锁文件。
5. 统筹先做完步 1 并提交，助手才开始往 `research-loop/` 写文件。

## 三、消息四条

1. 消息只传信号，内容走文件和 commit。汇报一条消息一件事，写清 commit 哈希、测试红绿数、还剩什么。每次 commit 之后把哈希发给评审和统筹各一份。
2. 助手碰到要裁的事发给统筹，不找 gyb。格式按「场景、问题、推荐」三段，等回信的时候先做不依赖的活。统筹按推荐做掉、记进 `plans/2026-09-04-research-loop-proxy-decisions.md` 的 D-NN，gyb 回来只看统筹这一个对话。
3. 发信被 auto 模式的分类器拦下的时候需要 gyb 放行一次（2026-08-28 出过一次）。收到「这个名字下是新会话」的提示先让对方确认一句上下文，不重新交代（2026-08-28 两次都是虚警）。
4. 子会话的模型按老规矩：实现用 sonnet，评审用 opus 或者 fable，fable 只用于评审。gyb 给统筹会话的「fable 当子会话」放行对复制出来的四个会话同样有效（统筹的假定，gyb 可以推翻）。

## 四、会话之间的依赖，谁给谁什么

- 统筹给底座：步 1 的 commit 哈希；步 A 的对照单文件路径。
- 验证给底座、统筹和评审：待验证第 5 条和第 9 条的结论（消息加 `plans/2026-09-05-research-loop-verify.md` 的 commit 哈希）。
- 底座给文本、验证、评审：步 3a、3b、4 各自的 commit 哈希。文本要 3a 的 json 文件名和 4 的子命令名，验证要 4 的钩子。
- 文本给评审、统筹：步 5、6 各自的 commit 哈希。
- 评审给作者和统筹：每个 commit 的回报。
