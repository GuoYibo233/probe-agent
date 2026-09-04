# 2026-09-05 待验证第 5 条、第 9 条和三条补充项的实测记录（施工步 0，验证助手会话）

写给 gyb、统筹会话、底座会话和评审会话。这份记录只装 2026-09-05 凌晨在真会话沙盒里测出来的事实，加上末尾一节单独写的解读和建议。测的是 30 分册待验证清单的第 5 条（子会话结束的时候 SessionEnd 和 SubagentStop 触不触发、会话 id 是不是同一个、子会话里敲 rl 算谁）和第 9 条（后台子会话在母会话活着的时候能不能长跑并回通知、母会话结束的时候后台子会话会不会被杀掉），另加统筹 2026-09-05 转来的三条补充项（agents 定义的 skills 字段写裸名还是带插件前缀才预载得上；带 disable-model-invocation 的 skill 能不能被预载；插件级钩子把插件的 bin 目录写进 PATH 之后能不能直接敲 rl）。顺带测到的第 1 条和第 10 条只记结果，不算正式裁决。第七节是同一天上午做的施工步 4 真会话验收（写权 deny、注册、销号、注入之后的权限流程），用的是底座落地的插件级钩子。

几个下文反复用的词。子会话：一个会话用 Agent 工具启动出来的下级会话，Claude Code 官方叫 subagent。钩子：Claude Code 在会话开始、结束、工具调用前后自动运行的脚本，钩子收到的输入是一段 JSON。状态文件：设计里由登记钩子写在 `loop/.sessions/<session_id>.json` 的那份小文件，rl 靠状态文件判断当前会话是什么角色。心跳文件：沙盒里长跑脚本每 10 秒追加一行时间戳的文件，用来判断脚本什么时候还活着。打印模式：`claude -p` 这种给一句话、跑完就退出的会话。

本机版本：Claude Code 2.1.260。沙盒里所有会话和子会话的模型都是 sonnet。沙盒目录 `/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/`（验证助手会话的临时目录，下文写作沙盒目录），原始记录全在沙盒目录里，路径在第六节。

## 一、沙盒和测法

沙盒目录里放了这几样东西：

| 文件 | 作用 |
|---|---|
| `settings.json` | 用 `--settings` 传进会话的设置：五个钩子（SessionStart、SessionEnd、SubagentStart、SubagentStop、PreToolUse 只匹配 Bash）都指向记录脚本；另外把 Bash 工具的默认超时设成 3600000 毫秒、上限设成 7200000 毫秒 |
| `hooks/hooklog.py` | 记录脚本：每次钩子触发追加一行 JSON 到 `hooklog.jsonl`，内容是事件名、时间、钩子进程看到的所有 CLAUDE 开头的环境变量、钩子输入 JSON 原文；SessionStart 收到的输入里没有 agent_type 的时候，按 06 第 118 行的登记写状态文件，角色固定写 deploy |
| `settings5b.json`、`hooks/envexport.py`、`hooks/inject.py` | 第 5 条第二轮用的设置：SubagentStart 换成 envexport.py（多做一件事：钩子进程有 CLAUDE_ENV_FILE 的话往里追加两行 export）；PreToolUse 换成 inject.py（多做一件事：输入里 agent_type 非空的时候用 updatedInput 把 `RL_HOOK_AGENT_TYPE=<agent_type> RL_HOOK_AGENT_ID=<agent_id>` 加在 Bash 命令前面） |
| `settings5c.json`、`hooks/inject2.py` | 链式命令补测用的设置：PreToolUse 换成 inject2.py，改写成 D-15 的 export 形式 |
| `agents.json` | 用 `--agents` 传进会话的两个 agent 类型 deploy 和 run，代替还没写的 `agents/<role>.md`：只有提示词和 model，没有 tools 字段 |
| `bin/rl` | 代替还没写的 rl，只有 `whoami` 一个子命令：打印并记录 Bash 里看到的 CLAUDE 和 RL 开头的环境变量、进程链、按环境变量里的会话 id 去找状态文件找到没有、读到的角色 |
| `bin/longjob.sh <秒数> <名字>` | 长跑脚本，每 10 秒往 `hb/<名字>.log` 追加一行心跳 |
| `bin/mark.sh` | 往 `marks.log` 追加一行时间戳，母会话收到子会话完成通知的时候调用 |
| `run_p.sh`、`run_9b.sh`、`run_9b_bg.sh`、`watch9a.sh` | 起打印模式会话、起 tmux 交互会话并结束母会话、盯长跑的脚本 |
| `plugtest/rlmini/` | 补充三条用的最小插件：两个 skill（idea 普通、gate 带 `disable-model-invocation: true`），四个 agent 定义（skills 字段分别写 `idea`、`rlmini:idea`、`gate`、`rlmini:gate`），一条插件级 SessionStart 钩子（`hooks/hooks.json` 加 `hooks/pathexport.py`）和一个只打印一行的 `bin/rl` |

钩子挂在设置这一层，不挂在插件这一层，依据是 06 第 102 行记的第 8 条实测结论：「仓库 settings 级和插件级钩子文件对 subagent 生效，输入带 `agent_type`、`agent_id`，`session_id` 与父会话相同」。这次的记录再次看到了同样的三个字段。

这次没测的：几个小时的长跑（原计划 40 分钟那次在 740 秒被中断，见 3.5，重跑缩成 1200 秒）、真正的 rl（还没写）、`launched_by=workflow` 的派活、沙盒不是 git 仓库。另外一处只在一种形状上测过：2.4 里 rl 读到的状态文件是沙盒的 SessionStart 钩子写的，真正的登记钩子还没写。注入对插件 `agents/<role>.md` 定义的子会话类型也补测过一次（2.5 末尾，08:26 那次）。退出对话框的第三个选项「Stay」没有选过。

## 二、第 5 条的实测事实

第 5 条跑了两轮打印模式会话。第一轮 t5a（会话 id `c5b97463…`）：母会话先运行一次 `bin/rl whoami --tag parent`，再在同一个回复里并发启动 deploy 和 run 两个子会话，各运行一次 `bin/rl whoami`，等两个都完成再运行 `bin/mark.sh`。第二轮 t5b（会话 id `08ac1df2…`）同样的流程，换成 settings5b.json 的两个信号钩子。

### 2.1 SubagentStart 和 SubagentStop 都触发，输入带 agent_id 和 agent_type

t5a 里 deploy 子会话的两条钩子记录原文（去掉了 transcript_path 和 cwd 两个字段，last_assistant_message 是子会话的最后一句话，太长省略）：

```
[SubagentStart 2026-09-05T00:21:31] {"session_id": "c5b97463-e7aa-407d-877b-d098480949b4", "prompt_id": "3623aaf2-fec3-46bb-8789-24a69fdd2782", "agent_id": "a6cb44d31c99e9184", "agent_type": "deploy", "hook_event_name": "SubagentStart"}
[SubagentStop 2026-09-05T00:21:46] {"session_id": "c5b97463-e7aa-407d-877b-d098480949b4", "prompt_id": "3623aaf2-fec3-46bb-8789-24a69fdd2782", "permission_mode": "acceptEdits", "agent_id": "a6cb44d31c99e9184", "agent_type": "deploy", "effort": {"level": "xhigh"}, "hook_event_name": "SubagentStop", "stop_hook_active": false, "agent_transcript_path": "…/agent-a6cb44d31c99e9184.jsonl", "last_assistant_message": "…", "background_tasks": []}
```

run 子会话同样两条：SubagentStart 00:21:32 `agent_id` 是 `aa1222987d84e8e00`、`agent_type` 是 `run`；SubagentStop 00:21:49 同一个 agent_id。agent_type 的值就是 `--agents` 里给的类型名，不是 general-purpose。SubagentStop 的输入比 SubagentStart 多五个字段：permission_mode、effort、stop_hook_active、agent_transcript_path（子会话自己的记录文件）、last_assistant_message、background_tasks。

### 2.2 会话 id 是同一个

t5a 的 SessionStart、两条 SubagentStart、两条 SubagentStop、子会话里的 PreToolUse、SessionEnd，`session_id` 全部是 `c5b97463-e7aa-407d-877b-d098480949b4`。子会话和母会话在钩子眼里是同一个会话 id，区分子会话靠 agent_id。

### 2.3 SessionEnd 在子会话结束的时候不触发，整个会话只触发一次

t5a 的钩子顺序：SubagentStop 00:21:46（deploy）、SubagentStop 00:21:49（run）、母会话 PreToolUse 00:21:51（mark.sh）、SessionEnd 00:21:54。SessionEnd 原文：

```
[SessionEnd 2026-09-05T00:21:54] {"session_id": "c5b97463-e7aa-407d-877b-d098480949b4", "prompt_id": "3623aaf2-fec3-46bb-8789-24a69fdd2782", "hook_event_name": "SessionEnd", "reason": "other"}
```

第 9 条的五个会话里 SessionEnd 同样每个会话只有一条（第三节的表）。

### 2.4 子会话里的 Bash 环境和母会话完全一样，按状态文件读到的是母会话的角色

t5a 里三次 `bin/rl whoami` 看到的环境变量键完全相同，都是这 12 个：CLAUDECODE、CLAUDE_CODE_AGENT、CLAUDE_CODE_BRIDGE_SESSION_ID、CLAUDE_CODE_CHILD_SESSION、CLAUDE_CODE_ENTRYPOINT、CLAUDE_CODE_EXECPATH、CLAUDE_CODE_MESSAGING_SOCKET、CLAUDE_CODE_MESSAGING_TOKEN、CLAUDE_CODE_SESSION_ID、CLAUDE_EFFORT、CLAUDE_JOB_DIR、CLAUDE_PID。三次的值也相同：CLAUDE_CODE_SESSION_ID 都是母会话的 `c5b97463…`，CLAUDE_CODE_AGENT 都是 `claude`，CLAUDE_PID 都是母会话进程 3193366。进程链上子会话的 Bash 直接挂在母会话的 claude 进程下面（`bash bin/rl` 的父进程是 `/bin/bash -c source …`，再上面就是 `claude -p …` 进程 3193366），没有子会话自己的进程。

deploy 子会话那次的 rl 记录原文（去掉了进程链后半段和环境变量的值）：

```
{"cmd": "whoami", "tag": "child-deploy", "ts": "2026-09-05T00:21:33", "pid": 3194105, "chain": [[3194104, "bash bin/rl whoami --tag child-deploy"], [3194102, "/bin/bash -c source /home/y-guo/.claude/shell-snapshots/snap…"], [3193366, "claude -p You are in a test sandbox. …"]], "env": {"CLAUDE_CODE_SESSION_ID": "c5b97463-e7aa-407d-877b-d098480949b4", "CLAUDE_CODE_AGENT": "claude", "CLAUDE_PID": "3193366", …}, "state_file_for_env_session": "…/loop/.sessions/c5b97463-e7aa-407d-877b-d098480949b4.json", "state_file_found": true, "role_read": "deploy"}
```

`role_read` 是 deploy，和 SessionStart 钩子给母会话写的状态文件里的角色相同，不是子会话自己的类型（run 子会话读到的同样是 deploy）。

### 2.5 另立信号试了两种，环境文件那种走不通，改写命令那种走得通

第一种，SubagentStart 钩子往 CLAUDE_ENV_FILE 追加 export 行。走不通，原因是 CLAUDE_ENV_FILE 只出现在 SessionStart 钩子进程的环境里（t5a 里的值是 `/home/y-guo/.claude/session-env/c5b97463-e7aa-407d-877b-d098480949b4/sessionstart-hook-1.sh`），SubagentStart、SubagentStop、PreToolUse、SessionEnd 四种钩子进程的环境里都没有这个变量（hooklog.jsonl 里每种事件的 env 键列表）。t5b 里 envexport.py 两次都记下 `envfile_written: null`。

第二种，PreToolUse 钩子用 updatedInput 改写 Bash 命令。走得通。t5b 里 run 子会话那次的钩子输出原文：

```
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "permissionDecisionReason": "sandbox test 5b identity injection", "updatedInput": {"command": "RL_HOOK_AGENT_TYPE=run RL_HOOK_AGENT_ID=a952e5f1f7315ad33 bin/rl whoami --tag child5b-run", "description": "Run rl whoami with child5b-run tag"}}}
```

同一次命令里 rl 看到的环境变量（rl.log 里 tag 是 child5b-run 的那行）：`RL_HOOK_AGENT_TYPE` 是 `run`，`RL_HOOK_AGENT_ID` 是 `a952e5f1f7315ad33`，和 SubagentStart 给这个子会话的 agent_id 一致。这两个变量名是沙盒里的名字，插件里定的名字是 `RL_AGENT_TYPE` 和 `RL_AGENT_ID`（底座会话 2026-09-05 定，rl 判 actor 和步 4 的写权钩子都按插件里的名字用）。deploy 子会话那次拿到的是 `deploy` 和 `a937154c19af4fa21`。两个子会话是并发的（PreToolUse 00:25:29 和 00:25:30 相差 1 秒），各自拿到的是自己的类型和编号，没有串。母会话那次（tag parent5b）没有 RL 开头的变量，说明改写只发生在 agent_type 非空的调用上。

改写的形式又补测了一次链式命令（评审 2026-09-05 指出前置赋值只作用到第一个命令，D-15 改定成 export 形式）。两次打印模式会话里 deploy 子会话各运行同一条命令行 `cd bin && ./rl whoami --tag <a> ; cd .. && bin/rl whoami --tag <b> ; python3 -c "…打印 RL_ 开头的环境变量…"`。前置赋值形式（t5c-prefix，钩子改写成 `RL_HOOK_AGENT_TYPE=deploy RL_HOOK_AGENT_ID=a4134fce3776560c8 cd bin && …`）：两次 rl 记录（tag chainp-a、chainp-b）的 RL 变量都是空，赋值只跟着第一个命令 `cd` 走了。export 形式（t5c-export，钩子改写原文如下）：

```
export RL_HOOK_AGENT_TYPE='deploy'; export RL_HOOK_AGENT_ID='aa7e53254a4da1ab7'; cd bin && ./rl whoami --tag chaine-a ; cd .. && bin/rl whoami --tag chaine-b ; python3 -c "import os; print(sorted(k for k in os.environ if k.startswith(\"RL_\")))"
```

两次 rl 记录（tag chaine-a，cwd 是 bin；tag chaine-b，cwd 是 verify0）的 RL_HOOK_AGENT_TYPE 都是 `deploy`、RL_HOOK_AGENT_ID 都是 `aa7e53254a4da1ab7`，和钩子输入里的 agent_id 一致；第三个命令 python3 打印出 `['RL_HOOK_AGENT_ID', 'RL_HOOK_AGENT_TYPE']`。

上面几次的子会话类型都是 `--agents` 命令行给的。评审 2026-09-05 建议再用插件定义的类型跑一次，把「注入对插件定义的子会话也生效、注入的值是带前缀的全名」收成实测。做法：rlmini 加一份 `agents/deploy.md`（tools 给 Bash 和 Read），打印模式会话（会话 id `b8a1282f…`，2026-09-05 08:26）派 `rlmini:deploy` 子会话运行链式命令 `bin/rl whoami --tag plug-inject-a ; cd bin && ./rl whoami --tag plug-inject-b`，钩子仍是 settings5c.json 的 export 形式。钩子记录原文：

```
SubagentStart 2026-09-05T08:26:21 {"agent_id": "a4794fd9dabff2f27", "agent_type": "rlmini:deploy"}
inject2 2026-09-05T08:26:28 agent_type=rlmini:deploy | rewrote to: export RL_HOOK_AGENT_TYPE='rlmini:deploy'; export RL_HOOK_AGENT_ID='a4794fd9dabff2f27'; bin/rl whoami --tag plug-inject-a ; cd bin && ./rl whoami --tag plug-inject-b
SubagentStop 2026-09-05T08:27:11 {"agent_id": "a4794fd9dabff2f27", "agent_type": "rlmini:deploy"}
```

两次 rl 记录（tag plug-inject-a，cwd 是 verify0；tag plug-inject-b，cwd 是 bin）的 RL_HOOK_AGENT_TYPE 都是 `rlmini:deploy`、RL_HOOK_AGENT_ID 都是 `a4794fd9dabff2f27`。注入的值就是钩子输入里带插件前缀的全名，rl 那一侧按底座 2026-09-05 定的写法取最后一个冒号后面的名字。第一次尝试（01:07，会话 id `d3e901ac…`）子会话刚启动就被 API 的 429（`You've hit your session limit · resets 4:10am`）终止，那次只有 SubagentStart 一条记录，没有 Bash 调用。

### 2.6 另外看到的两件事：交互会话里有多出来的 SubagentStop，被杀掉的子会话没有 SubagentStop

第一件。第 9 条的四个交互会话（9a、9b-2、9b-3、9b-4）里，deploy 子会话发出长跑命令的 PreToolUse 之后同一秒，都有一条 `agent_type` 为空串、agent_id 是另一个值、前面没有对应 SubagentStart 的 SubagentStop。9b-2 那条的原文：

```
[SubagentStop 2026-09-05T00:26:03] {"session_id": "ad9c140a-de68-479d-b263-3b9882039e17", "prompt_id": "07114ffb-3bfa-4e6e-9d81-7f2df611af6b", "permission_mode": "acceptEdits", "agent_id": "a0e7cd786326f1966", "agent_type": "", "effort": {"level": "xhigh"}, "hook_event_name": "SubagentStop", "stop_hook_active": false, "agent_transcript_path": "…/agent-a0e7cd786326f1966.jsonl", "last_assistant_message": "check on the deploy agent status", "background_tasks": [{"id": "a56fd524e4a75bbc2", "type": "subagent", "status": "running", "description": "Run longjob.sh via Bash", "agent_type": "deploy"}]}
```

9a 和 9b-2 里再过 30 到 43 秒还有一条没有 agent_type、agent_id 又是另一个值的 PreToolUse，命令和 deploy 子会话的长跑命令一字不差（9b-2 那条 00:26:46，agent_id `ab9ea2eae5c2d0282`），可是心跳文件里 START 行只有一行，也就是长跑脚本只启动过一次。这两种记录在打印模式的会话（t5a、t5b、9b-1）里没有出现。会话记录文件里找不到这两个 agent_id 对应的子会话记录文件。这两种记录是什么来头这次没查清，只记下来。

第二件。母会话结束的时候子会话被杀掉，那个子会话没有 SubagentStop，只有母会话的 SessionEnd（9b-2、9b-3、9b-4 三个会话的钩子记录，见第三节）。

### 2.7 顺带测到的第 1 条和第 10 条

第 1 条（Bash 环境里有没有现成的会话 id 变量）：有，`CLAUDE_CODE_SESSION_ID`，t5a 里 Bash 看到的值和同一个会话钩子输入里的 session_id 逐字相同（都是 `c5b97463-e7aa-407d-877b-d098480949b4`）。

第 10 条（钩子输入里有没有模型标识）：交互会话的 SessionStart 输入有 `model` 字段，打印模式的没有。交互会话 9a 的原文：

```
[SessionStart 2026-09-05T00:23:21] {"session_id": "f5fec2aa-f243-439a-9822-a90f03e12e03", "hook_event_name": "SessionStart", "source": "startup", "model": "claude-sonnet-5"}
```

打印模式会话 t5a 的原文只有三个键：

```
[SessionStart 2026-09-05T00:21:18] {"session_id": "c5b97463-e7aa-407d-877b-d098480949b4", "hook_event_name": "SessionStart", "source": "startup"}
```

交互会话的 SessionStart 输入还多一个 `scratchpad_dir` 字段。SubagentStart 的输入两种模式下都没有 model 字段。

## 三、第 9 条的实测事实

五个会话，长跑脚本都由 deploy 子会话运行，母会话派完就回一句 SPAWNED 不等。

| 编号 | 母会话 | 长跑秒数 | 母会话怎么结束 | 长跑脚本的结局（心跳文件首末行） | 母会话收没收到完成通知 |
|---|---|---|---|---|---|
| 9b-1 | 打印模式 | 150 | 回复 SPAWNED 之后自然结束 | 跑完：START 00:22:56，END 00:25:26 el=150 | 收到，还多跑了一轮 |
| 9a | tmux 交互 | 2400 | 计划一直活着；实际在 00:36:58 自己结束，原因见 3.5 | 跑了 740 秒被杀掉：START 00:24:27，最后一行 HB 00:36:47 el=740，子会话的工具结果是 `Exit code 137` | 没有 |
| 9a-2 | tmux 交互 | 1200 | 一直活着（9a 的重跑） | 跑完：START 00:40:51，END 01:00:52 el=1201，心跳 123 行没有间断 | 收到：SubagentStop 01:00:53，母会话 01:00:56 运行了 mark.sh，回复 NOTIFIED-DONE |
| 9a-3 | 打印模式 | 1200 | 回复 SPAWNED 之后由 -p 自己等；-p 等到 600 秒上限自己终止 | 被终止：START 00:41:26，最后一行 HB 00:51:07 el=581，之后没有 END | 收到一条 status stopped 的通知 |
| 9a-4 | 打印模式，环境变量 CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 | 700 | 回复 SPAWNED 之后由 -p 自己等，等了 728 秒 | 跑完：START 00:52:07，END 01:03:48 el=701 | 收到：SubagentStop 01:03:49，母会话 01:03:52 运行了 mark.sh |
| 9b-2 | tmux 交互 | 150 | 输入 `/exit`，选「1. Exit and stop tasks」 | 被杀掉：最后一行 HB 00:27:24 el=80，子会话的工具结果是 `Exit code 137` | 没有 |
| 9b-3 | tmux 交互 | 150 | `tmux kill-session`（相当于关终端） | 被杀掉：最后一行 HB 00:28:03 el=20，kill 在 00:28:10，00:28:20 进程已不在 | 没有 |
| 9b-4 | tmux 交互 | 240 | 输入 `/exit`，选「2. Move to background and exit」 | 被杀掉：最后一行 HB 00:29:11 el=20，选项在 00:29:18 确认 | 挪到后台的新会话收到一条状态 failed 的通知 |

### 3.1 9b-1：打印模式的母会话会等后台子会话跑完再退出

run_p.sh 记的墙钟：START 00:22:35，END 00:25:30，elapsed 175 秒。stream-json 里三条 result 的 duration_ms 依次是 4728、156963、13983，也就是母会话第一轮 14 秒回了 SPAWNED，进程没有退出，等了 157 秒到子会话完成，收到 task_notification（status completed），又跑了一轮说「The background agent finished」，然后才退出。钩子顺序：SubagentStart 00:22:51（deploy，agent_id `abc05520b9aac780e`）、PreToolUse 00:22:55（`bin/longjob.sh 150 nine-b1`）、SubagentStop 00:25:27（同一个 agent_id）、SessionEnd 00:25:30（reason other）。

### 3.2 9b-2：交互会话输入 /exit 会弹一个对话框，选「退出并停掉」子会话被杀掉

/exit 之后 tmux 屏幕上的原文：

```
   Background work is running
   The following will stop when you exit:
   subagent · Run longjob.sh via Bash
   shell · bin/longjob.sh 150 nine-b2
   ❯ 1. Exit and stop tasks
     2. Move to background and exit
     3. Stay
   Enter to confirm · Esc to cancel
```

对话框弹出来的时候长跑照跑（run_9b.sh 记的 t+10s、t+20s、t+30s 三行心跳都在涨）。选 1 之后：子会话记录文件里 Bash 的工具结果是 `Exit code 137`（SIGKILL），心跳停在 00:27:24 el=80，00:27:28 tmux 会话消失，两个进程（3205551、3205553）都不在。钩子：SessionEnd 00:27:27 reason `prompt_input_exit`，deploy 子会话（agent_id `a56fd524e4a75bbc2`）没有 SubagentStop。

### 3.3 9b-3：关终端，子会话十秒内被杀掉，SessionEnd 照样触发

`tmux kill-session` 在 00:28:10。心跳最后一行 00:28:03 el=20，之后再没有；00:28:20 起六次探测都没有长跑进程。钩子：SessionEnd 00:28:10 reason `other`，deploy 子会话（agent_id `a995922020f2871b1`）没有 SubagentStop。

### 3.4 9b-4：选「挪到后台再退出」，会话换了一个 id 活下来，子会话没有活下来

选 2 之后 tmux 会话消失；`claude agents --json` 列出一个新的后台会话：

```
{"pid": 3177314, "id": "dd30af6c", "cwd": "/home/y-guo/.claude/jobs/1a0406df/tmp/verify0", "kind": "background", "startedAt": 1788535758815, "sessionId": "dd30af6c-56f8-4a75-b60d-998084aa2873", "name": "Test sandbox agent deployment", "status": "idle", "state": "done"}
```

原会话 id 是 `ab2b2c94…`，挪到后台之后是 `dd30af6c…`，两份会话记录文件都在，后一份的内容从同一句开场话起。心跳停在 00:29:11 el=20，没有 END 行。新会话在 00:29:19 收到一条子会话的通知，原文：

```
<task-notification> <task-id>a41f1f5200fea77fe</task-id> <status>failed</status> <summary>Background agent "Run long job script" was running when the previous Claude Code process exited and did not complete. Its in-process state was lost. Check its worktree/output for partial work before assuming the task landed.</summary> </task-notification>
```

新会话按开场话运行了 `bin/mark.sh nine-b4 NOTIFIED`（marks.log 里那行的 sid 是 `dd30af6c…`，CLAUDE_CODE_AGENT 是空）。钩子：原会话 SessionEnd 00:29:18 reason `prompt_input_exit`；新会话 dd30af6c 在 hooklog.jsonl 里一条记录都没有（新会话不是用 `--settings` 起的，钩子设置没跟过去）。

### 3.5 9a：母会话活着的时候长跑到 740 秒，然后母会话自己结束了

9a 的 deploy 子会话从 00:24:27 起每 10 秒一行心跳，到 00:36:47 el=740 为止没有间断，这 12 分钟里 tmux 屏幕上母会话一直显示 `◯ deploy  Run longjob script for nine-a` 在跑、母会话空闲。00:36:57 子会话的 Bash 工具结果记成 `Exit code 137`，00:36:58 母会话的 SessionEnd 触发，reason 是 `prompt_input_exit`，tmux 会话随之消失。母会话的记录文件最后一条是 00:24:24 回复 SPAWNED 之后的 turn_duration（`pendingBackgroundAgentCount: 1`），之后没有任何输入或输出。验证助手会话在 00:36 前后没有对这个 tmux 会话发过任何按键（发按键的脚本只对 rlv-nine-b2、rlv-nine-b3、rlv-nine-b4 三个会话）。这个会话和沙盒里别的会话一样连着 Remote Control（记录文件里有 bridge-session 行）。这个 reason 值 `prompt_input_exit` 和 9b-2、9b-4 输入 `/exit` 之后的 SessionEnd 相同，和 9b-3 用 `tmux kill-session` 的 `other` 不同。谁让母会话结束的这次没查出来。所以 9a 只证明了后台子会话在母会话活着的时候能跑过 740 秒、没有撞到 Bash 超时，没证明 2400 秒。重跑一次缩成 1200 秒（9a-2），另加一路打印模式 1200 秒（9a-3）。

9a-2（会话 id `0461c189…`）跑完了。心跳文件首末行：

```
START 2026-09-05T00:40:51+09:00 pid=3245106 ppid=3245104 secs=1200
END 2026-09-05T01:00:52+09:00 el=1201
```

钩子顺序：SubagentStart 00:40:47（deploy，agent_id `a4b6d07d2778df531`）、PreToolUse 00:40:50（`bin/longjob.sh 1200 nine-a2`）、SubagentStop 01:00:53（同一个 agent_id）、母会话 PreToolUse 01:00:56（`bin/mark.sh nine-a2 NOTIFIED`）。marks.log 里的那行：`2026-09-05T01:00:56+09:00 sid=0461c189-caa9-47ef-90f5-3ec5c97ff295 agent=none nine-a2 NOTIFIED`。tmux 屏幕上母会话的三句回复依次是 SPAWNED、NOTIFIED-DONE（中间隔了 20 分钟），母会话这 20 分钟里没有人碰过。这个会话里同样有第 2.6 节说的那两种多出来的记录（00:40:50 一条 agent_type 为空串的 SubagentStop，00:41:20 一条没有 agent_type 的 PreToolUse）。

### 3.7 9a-3 和 9a-4：打印模式的母会话默认最多等后台子会话 600 秒

9a-3 的 run_p.sh 墙钟：START 00:40:54，END 00:51:14，elapsed 620 秒，退出码 0。标准错误里的原文：

```
Background tasks still running after 600s; terminating. Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely.
```

stream-json 的顺序：Agent 调用、task_started、SPAWNED、子会话的 Bash 调用（也是一个 task_started）、result（duration_ms 16804）、然后两条 task_notification 的 status 都是 `stopped`（一条是子会话 a3de4abf2d9e650fc，一条是子会话里的 Bash 任务）。心跳最后一行 00:51:07 el=581，没有 END 行。这个会话的钩子记录只有 SessionStart 00:40:55、SubagentStart 00:41:12、PreToolUse 00:41:25 三条，被终止的时候 SubagentStop 和 SessionEnd 都没有触发。9a-4（会话 id `f9c3ff34…`）按标准错误里提示的环境变量 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` 重跑一次，长跑缩成 700 秒：run_p.sh 墙钟 START 00:51:46，END 01:03:54，elapsed 728 秒，标准错误为空；心跳 START 00:52:07，END 01:03:48 el=701；钩子顺序 SubagentStart 00:52:04（deploy，agent_id `ab91fba12d728ee51`）、PreToolUse 00:52:06、SubagentStop 01:03:49（同一个 agent_id）、母会话 PreToolUse 01:03:52（`bin/mark.sh nine-a4 NOTIFIED`）、SessionEnd 01:03:53（reason other）；stream-json 里两条 task_notification 的 status 都是 completed。9a-3 那个被终止的会话到 01:04 为止仍然没有 SessionEnd 记录。

### 3.6 Bash 工具的超时

沙盒设置里 Bash 默认超时是 3600000 毫秒。9b-1 的 150 秒、9a 的 740 秒都没有撞到超时。子会话运行长跑命令的时候，stream-json 里看到 Bash 调用本身被当成一个后台任务（task_started 加 task_notification 之后才有 TOOL_RESULT），交互会话的退出对话框里也把长跑的 shell 单独列成一项。

## 四、补充三条的实测事实

最小插件 rlmini 用 `claude -p --plugin-dir ./rlmini --debug` 加载，母会话在一个回复里启动四个插件 agent，各问一句「What is the marker word?」。四个 agent 定义只给 Read 一个工具，没有 Skill 工具，所以回得出标记词只能是预载进来的。

| agent 定义 | skills 字段 | 回答 |
|---|---|---|
| rlmini:idea-bare | `idea` | IDEAMARK-7391 |
| rlmini:idea-ns | `rlmini:idea` | IDEAMARK-7391 |
| rlmini:gate-bare | `gate`（这个 skill 带 `disable-model-invocation: true`） | NO-MARKER |
| rlmini:gate-ns | `rlmini:gate` | NO-MARKER |

debug 日志（`~/.claude/debug/e8f8ab81-e149-493b-bbc8-e222d4ca6d74.txt`）第 314 行和第 331 行的原文：

```
2026-09-04T15:33:00.771Z [WARN] [Agent: rlmini:gate-bare] Warning: Skill 'gate' specified in frontmatter was not found
2026-09-04T15:33:01.183Z [WARN] [Agent: rlmini:gate-ns] Warning: Skill 'rlmini:gate' specified in frontmatter was not found
```

idea 的两种写法在 debug 日志里没有任何警告。插件 agent 在 Agent 工具里的类型名带插件前缀（init 事件列出的是 `rlmini:idea-bare` 这种写法）。

文本会话另外问：插件 agent 起的子会话，钩子输入里的 agent_type 是裸名还是带前缀。第二次运行（plug2，会话 id `8480ee6f…`，挂上 settings.json 的钩子）里 rlmini:idea-bare 子会话的两条钩子原文：

```
SubagentStart 2026-09-05T00:41:19 {"agent_id": "aac9f74e735f21740", "agent_type": "rlmini:idea-bare"}
SubagentStop 2026-09-05T00:41:21 {"agent_id": "aac9f74e735f21740", "agent_type": "rlmini:idea-bare"}
```

是带插件前缀的全名。第 5 条里 agent_type 是 `deploy` 这种裸名，是因为那两个类型用 `--agents` 命令行参数给的，不经过插件。

### 4.1 D-21：插件级 SessionStart 钩子把插件的 bin 目录写进 PATH，母会话和后台子会话都能直接敲 rl

统筹 2026-09-05 转来的第三条补充项。rlmini 加了插件级钩子文件 `hooks/hooks.json`，只有一条 SessionStart 钩子，命令是 `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/pathexport.py ${CLAUDE_PLUGIN_ROOT}`；脚本往 CLAUDE_ENV_FILE 追加一行 `export PATH="<插件根>/bin:$PATH"`，插件根取钩子进程环境变量 CLAUDE_PLUGIN_ROOT 的值。`rlmini/bin/rl` 是一个只打印一行的脚本。母会话先敲 `rl parent-x`，再派一个 deploy 后台子会话敲 `rl child-x`。

打印模式（会话 id `27d708bd…`）和交互模式（tmux，会话 id `0b6182eb…`）各一次，四次 rl 的输出原文（`pathtest.log`）：

```
RL-ON-PATH 2026-09-05T00:52:53+09:00 tag=parent-p sid=27d708bd-fed7-4f56-94cb-2da9089f7e86 which=/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plugtest/rlmini/bin/rl agent_var=none
RL-ON-PATH 2026-09-05T00:53:00+09:00 tag=child-p sid=27d708bd-fed7-4f56-94cb-2da9089f7e86 which=/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plugtest/rlmini/bin/rl agent_var=none
RL-ON-PATH 2026-09-05T00:53:36+09:00 tag=parent-i sid=0b6182eb-3cd8-4372-ad20-49da7a7a9aab which=/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plugtest/rlmini/bin/rl agent_var=none
RL-ON-PATH 2026-09-05T00:53:41+09:00 tag=child-i sid=0b6182eb-3cd8-4372-ad20-49da7a7a9aab which=/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plugtest/rlmini/bin/rl agent_var=none
```

钩子记录：两次 SessionStart 钩子进程的环境里都有 CLAUDE_PLUGIN_ROOT，值是 `/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plugtest/rlmini`，和命令行替换出来的参数相同；写进去的文件是 `~/.claude/session-env/<session_id>/sessionstart-hook-2.sh`，内容一行 `export PATH="/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plugtest/rlmini/bin:$PATH"`。

## 五、解读和建议

事实到此为止，下面是验证助手的解读和建议。第 5 条「测完由 04 定」，04 是冻结分册，所以这里只给建议，裁决由统筹按代裁规矩记录，正文改动记成欠账。

第 5 条，钩子那一半主案成立：子会话开始和结束各有一条钩子，两条都带同一个 agent_id 和 agent_type，会话 id 和母会话相同。登记和销号可以挂在 SubagentStart 和 SubagentStop 上，主键要用 agent_id 而不能只用 session_id，因为同一个会话 id 下可以同时有好几个子会话（t5a 里两个）。建议 sessions 账给子会话加一栏 agent_id（顶层会话留空），`launched_by` 记 subagent，`session_id` 照记母会话的。

第 5 条，rl 判 actor 那一半，缺口是真的：子会话的 Bash 环境和母会话逐字相同，rl 在子会话里按状态文件读到的一定是母会话的角色，06 第 118 行「subagent 里敲 rl 时按状态文件读到的是父会话的角色」这句成立。建议另立信号，用的就是第 2.5 节走通的那一种：写权钩子本来就要解析每条 Bash 命令，让同一个钩子在输入里 agent_type 非空的时候用 updatedInput 把 `RL_AGENT_TYPE=<agent_type> RL_AGENT_ID=<agent_id>` 加在命令前面，rl 判 actor 的顺序改成先看 RL_AGENT_TYPE、再看状态文件、都没有就是 gyb。环境文件那条路不通，文件那条路在并发子会话下会串（t5a 两个子会话的调用相差 2 秒）。注入要用 export 形式（两个 export 语句加分号再接原命令），前置赋值形式在链式命令上只作用到第一个命令，第 2.5 节两次补测的结果就是这样。这个信号只覆盖 Bash 工具的调用，rl 只会从 Bash 里被调用，够用。

第 5 条，销号那一半：子会话正常结束靠 SubagentStop；母会话结束的时候子会话被杀掉，没有 SubagentStop，只有母会话的 SessionEnd（三种结束方式都是）。所以 SessionEnd 上的销号必须把这个会话 id 名下所有 holder 的单子一起交回，包括子会话认领的。挪到后台再退出那种情况会话换了 id，原会话的 SessionEnd 触发、新会话按新 id 活着，状态文件按旧 id 写的就对不上了，这一点建议 04 记一句。第 2.6 节里 agent_type 为空串的 SubagentStop，按 06 第 102 行「不认识的按最严判」处理，销号脚本收到没登记过的 agent_id 直接跳过就行。

第 9 条，母会话活着那一半，主案成立：交互会话 9a-2 的后台子会话跑满 1200 秒，母会话收到完成通知并按开场话运行了标记命令；打印模式 9b-1 在 150 秒上同样完整走了一轮。几个小时这次没测，1200 秒和 9a 的 740 秒都没有碰到任何超时。打印模式有一个 600 秒的等待上限（3.7），要让 -p 母会话等更久要设 CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0，这一点 launched_by 是 workflow 或者 -p 的派活要写进说明书。打印模式的母会话会自己等后台子会话跑完再退出（3.1），交互会话在屏幕上显示「Waiting for 1 background agent to finish」。母会话结束那一半：三种结束方式子会话都被杀掉，「挪到后台」保住的是会话不是子会话。30 第 21 行的失败备案照旧成立：GPU 在 tmux、单子在账上、下一个 run 会话认领，多出来的只是待认领的单子。另外 /exit 会弹对话框而不是直接退，这一点值得写进 run 角色的说明书；对话框自己写着「The following will stop when you exit」，所以选「留下」应该能保住子会话，这个选项这次没有选过，是推断不是实测。被 -p 的 600 秒上限终止的会话（3.7）SubagentStop 和 SessionEnd 都没触发，子会话手上的单子只能靠 rl status 段 7 和 rl reclaim 兜底，这是评审 2026-09-05 点出来要写进第五节的。

步 4 真会话验收（第七节）的解读。写权钩子按设计拦住了两类写（别的角色的目录、直接写 loop/），回话三样齐全，放行了自己目录的写；注册在敲角色的一秒内落状态文件、四秒内落 open 版；销号在 /exit 的同一秒落 closed 版并删状态文件，setsid 脱离的写法在 1.5 秒预算下和抬高预算下表现一样，D-26 那条「宿主要设 CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS」在这一轮没有用上，可以留着当保险但不是必需。三件要写进说明书或者待裁的事：一是 Bash 工具的工作目录会因为模型自己 `cd` 而漂移，之后相对路径的判定跟着漂（7.4），角色说明书里要写「Bash 里不 cd，路径从仓库根写」；二是注入之后子会话每条 Bash 在 default 模式下都要人按一次审批、「don't ask again」绑着单个 agent_id（7.3），auto 模式下分类器放行（7.6），gyb 的会话都是 auto，所以这条对 gyb 自己开的会话不碍事，对别人用 default 模式的会话要么另写一条 `Bash(export RL_AGENT_TYPE=*)` 之类的宿主规则、要么换注入办法，这一条统筹已列进待裁清单；三是 run 子会话拿到不像发射单的开场话会先斟酌 50 到 85 秒，测试和真派活的开场话都要按单子格式给。

补充三条。D-21 站得住：插件级 SessionStart 钩子往 CLAUDE_ENV_FILE 写一行 export PATH 之后，同一会话的母会话和后台子会话在打印模式和交互模式下都能直接敲到插件的 rl，四次都找到了插件 bin 目录下的那份。D-13 站得住：agents 定义的 skills 字段写裸名和带插件前缀都预载得上，带 `disable-model-invocation: true` 的 skill 两种写法都预载不上，debug 日志报「was not found」。入口 skill 关模型调用之后就不能被任何 agent 定义预载，角色 skill 不能关。

第 1 条和第 10 条顺带的结果：`CLAUDE_CODE_SESSION_ID` 能当会话 id 用；model 字段交互会话有、打印模式没有，所以「取不到记 unknown」那条兜底要留着。

## 七、步 4 真会话验收（2026-09-05 上午，插件快照 HEAD 8628f4d）

这一节测的是底座落地的插件级钩子（`research-loop/hooks/hooks.json` 加 `hooks/rl_hook.py`）在真会话里的行为：注册、写权 deny、销号、注入之后的权限流程。插件按 `git archive HEAD` 打的快照放在沙盒目录 `plug-8628f4d/research-loop/`，用 `--plugin-dir` 装载；同时装第二个只记日志的插件 `rllog/`（钩子事件 SessionStart、SessionEnd、SubagentStart、SubagentStop、UserPromptExpansion、PreToolUse、PostToolUse，只把输入 JSON 追加到 `hooklog2.jsonl`，不做任何决定），两个都是插件级钩子，不用 `--settings` 挂钩子（评审 2026-09-05 提醒：settings 级钩子的 timeout 会把 SessionEnd 的预算抬高，插件级抬不高，混用测出来的时长不算数）。宿主仓库是手搭的（`rl init` 归步 7，HEAD 上还没有）：沙盒目录 `host/`，按 08 第一节放 `research-loop.json`（键按 tables/config_defaults.json，launcher 四个模板留空）、`loop/` 下九本空账（decisions 按六个 actor 各一份文件）、`loop/.sessions/`、experiments/ analysis/ review/ notes/ 四个目录，`git init` 提交一次。

这个快照上 `rl session start`、`rl session end`、`rl session list`、`rl inbox` 都还是「not implemented: build step 3b fills scripts/rl_cmds/」（bin/rl 的原话），所以 sessions 账落不落 open 版和 closed 版这次测不了，只能测钩子这一层：状态文件写没写、删没删、钩子触没触发、deny 的回话、销号脚本跑没跑。session 一族落地之后要再跑一次。

### 7.1 打印模式：`/research-loop:deploy` 触发 UserPromptExpansion，command_name 是带前缀的全名，状态文件写了又在会话结束时删了

`claude -p "/research-loop:deploy"`（会话 id `7639c03f…`，08:32）。记日志插件收到的 UserPromptExpansion 输入原文（去掉 session_id、cwd、transcript_path）：

```
UserPromptExpansion 08:32:16.170 {"prompt_id": "0b67e1f2-3e9b-4027-a82c-c9dd3d15c138", "expansion_type": "slash_command", "command_name": "research-loop:deploy", "command_args": "", "command_source": "plugin", "prompt": "/research-loop:deploy"}
```

会话结束之后 `loop/.sessions/` 里只剩 `7639c03f-….end.log`，内容是：

```
internal
not implemented: rl session end
build step 3b fills scripts/rl_cmds/
```

这个 `.end.log` 只有销号钩子在状态文件存在的时候才会写（rl_hook.py 第 396 到 407 行），所以状态文件在会话期间是存在的，由 UserPromptExpansion 那条钩子写的，销号那条钩子起的后台脚本先运行 `rl session end`（失败，未实现）再删掉了状态文件。会话里模型运行 `which rl` 的结果是 `…/plug-8628f4d/research-loop/bin/rl`，环境文件 `~/.claude/session-env/7639c03f-…/sessionstart-hook-1.sh` 里那一行是 `export PATH="/home/y-guo/.claude/jobs/1a0406df/tmp/verify0/plug-8628f4d/research-loop/bin:$PATH"`，D-21 那条钩子在真插件上生效。SessionEnd 记日志钩子的时间 08:33:11.937，`.end.log` 的修改时间 08:33，`rl session end` 那一步立刻失败所以量不出销号本身的时长。

### 7.2 交互会话：加载角色 1 秒内写状态文件，写别人的目录被拒且回话三样齐全，写自己的目录放行，/exit 之后销号脚本 35 毫秒内起来

tmux 交互会话（会话 id `26f35ffd…`，08:33 到 08:39，`--permission-mode acceptEdits`，Bash、Write 等工具在 allowedTools 里），run_t1.sh 按顺序敲五句。

加载角色：08:33:42 敲 `/research-loop:deploy`，记日志插件 08:33:42.158 收到 UserPromptExpansion（command_name `research-loop:deploy`），08:33:43 `loop/.sessions/` 里已经有状态文件和模型缓存文件，状态文件原文：

```
{"session_id": "26f35ffd-ddb2-4e5f-8ae1-f01e5d783023", "role": "deploy", "model": "claude-sonnet-5", "launched_by": "manual", "started_at": "2026-09-05T08:33:42+0900"}
```

模型名来自 SessionStart 钩子按输入里的 model 字段写的缓存（记日志插件的 SessionStart 输入里 `"model": "claude-sonnet-5"`）。`rl session start` 在这个快照上未实现，登记钩子只落了状态文件。

写别人的目录：敲「用 Write 工具往 analysis/probe.md 写一个 probe」，屏幕原文：

```
● Write(analysis/probe.md)
  ⎿  Error: research-loop: you are a deploy session; Write to analysis/probe.md was denied because analysis/ belongs to analysis
     (06 L45-48). Open an issue to the owner: rl issue open --to analysis --kind denied --handoff <your-order-id> --text "deploy
     needs a change in analysis/probe.md"
```

回话里三样都在：角色（a deploy session）、原因（analysis/ belongs to analysis）、开 issue 的命令（rl issue open --to analysis --kind denied …）。记日志插件只有这次 Write 的 PreToolUse（08:35:37.828），没有 PostToolUse，文件没有生成。

写自己的目录：敲「往 experiments/probe.md 写 probe」，Write 放行，屏幕原文 `⎿  Wrote 1 line to experiments/probe.md`，记日志插件有 PreToolUse 08:35:45.055 和 PostToolUse 08:38:49.540。这两条相差 3 分钟：会话记录文件里 Write 的 tool_use 在 08:35:45、tool_result 在 08:38:49，中间没有任何记录，tool_result 落下的那一秒正好是脚本敲下一句（第三句，往 loop/ 重定向）并按回车的时刻。也就是说这次 Write 被一个不进记录文件的对话框挡住了 3 分钟，脚本的回车把对话框按掉了，第三句的正文被对话框吃掉、没有进入会话（会话记录里没有这句）。是什么对话框这一轮没抓到屏幕，7.4 的补跑带了屏幕抓取。

`rl status`：敲「运行 rl status」，Bash 直接运行（rl 在 PATH 上，D-21 那条钩子生效），结果是 `internal / not implemented: rl status / build step 3b fills scripts/rl_cmds/`。

销号：08:39:05 敲 `/exit`，记日志插件的 SessionEnd 08:39:06.372（reason `prompt_input_exit`），`.end.log` 的修改时间 08:39:06.407，也就是销号钩子起的后台脚本在 SessionEnd 之后 35 毫秒内运行了 `rl session end`（失败，未实现）并删掉了状态文件；08:39:07 tmux 会话消失，之后 12 秒内 `loop/.sessions/` 里只剩 `.end.log`，sessions 账 0 行。钩子本身在 1.5 秒预算内返回，这一点从会话 1 秒内正常退出看得出来；`rl session end` 真正要多久，等 session 一族实现之后再量。会话记录文件里没有 SessionEnd 钩子的时长记录（只有 Stop 钩子有 stop_hook_summary）。

另外每一轮回复结束都有一条 `agent_type` 为空串的 SubagentStop（08:35:28、08:35:41、08:38:53、08:39:05），和第 2.6 节说的一样；这一轮看到输入框里出现了模型建议的下一句（「hook test five: run rl handoff open --help」，没有发出去），这两件事时间上对得上，来源这次仍然没查。

### 7.3 注入只返回 updatedInput 之后，子会话的 Bash 走正常权限流程：宿主按前缀写的放行规则不命中，母会话屏幕上弹出审批框

tmux 交互会话（会话 id `a9e1cd10…`，08:39 到 08:43），`--permission-mode default`，用 `--settings` 传进宿主放行规则 `Bash(rl *)`、`Bash(python3 *)`、`Agent`（这里的 settings 只装规则，不装钩子）。母会话先自己敲 `rl status`：记日志插件 08:40:09.871 收到 PreToolUse，命令 `rl status`，没有弹框，结果 `internal`。然后母会话派 `research-loop:run` 子会话（插件 agents/run.md 定义的，模型 opus，`background: true`）运行同一条 `rl status`。子会话 08:40:21 启动，08:41:11 起先想了 50 秒（子会话记录原文「I'll consult the advisor before acting, since this message asks me to bypass the run role's defined protocol…」），08:41:58 发出 Bash 调用，记日志插件的 PreToolUse 里 tool_input.command 是原命令 `rl status`。母会话屏幕随即出现的对话框原文：

```
 Bash command · from the research-loop:run agent
 Tip: auto mode handles these prompts for you — choose "switch to auto mode" below
   │ export RL_AGENT_TYPE='research-loop:run'; export RL_AGENT_ID='a04565e16f36c3163'; rl status
   Check research-loop status
 This command requires approval
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for export RL_AGENT_TYPE='research-loop:run' and export RL_AGENT_ID='a04565e16f36c3163' commands in /home/y-guo/.claude/jobs/1a0406df/tmp/verify0/host
   3. Yes, and switch to auto mode · auto mode handles these prompts for you
   4. No
```

对话框里的命令已经是插件钩子改写之后的 export 形式，`RL_AGENT_ID` 和 SubagentStart 给这个子会话的 agent_id（`a04565e16f36c3163`）一致。三点事实：同一条 `rl status` 母会话敲不弹框、子会话敲弹框，差别只在钩子改写之后命令以 export 开头、`Bash(rl *)` 不再命中；对话框在母会话的屏幕上，标着来自哪个 agent；第 2 项「don't ask again」生成的规则前缀是 `export RL_AGENT_TYPE='research-loop:run' and export RL_AGENT_ID='a04565e16f36c3163'`，绑着这一个子会话的 agent_id，对下一个子会话没有用。这一轮没有测 auto 模式（对话框第 3 项写着 auto 模式会代答这类提示）；子会话被批准之后的执行没有看到（脚本随后退出并停掉了任务），注入之后命令能正常执行这一点已经在第 2.5 节的打印模式里测过。另外脚本敲 `/exit` 的时候子会话还在等审批，退出对话框（3.2 节那种）把审批框盖住了，选「留下」之后审批框才露出来。

### 7.4 补跑：往 loop/ 重定向被拒、Write review/ 被拒，另外看到 Bash 工具的工作目录漂移会改变相对路径的判定

tmux 交互会话（会话 id `ed41ee61…`，08:44 到 08:47，插件快照 8628f4d，run_t1b.sh，每 3 秒抓一次屏幕）。08:44:14 敲 `/research-loop:deploy`，状态文件写出；模型在加载角色之后自己探索仓库，08:45:50 运行了一条 `cd /home/y-guo/.claude/jobs/1a0406df/tmp/verify0/host/loop && for f in …` 的 Bash 命令。Bash 工具的工作目录在两次调用之间是保持的，从这条命令起这个会话后面所有 Bash 调用的 cwd 都是 `host/loop`（记日志插件里三次 PreToolUse 的 cwd 字段），屏幕状态栏也显示目录是 loop。

第三句（往 loop/ 重定向）：08:46:53 Bash `echo probe > loop/handoffs.jsonl`，cwd 是 host/loop，回话原文：

```
research-loop: you are a deploy session; Bash to loop/loop/handoffs.jsonl was denied because loop/ holds the nine ledgers and is written only through rl (03 L9; 06 L52). Use the rl write command for that ledger instead (rl handoff ..., rl issue ..., rl decision ..., see tables/commands.json).
```

路径 `loop/loop/handoffs.jsonl` 是钩子把相对路径折到当时的 cwd（host/loop）上得出的，和 shell 真正会写的位置一致（06 第 56 行：相对路径折到会话 cwd 上）。直接写 loop/ 的回话按 06 第 98 行给的是 rl 写命令的提示，不给开 issue 的命令，和设计一致。

第五句（往 experiments/ 追加，本来应该放行）：08:47:03 Bash `echo probe >> experiments/notes.txt`，cwd 仍是 host/loop，被拒，回话原文里的路径是 `loop/experiments/notes.txt`。这次拒绝对 shell 真正会写的位置来说是对的（cwd 在 loop/ 下面，相对路径 experiments/notes.txt 落在 loop/experiments/），但是对模型的本意（写 experiments/）来说是误拦。原因不在钩子，在 Bash 工具的工作目录漂移：模型探索时 `cd` 进了 loop/，之后所有相对路径都变了意思。这一点值得写进角色说明书（Bash 里不要 `cd`，或者一律用仓库根起的路径），也说明钩子回话里带折算后的路径是有用的，读的人能从 `loop/experiments/notes.txt` 看出目录漂了。

第六句：Write `review/probe.md`（绝对路径），被拒，回话三样齐：

```
research-loop: you are a deploy session; Write to review/probe.md was denied because review/ belongs to reviewer (06 L45-48). Open an issue to the owner: rl issue open --to reviewer --kind denied --handoff <your-order-id> --text "deploy needs a change in review/probe.md"
```

这一轮四步里都没有出现任何对话框（每 3 秒的屏幕抓取里没有「Do you want」「Enter to confirm」），7.2 节那次挡了 3 分钟的对话框这次没有重现，是什么框仍然没有查出来。08:47:39 敲 `/exit`，1 秒后 tmux 会话消失，`loop/.sessions/` 里只剩 `.end.log`（后面排队的下一轮脚本把目录清空了，所以这次的 `.end.log` 内容没留下）。

### 7.5 session 一族落地之后（快照 fa1adb6）：注册 4 秒内落 open 版，/exit 之后 1 秒内落 closed 版，设不设预算变量没有差别

HEAD 走到 fa1adb6（含 2e53d0d 的 session 一族）之后重新打快照 `plug-fa1adb6/`。先在裸终端里核一次：手搭宿主树里 `rl session start --role deploy --model sonnet --launched-by manual`（环境变量 RL_CALLER=hook）落一行 open 版，`rl session end --reason hook` 落一行 closed 版并打印 `released_handoffs: (none)`，end 这一步墙钟 100 毫秒；没有状态文件的时候 rl 把 session_id 记成 `cli`、actor 记成 `gyb`（03 的裸终端规矩）。`rl init` 在 fa1adb6 上仍然抛「rl init is built in step 7」（init.py 只建了角色会话那道门），所以宿主树仍是手搭的。

真会话两次（run_t1c.sh，tmux，`--permission-mode acceptEdits`），第二次多带环境变量 `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS=10000`：

| | 默认（会话 `6df57aa4…`） | 带预算变量（会话 `a1fac456…`） |
|---|---|---|
| 敲 `/research-loop:deploy` | 08:47:44 | 08:49:07 |
| 状态文件出现 | 08:47:45 | 08:49:08 |
| sessions 账 open 版的 ts | 08:47:44 | 08:49:08 |
| 记日志插件的 SessionEnd | 08:48:59.849 | 08:51:21.347 |
| `.end.log` 的修改时间 | 08:48:59.957 | 08:51:21.450 |
| closed 版的 ended_at | 08:48:59 | 08:51:21 |
| /exit 之后 1 秒探测 | 账 2 行、状态文件只剩 `.end.log` | 同 |

open 版原文（默认那次）：

```
{"actor": "deploy", "launched_by": "manual", "model": "claude-sonnet-5", "role": "deploy", "rules_version": 1, "schema_version": 1, "session_id": "6df57aa4-712a-4268-a85a-98191b65eacd", "started_at": "2026-09-05T08:47:44+0900", "status": "open", "ts": "2026-09-05T08:47:44+0900", "version": 1}
```

closed 版原文（默认那次）：

```
{"actor": "deploy", "end_reason": "hook", "ended_at": "2026-09-05T08:48:59+0900", "launched_by": "manual", "model": "claude-sonnet-5", "released_handoffs": [], "role": "deploy", "rules_version": 1, "schema_version": 1, "session_id": "6df57aa4-712a-4268-a85a-98191b65eacd", "started_at": "2026-09-05T08:47:44+0900", "status": "closed", "ts": "2026-09-05T08:48:59+0900", "version": 2}
```

两次 `.end.log` 都是空的（`rl session end` 没有报错），SessionEnd 到 `.end.log` 出现相差 108 毫秒和 103 毫秒，closed 版在 SessionEnd 的同一秒落账，tmux 会话在 /exit 之后 1 秒消失。销号钩子把 `rl session end` 用 setsid 脱到后台这一招（D-26）在两种预算下都在 1 秒内把 closed 版落了账，预算变量没有改变任何一列。这一轮没有开干的单子，released_handoffs 为空，「交回单子」那一段没有测到。

### 7.6 auto 模式：同一条改写后的命令由分类器放行，不弹框

tmux 交互会话（会话 id `f9e8d852…`，08:52 到 08:55，`--permission-mode auto`，宿主规则同 7.3，快照 fa1adb6，run_t3b.sh）。母会话自己敲 `rl status` 直接运行；`research-loop:run` 子会话 08:52:54 启动，08:54:19 发出 Bash `rl status`（记日志插件的 PreToolUse，agent_type `research-loop:run`），钩子改写成 export 形式之后 08:54:21 就有了工具结果（子会话记录原文 `Exit code 1 internal not implemented: rl status build step 3b fills scripts/rl_cmds/`），母会话屏幕上全程没有出现任何审批框（每 3 秒抓一次屏幕，只有「Waiting for 1 background agent to finish」和之后的「Agent … finished · 1m 44s」），母会话最后回复 `RESULT-PARENT: Exit code 1` 和 `RESULT-CHILD: Exit code 1`。所以在 auto 模式下，以 export 开头的改写命令由分类器放行，default 模式下（7.3）要人按一次审批。这一轮 opus 的 run 子会话从启动到发出命令用了 85 秒，和 7.3 那次的 50 秒一样是在斟酌「这不是发射单要不要做」。

第一次 auto 模式的尝试（会话 `4893718e…`，08:51:27）因为脚本把开场话里的字样当成了结果、8 秒就退出了，没有数据，只记一笔。

## 六、原始记录的位置

- 钩子记录：沙盒目录 `hooklog.jsonl`（所有会话混在一起，按 input.session_id 区分）；第一次冒烟因为脚本吃掉了标准输入而作废的记录在 `hooklog.smoke1-bad.jsonl`。
- rl 记录：沙盒目录 `rl.log`。
- 心跳文件：沙盒目录 `hb/nine-a.log`、`hb/nine-b1.log` 到 `hb/nine-b4.log`。
- 母会话收到通知之后的标记：沙盒目录 `marks.log`。
- 打印模式会话的 stream-json 和墙钟：沙盒目录 `out/t5a.*`、`out/t5b.*`、`out/t9b1.*`、`out/smoke2.*`。
- 交互会话的过程记录：沙盒目录 `out/9b-nine-b2.log`、`out/9b-nine-b3.log`、`out/9b-nine-b4.log`。
- 会话记录文件：`~/.claude/projects/-home-y-guo--claude-jobs-1a0406df-tmp-verify0/`，子会话的记录在各会话目录的 `subagents/` 下。
- 插件测试：沙盒目录 `plugtest/out/plug1.jsonl`、`plugtest/out/plug1.err`，debug 日志 `~/.claude/debug/e8f8ab81-e149-493b-bbc8-e222d4ca6d74.txt`。
- 步 4 真会话验收：插件快照 `plug-8628f4d/`、`plug-fa1adb6/`（`git archive HEAD research-loop` 解出来的）；手搭宿主树 `host/`；记日志插件 `rllog/`，记录在 `hooklog2.jsonl`；各轮的过程记录 `out/upe-p.jsonl`、`out/t1-default.log`、`out/t1b-a.log`、`out/t1c-default.log`、`out/t1c-timeout10s.log`、`out/t3-default.log`、`out/t3b-auto.log`、`out/t3b-auto2.log`；会话记录文件在 `~/.claude/projects/-home-y-guo--claude-jobs-1a0406df-tmp-verify0-host/`。
