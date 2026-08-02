# env_locks — 版本锁快照

这个目录下的 `*.txt` 是本项目**全部实验用环境**的 pip freeze 快照（审计 E26，
2026-08-02 生成），用来在出现"某环境突然装不进包 / 行为跟以前不一样"时，
能对照到具体哪个包的版本变了，而不用去猜。
"全部实验用环境" = 下面那张对应表列的那些；`related_work/` 下第三方 clone 自带的
venv 不算在内，它们不参与本项目的实验，也不做快照。

## 生成命令

本项目的 venv 都是 `uv venv` 建的，venv 内部通常没装 pip 模块本体（`<venv>/bin/python -m pip`
会报 `No module named pip`），所以不能直接用 `pip freeze`。改用 `uv pip freeze` 对着
venv 的 python 解释器跑，效果等价：

```bash
uv pip freeze --color never --python <venv>/bin/python > ops/env_locks/<名字>.txt
```

`--color never` 是必须的：uv 默认会在非 tty 输出里也塞 ANSI 颜色码，重定向到文件时
不加这个参数会把控制字符写进快照，污染 diff。

对应关系（venv 路径 → 快照文件名）：

| venv 路径 | 快照文件 |
|---|---|
| `cprobe-env` | `cprobe-env.txt` |
| `mbert-env` | `mbert-env.txt` |
| `jlens-env` | `jlens-env.txt` |
| `envs/appworld/venv` | `appworld.txt` |
| `envs/alfworld/venv` | `alfworld.txt` |
| `envs/tales/venv` | `tales.txt` |
| `envs/tau2-bench/.venv` | `tau2.txt` |
| `envs/toolhop-env` | `toolhop.txt` |
| `envs/stb-server-env` | `stb-server.txt` |
| `envs/vllm-env` | `vllm.txt` |
| `envs/bfcl/venv` | `bfcl.txt` |

## 双环境铁律

`mbert-env` 和 `cprobe-env` 各管一条实验线，版本互不迁就，任何情况下都不许为了
解冲突去升级或降级已装好的环境：

- `mbert-env`：transformers 钉死 **4.57.6**。
- `cprobe-env`：transformers 保持 **≥5.14**。

旧版 transformers 对混合架构做分块增量前向会静默算错（不报错、结果是错的），
两条线就是为隔离这个坑才分开的。升错一边，之前跑的实验结论全部作废且没人会
立刻发现。这两个环境的快照文件头部额外带一行铁律提示，其余环境的快照没有。

## 使用方式

- **重大升级前先重生成快照并 commit**：动 `uv pip install` / `uv sync` 之类会改变
  某个 venv 包版本的操作之前，先按上面的命令重新生成对应环境的快照、`git diff`
  看清楚要变的到底是哪些包、确认不碰红线包（尤其是 mbert-env / cprobe-env 里的
  transformers），再 commit 这次快照更新，之后再动手装包。
- 怀疑某个环境"以前能跑现在不能跑"，先 `git log -p ops/env_locks/<名字>.txt`
  翻历史快照对比，比重新趟一遍装包过程快。
- 这些快照是只读记录，不是环境定义文件，不能拿去 `uv pip install -r` 直接复原
  环境（有的包是可编辑安装 / 本地路径安装，freeze 出来的行不一定能反向安装）。
