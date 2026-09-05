# 2026-09-05 research-loop v2 骨架版施工汇报：一天里五个会话并行把插件树全部落成文件，20 个测试文件在 HEAD 全绿，38 条代裁等 gyb 审

写给 gyb。这份汇报只写 2026-09-05 00:15 到 09:50 这一轮施工落了什么、测到什么、还有什么没做，事实在前、解读在后。文件位置：插件本体 `research-loop/`，代裁记录 `plans/2026-09-04-research-loop-proxy-decisions.md`，五会话协议 `plans/2026-09-05-research-loop-fork-protocol.md`，欠账对照单 `plans/2026-09-05-research-loop-debt-map.md`，验证记录 `plans/2026-09-05-research-loop-verify.md`，压力场景汇总 `plans/2026-09-05-research-loop-pressure-scenarios.md`。施工指南是 `plans/2026-09-04-research-loop-work-guide.md`。

下文里「骨架版」的口径按指南第一节：所有组件文件都在，已裁定的部分代码写完并且能写成用例的测试全绿，没裁定的地方在代码里标 `PENDING(...)` 指回问题编号或者分册条目，母版和说明书是草稿。「代裁」指统筹会话按 gyb 2026-09-04 的授权替 gyb 做的决定，每条记成 D-NN，gyb 逐条填审查栏。

## 一、落了什么，测到什么（事实）

插件树在 HEAD ba55ccc（底座最后一个 commit）有 109 个文件，工作树干净。按施工步分：

| 施工步 | 落地的 | 没落地的 |
|---|---|---|
| 步 1 清空建树 | 旧 0.1.0 退役，`plugin.json`、英文 README、空目录 | 无 |
| 步 3a 表与 schema | `tables/` 七张（账本清单、转移表、五份角色 json、gyb use case 表，另加命令表、退出码表、配置默认值表，D-12）；`schemas/` 九份，按 status 定必填 | 无 |
| 步 3b 实现 | `scripts/rl_lib.py`（锁、编号、追加、校验、actor 判定、转移表校验、退出码）加 `scripts/rl_cmds/` 十五组（session、feedback、eval、decision、issue、trace、handoff、run、ql、scratch、init、status、inbox、doctor、reclaim），`bin/rl` 分发 | D-37 的 `show --history`（八个 show 没加）；`rl init` 建宿主树是步 7 的桩子，只建了角色会话那道门 |
| 步 4 交流机制 | `hooks/hooks.json` 六个入口加 `hooks/rl_hook.py`（写权拦两类、子会话身份注入、登记、销号、PATH 导出） | `monitors/` 发射看门狗 |
| 步 5 母版 | `common/` 五文件底稿（英文），经评审十处修订 | gyb 逐条过 |
| 步 6 说明书 | 五份 `skills/<role>/SKILL.md`、五份 `agents/<role>.md`、入口 skill、`tests/test_skill_refs.py`（测试 13）、`tests/scenarios/` 十五份压力场景 | 六场压力场景没跑（见下） |
| 步 7、步 8 | 没做 | 沙盒最小一条路、new1 的 `rl init`、总验收 |

测试：`tests/run_all.py` 在 ba55ccc 上 20 个文件全绿，共 250 例跑、0 失败、0 错误、9 跳过（跳过的是 grants 三例 D-01、22 L115 一例、问题 41(f) 两例、问题 50 一例等）。测试 13 单跑红 1 处：reviewer 说明书引了 `rl run show RUN_ID --history`，D-37 的旗子还没进命令表。

验证（步 0 加步 4 真会话那一半，`plans/2026-09-05-research-loop-verify.md` 五版，最后一版 86b2e23 之后由验证助手报哈希）：待验证第 5 条测完（SubagentStart、SubagentStop 触发并带 agent_id、agent_type，session_id 与母会话相同，SessionEnd 子会话结束不触发，rl 按状态文件读到母会话角色，updatedInput 注入通、环境文件不通）；第 9 条测完（母会话活着时后台子会话跑满 1200 秒回通知，三种结束方式子会话都被杀，打印模式默认只等 600 秒）；顺带第 1、10 条有结果；三条补充项（skills 预载两种拼法都通、带 disable-model-invocation 的 skill 预载不上、SessionStart 写 CLAUDE_ENV_FILE 让 rl 进 PATH 四次都通）；步 4 真会话验收（注册 1 秒内状态文件、4 秒内 sessions 账 open 版；deny 三种都拒且回话三样齐；`/exit` 之后 SessionEnd 与 closed 版同一秒落账；default 模式下子会话每条改写后的 Bash 弹审批框，auto 模式分类器全程放行）。30 分册待验证清单第 1、5、9、10 条状态栏已改成已测。验证的原始记录（钩子日志、会话记录，3.9M）从验证助手的 job 临时目录拷到了 `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/plans-raw/2026-09-05-research-loop-verify0/`；压力场景的原始对话记录在文本助手的 job 临时目录里，没有拷。

压力场景（`plans/2026-09-05-research-loop-pressure-scenarios.md`）：九场不带 skill 的对照臂（opus）里五场本来合规、三场违规（idea 验收通读代码、reviewer 读序反了没记 focus、deploy 超参一行决定没写且把 gyb 在场的话转给 idea）、一场步骤不全（deploy 修 smoke 没 amend 新尝试）；带 skill 的臂跑了两场（deploy 超参、reviewer 读序），对照臂违规的地方带 skill 之后都照做，还把 `research-loop:run` 子会话派通了、账上看到了 D-15 的 agent_id；idea 验收那场带 skill 的臂启动命令被 auto 模式分类器拦下没起；六场没跑。

记录与账：今天的 commit 按前缀数是 `research-loop v2:` 89 个、`research-loop plan:` 40 个、`research-loop sync:` 12 个（rl-hub-v6 的分册账同步）。代裁 D-01 到 D-38 全部在记录文件里，每条有问题、决定、理由、落点、空着的审查栏。sync-inbox 追了问题 48(a) 到 (k)、49(a) 到 (e)、41(k)、50(a)(b)、51，前三组是施工期代裁动到冻结三份的落点，50 和 51 是等 gyb 的。插件树里 `PENDING(` 标记 62 个不同、128 处出现（底座清点，HEAD ba55ccc），全部是 D-09 的两种形式；最多的是 `PENDING(issue 43c)`（grants 账留位）、`PENDING(issue 41f)`（转进单出口子命令名）、20 到 25 六份没开定稿的七处 schema 条目、`PENDING(issue 50)`（run 的 issues 写权）。

## 二、等你裁的（事实）

1. 代裁记录 D-01 到 D-38 逐条填审查栏。要紧的几条：D-09 插件本体一律英文；D-15 子会话身份（rl 先看钩子注入的 RL_AGENT_TYPE、RL_AGENT_ID，骨架加可选栏 agent_id，子会话在 sessions 账另落一行，SubagentStop 和 SessionEnd 各自交回）；D-21 rl 进 PATH 走 SessionStart 写 CLAUDE_ENV_FILE；D-22 batch start 整批接下；D-24 快车道补单 actor deploy、from_role gyb；D-31 命令不变也算新尝试；D-32 done 收交付物路径。
2. 注入身份之后的权限流程（D-15 补记）：default 模式下子会话每条 Bash 弹审批框、「don't ask again」绑 agent_id 无用；auto 模式全程放行。new1 现在是 auto 模式，现状能用。两条路给你选：宿主另写 `Bash(export RL_AGENT_TYPE=*)` 一类规则（等于放行子会话在仓库里的全部 Bash），或者评审提的备选「钩子只改写命令里的 rl 调用、把身份当参数传」（前缀规则照样命中，代价是脚本内部再调 rl 拿不到身份）。
3. sync-inbox 等 gyb 的四题：43(c) grants 账存废（今天留位不建立，D-01）；46 派活开场话推广（今天按 D-02 推广到所有通道）；50 run 的 issues 写权要不要加 reply、close、link（45(b) 和 doctor 第 3 项两处都卡在这里）；51 账上要不要记写 commit 的会话（REVIEW-CHECKLIST 的 D2 卡在这里）。
4. 对照臂里 idea 和 reviewer 用的是 opus，角色 json 定的是 fable，要不要按 fable 重跑。
5. idea 验收那场带 skill 的臂：文本助手的启动命令被 auto 模式分类器拦下，需要你放行一次才能起。
6. 30 分册待验证清单第 3、4、11 条还没测；步 7（沙盒最小一条路、new1 的 `rl init`、宿主 CLAUDE.md 两处手改、`run.py` 门禁白名单）和步 8（总验收）没做。
7. 母版 `common/` 五文件按 30 步 5 的验收要你逐条过。

## 三、解读与下一步

事实到此为止，下面是我的解读。

五会话并行这个做法今天成立了：按目录切人、只 add 自己的路径、做完立刻提交，五个会话改同一棵树一天 141 个 commit 没有一次撞车；评审会话从头到尾盯每个 commit，报出的要改项在两位数以上，其中真洞（session start 被自己的 closed 校验挡死、reclaim 收窄、注入带 allow 等于替人批准、SessionEnd 1.5 秒预算、holder 分不开两个子会话）都是代码落地之前被它抓住的。代裁记录这条路也走通了：38 条里没有一条是我凭空定的，每条都指回分册行号或者实测记录，gyb 可以逐条否。

代价有三处。一是 opus 的会话额度在 01:07 把底座的实现者打死，底座会话跟着停到 08:08 我发消息才动，中间七个小时没有人发现，原因是四个助手和统筹都在等对方的消息、没有人定时看；今天 08:08 之后我挂了每半小时一次的进度检查，下一次从开工就挂。二是会话重启之后旧地址失效（文本、底座、验证各一次），发消息要重新用 ListAgents 找名字。三是压力场景只跑了一轮里的一半，六场没跑、带 skill 的臂只有两场，说明书「照不照做」的证据还薄。

下一轮的活按顺序：（1）底座清单里的十条（D-37 的 `--history`、D-36 的测试、doctor 末段指 REVIEW-CHECKLIST、doctor 第 5 项修法、reclaim 计时的测试、`--flag=value` 布尔旗子、reclaim 和 doctor 的重复助手并进 rl_lib、拒绝回话列可用命令、status --json 容器形状、测试 13 按子命令核旗子已由文本做掉）；（2）`monitors/` 看门狗；（3）压力场景补六场、三场违规的带 skill 臂补齐，按结果改说明书，五场不区分的场景换压力形态；（4）等你审完 D-01 到 D-38 和四道题，再走步 7（沙盒最小一条路、new1 `rl init`）和步 8（总验收）。
