#!/usr/bin/env python3
"""new1 全链路统一入口:一个注册表管七段(采集/标注/训练/评测/回放注入/执行/活跑)。

用法(任意 python3 都能跑本文件,底层脚本各用各的 venv):
  python3 run.py list [stage]          # 列任务(按段分组)
  python3 run.py show <task>           # 打印将执行的完整命令与备注,不执行
  python3 run.py <task> [参数...]      # 执行;参数原样透传给底层脚本
  python3 run.py recipes               # 列配方(一条命令跑多步的记名链)
  python3 run.py recipe <name> [--set k=v ...] [--id X] [--resume] [--dry-run]
  python3 run.py status [dir]          # 配方进度(读状态文件+日志尾巴)
  python3 run.py selfcheck             # 注册表体检:解释器/脚本/配方引用齐不齐

三条分派规矩:
- CPU 任务直跑:subprocess, cwd=ROOT, 解释器按注册表(venv 绝对路径)。
- GPU/发射类任务(handoff=True)只拼命令不发射:打印 `<解释器> <脚本> <参数>`
  一段(cd/CUDA_VISIBLE_DEVICES/tee 不打——那是 gpu-run 发射模板的活,打了会被
  二次引用),发射走 gpu-run skill 全生命周期。
- handoff 任务出命令前查工作树:脏(git status --porcelain 非空)就拒绝,
  显式 --allow-dirty 才放行——发射实验前先 commit 是铁律,79/79 次脏发射的
  历史证明软提醒没用。--dry-run 在场时不拦。

扩展规矩(与记忆、probe-pipeline skill Phase E 同一条线):
  以后任何扩展——新模型/新环境/新格/新脚本/新参数——代码落地的同时必须挂进
  本文件:新脚本加 TASKS 条目,新多步流程加 RECIPES 条目,底层脚本加参数不用
  改这里(透传)。训练四格的唯一真源是本文件的 CELLS,ops/launch_probe.py 从
  这里 import——别再另写一张格表。

配方状态与日志:logs/recipe/<name>__<id>/ 下 NN_<step>.log 一步一个文件 +
state.json(tmp+replace 原子写)。续跑键 = (步骤名, 命令指纹),改了参数自动
视为没做过。rc=0 不算完成——声明了 done 的步骤还要验产物在不在。
"""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGD = ROOT / "logs" / "recipe"

# 解释器地图(双环境铁律:mbert 线钉 transformers 4.57.6,cprobe 线 >=5.14,
# 互不升级;appworld/alfworld/tales/bfcl/tau2 各自的仿真环境各管一条线)
PY = {
    "sys":      "python3",
    "cprobe":   str(ROOT / "cprobe-env/bin/python"),
    "mbert":    str(ROOT / "mbert-env/bin/python"),
    "appworld": str(ROOT / "envs/appworld/venv/bin/python"),
    "alfworld": str(ROOT / "envs/alfworld/venv/bin/python"),
    "tales":    str(ROOT / "envs/tales/venv/bin/python"),
    "tau2":     str(ROOT / "envs/tau2-bench/.venv/bin/python"),
    "toolhop":  str(ROOT / "envs/toolhop-env/bin/python"),
    "stbserver": str(ROOT / "envs/stb-server-env/bin/python"),
    "bash":     "bash",
}

# 训练四格唯一真源:格 -> (解释器, 训练脚本, 该格固定要带的参数)。
# ops/launch_probe.py 从这里 import,别处不许再抄一份。
CELLS = {
    "mtool": (PY["mbert"], str(ROOT / "pipeline/train/train_mbert_tool.py"), []),
    "mext":  (PY["mbert"], str(ROOT / "pipeline/train/train_mbert_extract.py"), []),
    "ctool": (PY["cprobe"], str(ROOT / "pipeline/train/train_causal_tool.py"),
              ["--base", "qwen"]),
    "cgen":  (PY["cprobe"], str(ROOT / "pipeline/train/train_causal_callgen.py"), []),
}
CELL_ORDER = ("mtool", "mext", "ctool", "cgen")

# ---------------------------------------------------------------- 任务注册表
# 字段:stage 段名 / desc 一句话 / py 解释器键 / script 相对 ROOT 的脚本
#      args 固定前置参数 / gpu 要不要卡 / handoff 只拼命令不执行(默认=gpu)
#      env 附加环境变量 / cwd 覆盖工作目录(默认 ROOT) / notes 坑位备注
# 一次性发射器(thsweep 系列、launch_vllm_{w0,topup,trio,pair,gptoss,bfcl_gptoss}、
# 各批次生成物 launch_servers.py/launch_clients.sh)按用户裁决不进注册表。

TASKS = {
    # ---- collect 采集 ----
    "collect-aw": dict(
        stage="collect", py="appworld", script="envs/collect/run_appworld.py",
        desc="AppWorld 采集器(要 vLLM /v1 在线)",
        notes=["必给 --base-url --model --outdir;outdir 名必须 appworld_<q35|q36|gptoss>,"
               "别的尾巴下游静默跳过整目录",
               "重跑必带 --resume,否则同名轨迹被截断重写",
               "脚本自己 chdir envs/appworld;相对 --outdir 按 ROOT 解析"]),
    "collect-alf": dict(
        stage="collect", py="alfworld", script="envs/collect/run_alfworld.py",
        desc="ALFWorld 采集器(要 vLLM /v1 在线)",
        notes=["必给 --base-url --model --outdir;--split val=官方 valid_seen",
               "外部 export 过 ALFWORLD_DATA 会盖过 --data-root(脚本 setdefault)",
               "重跑必带 --resume"]),
    "collect-tales": dict(
        stage="collect", py="tales", script="envs/collect/run_tales.py",
        desc="TALES/TWX 采集器(要 vLLM /v1 在线)",
        notes=["无 --split/--exp/分片,分片靠拆 --seeds;--game 写错直接 KeyError",
               "重跑必带 --resume"]),
    "collect-tau2": dict(
        stage="collect", py="tau2", script="envs/collect/run_tau2.py",
        desc="tau2-bench 采集器(要两个 /v1:agent+用户模拟器)",
        notes=["端点冒烟已过(2026-08-02,airline 2 题,gptoss 双端点同服;解析失败/"
               "参数丢失全 0);正式放量未跑,放量时 agent 与用户模拟器要分服分模型",
               "--user-base-url/--user-model 另给,缺省=agent 同端点",
               "服务要 --max-model-len 65536 量级(系统提示 ~6k token)",
               "--domain 只接了 airline/retail;telecom(2285 题,solo 采集要用"
               " llm_agent_solo)还没进 DOMAINS,扩它是集成期的活"]),
    "toolhop-official": dict(
        stage="collect", py="toolhop", script="envs/toolhop/code/evaluation_closed.py",
        cwd=str(ROOT / "envs/toolhop/code"),
        desc="ToolHop 官方闭源路评测器(要 vLLM /v1 在线;本体在 NFS,软链穿透)",
        notes=["服务端必须带 --enable-auto-tool-choice --tool-call-parser openai"
               "(vLLM 0.26 注册表里 openai=GptOssToolParser);裸旗标下模型想调工具"
               "但 tool_calls 恒空(2026-08-02 实测)",
               "必给 --base_url(以 /v1 结尾) --output_file;参数全是下划线风格",
               "冒烟: --input_file ../data/smoke_2.json(相对 code/);输出 append 且跳已存"
               " id,重跑先删输出文件",
               "打印的 Result 百分比写死除以 995,跑子集时无意义;看 Valid Items 与逐条"
               " answer_correct",
               "--scenario Direct 会发 tools:null,vLLM 可能 400;用 Mandatory/Free",
               "toolhop-env 钉 python 3.12;升 3.13 后每次工具调用静默变错误(PEP 667,"
               "已实测);对上游的全部改动见 patches/toolhop_req_closed.diff"]),
    "collect-bfcl": dict(
        stage="collect", prog=str(ROOT / "envs/bfcl/venv/bin/bfcl"),
        cwd=str(ROOT / "envs/bfcl"),
        env={"BFCL_PROJECT_ROOT": str(ROOT / "envs/bfcl")},
        desc="BFCL 采集(console script,cwd=envs/bfcl)",
        notes=["完整流程看 envs/collect/bfcl_gptoss/RUNBOOK.md:先 install_patch.py,"
               "再 printf 题单 json,再 bfcl generate",
               "还要 LOCAL_SERVER_ENDPOINT/LOCAL_SERVER_PORT 两个环境变量指服务"]),
    "gen-launch": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_launch.py",
        desc="按 manifest 生成采集批次的服务+客户端发射器",
        notes=["必给 --config;生成物仍要占卡跑(那一步走 gpu-run)",
               "ENV_TABLE 只有 appworld/alfworld,加环境先扩它"]),
    "gen-alf-splits": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_alfworld_splits.py",
        desc="ALFWorld 官方目录抽题单三堆",
        notes=["没有防覆盖门禁,重跑直接改写已入库 txt"]),
    "gen-bfcl-splits": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_bfcl_splits.py",
        desc="BFCL multi_turn_base 200 题切三堆(四道门禁)",
        notes=["已入库题单不同时拒绝覆盖,要 --force"]),
    "build-dataset-legacy": dict(
        stage="collect", py="cprobe", script="envs/collect/build_dataset.py",
        desc="旧线数据集构建(已被 ann-build 取代,留档)",
        notes=["只认 appworld/tales/bfcl;不认识的目录尾巴静默跳过"]),
    "summarize-full": dict(
        stage="collect", py="sys", script="envs/collect/summarize_full.py",
        desc="全量采集批次成绩汇总(批次/模型写死在代码里)",
        notes=["换批次要改源码;目录缺了静默少一行"]),

    # ---- annotate 标注 ----
    "ann-build": dict(
        stage="annotate", py="sys", script="pipeline/annotate/build.py",
        desc="轨迹 -> 三堆数据集(必给 --config)",
        notes=["采集目录尾巴不在 q35/q36/gptoss 里=整目录静默跳过"]),
    "ann-params": dict(
        stage="annotate", py="sys", script="pipeline/annotate/param_label.py",
        desc="参数抽取标注(必给 --config;须在 ann-build 之后)",
        notes=["三堆 jsonl 不存在就 FileNotFoundError"]),
    "ann-accept-v3diff": dict(
        stage="annotate", py="sys", script="pipeline/annotate/accept_v3diff.py",
        desc="v3 数据集重建一致性验收(无参数,路径写死)",
        notes=["退出码语义特殊:全一致=0,有任何不一致=1"]),
    "ann-check-callstr": dict(
        stage="annotate", py="cprobe", script="pipeline/annotate/check_callstr.py",
        env={"CUDA_VISIBLE_DEVICES": ""},
        desc="真值调用串回读门禁 G19-G22(必给 --config)",
        notes=["文档写 python3 是错的:它 import eval_causal_call -> torch,必须 cprobe-env",
               "入口替它清空 CUDA_VISIBLE_DEVICES(脚本 setdefault 挡不住外部 export)"]),
    "readonly-gen-tables": dict(
        stage="annotate", py="sys", script="pipeline/annotate/readonly/gen_tables.py",
        desc="只读/非只读工具真值表生成器",
        notes=["没有 __main__ 保护,import 即执行;产物是 readonly/{appworld,bfcl}.json"]),

    # ---- train 训练(四格全 GPU,发射走 gpu-run;排卡发射器是 launch-probe) ----
    "train-mtool": dict(
        stage="train", py="mbert", script="pipeline/train/train_mbert_tool.py",
        gpu=True, desc="ModernBERT 工具名探针(必给 --data --out)",
        notes=["--smoke 必须同时换 --out,否则冒烟权重占住 best/",
               "train_log.jsonl 追加不清空"]),
    "train-mext": dict(
        stage="train", py="mbert", script="pipeline/train/train_mbert_extract.py",
        gpu=True, desc="ModernBERT 参数抽取头(必给 --data --out)",
        notes=["产物是裸 state_dict best/model.pt,复用走 load_extractor()"]),
    "train-ctool": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_tool.py",
        gpu=True, args=["--base", "qwen"],
        desc="因果工具名探针(必给 --data --out;固定 --base qwen)",
        notes=["开训对齐门禁 FAIL 退 2(reldiff 1e-6 量级=噪声,1e-3 以上=真错)"]),
    "train-cgen": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_callgen.py",
        gpu=True, desc="因果整条调用生成头(必给 --data --out)",
        notes=["没有 --base,换底座要改源码"]),

    # ---- eval 评测 ----
    "eval-tool-mbert": dict(
        stage="eval", py="mbert", script="pipeline/eval/eval_tool.py",
        gpu=True, args=["--head", "mbert"],
        desc="工具名评测 mbert 头(必给 --env --run --data)",
        notes=["logits 永远写 --run,报告跟 --report-dir;是两个 call 评测的前置"]),
    "eval-tool-causal": dict(
        stage="eval", py="cprobe", script="pipeline/eval/eval_tool.py",
        gpu=True, args=["--head", "causal"],
        desc="工具名评测 causal 头(同上,解释器不同)",
        notes=["同一脚本两解释器按 --head 分岔,注册表拆成两条任务"]),
    "eval-mcall": dict(
        stage="eval", py="mbert", script="pipeline/eval/eval_mbert_call.py",
        gpu=True, desc="mbert 整条调用评测(必给 --env --run --data --extractor)",
        notes=["必须等同模型 eval-tool-mbert 跑完(要 REPLAY_REPORT+logits)",
               "θ 为 null 硬失败退 1:标准处置是降 --risk 0.1 重跑,两档皆 null 才 N/A"]),
    "eval-ccall": dict(
        stage="eval", py="cprobe", script="pipeline/eval/eval_causal_call.py",
        gpu=True, desc="causal 整条调用评测(必给 --env --ctool-run --cgen-run --data)",
        notes=["必须等 eval-tool-causal 跑完;--env 传错静默毁数字"]),
    "matrix": dict(
        stage="eval", py="sys", script="pipeline/eval/summarize_matrix.py",
        desc="矩阵汇总(必给 --runs-dir --out)",
        notes=["--risk 是字符串键,只认 \"0.05\" 或 \"0.1\",传 0.10 整行成 - 但状态仍 OK",
               "--models 是 nargs=+,裸参数会被它吞"]),

    # ---- inject 回放注入 + exec 执行 ----
    "inject-plan": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        gpu=True, args=["plan"],
        desc="出手计划:探针+cgen 过全量事件(必给 --ctool-run --cgen-run --data --traj-root --out)",
        notes=["--theta 盖过 --risk,--decision-file 又盖过 θ"]),
    "inject-run": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        handoff=True, args=["run"],
        desc="按 plan 发续写请求(要 vLLM;长活,进 tmux 跑)",
        notes=["--base-url 必须以 /v1 结尾;输出写 --plan 同目录",
               "--tag 只是 raw 文件后缀,分片要靠外部按臂拆(参 splice_client.py)",
               "单条请求失败只计数,整体照样退 0——完成判据看 raw 行数不是 rc"]),
    "inject-merge-exec": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        args=["merge-exec"], desc="execute 档:执行结果并回 plan(必给 --plan --exec)"),
    "inject-score": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        args=["score"], desc="打分出 INJECT_REPORT(必给 --run-dir)",
        notes=["分片 raw 要先 cat 合并成单个 raw<tag>.jsonl",
               "saved_baseline 换口径要 --rebaseline 且整条 θ 曲线重跑"]),
    "extract-completed": dict(
        stage="inject", py="cprobe", script="pipeline/inject/extract_completed.py",
        desc="按臂抽补完调用 -> exec_in_<arm>.jsonl(必给 --run-dir --arms)",
        notes=["骨架一律用 pred_label,禁用 label(上帝视角红线)"]),
    "exec-calls": dict(
        stage="inject", py="appworld", script="pipeline/inject/exec_calls.py",
        desc="正身世界执行调用(必给 --plan --out --cache --exp)",
        notes=["并发只能多进程+各自 --exp;分片时 out/cache 自动带 .sN 后缀",
               "单 unit 炸只记 unit_errors 继续,rc 仍 0——看 meta.json 不是 rc"]),
    "acceptance": dict(
        stage="inject", py="cprobe", script="pipeline/inject/acceptance.py",
        desc="甲(工具名接受率)/丙(草稿接受长度)算力账(必给 --run-dir)",
        notes=["--base-url 才跑 echo 精确路,必须以 /v1 结尾,"
               "且服务要 util 0.80 + --max-num-batched-tokens 2048 的专用副本"]),
    "sweep-run": dict(
        stage="inject", py="cprobe", script="pipeline/inject/sweep_theta.py",
        handoff=True, args=["run"],
        desc="θ 扫描编排:逐目录 run+score(必给 --runs --services;长活)",
        notes=["子进程解释器写死 cprobe-env,注册表管不到它拉起的 replay_inject",
               ".run_lock 残留要人工确认后删"]),
    "sweep-curve": dict(
        stage="inject", py="cprobe", script="pipeline/inject/sweep_theta.py",
        args=["curve"], desc="汇总 θ 曲线(必给 --runs)",
        notes=["只重跑单点 score 会让曲线两截口径——check_saved_baseline 就是挡这个"]),
    "build-form-table": dict(
        stage="inject", py="cprobe", script="pipeline/inject/build_form_table.py",
        desc="骨架形态表(默认参数即可跑)",
        notes=["硬拦 w0 测试集;重建换表会让已跑完的 skel 臂 score 对不上"]),
    "check-bundle-mbert": dict(
        stage="inject", py="mbert", script="pipeline/inject/check_bundle.py",
        args=["--head", "mbert", "--device", "cpu"],
        desc="mbert 权重包跨进程装载检查(必给 --run --data;CPU)"),
    "check-bundle-causal": dict(
        stage="inject", py="cprobe", script="pipeline/inject/check_bundle.py",
        gpu=True, args=["--head", "causal"],
        desc="causal 权重包装载检查(必给 --run --data;默认 cuda)"),
    "parse-call-selftest": dict(
        stage="inject", py="cprobe", script="pipeline/inject/parse_call.py",
        desc="括号配平提取器自测(无参数;也是 run.py 的冒烟件)"),
    "launch-plan-sweep": dict(
        stage="inject", py="sys", script="pipeline/inject/launch_plan_sweep.py",
        handoff=True, gpu=True,
        desc="θ 扫描 plan 段发射器(自己 ssh+tmux 到 tokyo106)",
        notes=["补发单点必须 --only(SKIP 只挡还活着的会话)"]),

    # ---- live 活跑 + serve 服务 ----
    "live-appworld": dict(
        stage="live", py="appworld", script="pipeline/inject/live_appworld.py",
        handoff=True,
        desc="活跑驱动器(要 vLLM+探针服务;必给 --base-url --probe-url --outdir --exp)",
        notes=["--no-probe 臂也要 --probe-url(/render 在服务侧)",
               "临时故障会写 task_error final,--resume 不重试:重试先删该题 live_*.jsonl",
               "放量走 live-arm-job 12 分片"]),
    "probe-serve": dict(
        stage="live", py="cprobe", script="pipeline/inject/probe_server.py",
        gpu=True, args=["serve"],
        desc="探针常驻服务(ctool+cgen,~3GB;默认端口 8790)",
        notes=["serve_forever 永不返回;温度从 <ctool-run>/REPLAY_REPORT.json 读"]),
    "probe-selftest": dict(
        stage="live", py="cprobe", script="pipeline/inject/probe_server.py",
        args=["selftest", "--device", "cpu"],
        desc="探针触发一致性自检(纯 CPU)"),
    "score-live": dict(
        stage="live", py="cprobe", script="pipeline/inject/score_live.py",
        desc="活跑打分 -> LIVE_REPORT(必给 --live-dir --base-root)",
        notes=["必须等 live_appworld 跑完;task_error 单列不进成败分母"]),
    "live-arm-job": dict(
        stage="live", py="bash", script="envs/serve_logs/live_arm_job.sh",
        handoff=True,
        desc="活跑一臂 12 分片(位置参数 probe|noprobe run_name;tmux 里整段跑)",
        notes=["端口 8114-8116 与探针 tokyo105:8790 写死,换机器改文件",
               "run_name 必填(如 live_aw_gptoss_v2)=runs/ 下输出目录,"
               "防呆:漏传曾经会静默空跑 v1 目录再假报 DONE"]),
    "serve-splice": dict(
        stage="live", py="sys", script="envs/serve_logs/launch_vllm_splice.py",
        handoff=True, gpu=True,
        desc="gpt-oss 三副本 vLLM 发射器(tokyo108:8114-8116;自己 ssh+tmux,幂等)",
        notes=["环境变量(cuda-compat/FLASHINFER/缓存进 /net)已内嵌在脚本里"]),
    "serve-mirrorapi": dict(
        stage="live", prog=str(ROOT / "envs/vllm-env/bin/vllm"),
        handoff=True, gpu=True,
        args=["serve",
              "/net/tokyo100-10g/data/str01_01/y-guo/models/MirrorAPI-Cache",
              "--served-model-name", "mirrorapi-cache"],
        desc="StableToolBench 模拟器 MirrorAPI-Cache(Qwen2.5-7B 微调,bf16 ~15G)",
        notes=["典型追加: --port 8125 --gpu-memory-utilization 0.5",
               "tokyo108 要 LD_LIBRARY_PATH=envs/cuda-compat-13.0(照"
               " envs/serve_logs/run_gptoss.sh 那套);106/107 CUDA 12.2 先 10 秒实测",
               "served-model-name 必须=mirrorapi-cache,server 配置里写死同名"]),
    "stb-virtual-server": dict(
        stage="live", py="stbserver",
        script="envs/stabletoolbench/server/main_mirrorapi_cache.py",
        cwd=str(ROOT / "envs/stabletoolbench/server"),
        handoff=True,
        desc="StableToolBench 虚拟 API 服务(CPU,读 cwd 的 config_mirrorapi_cache.yml)",
        notes=["先起 serve-mirrorapi,再把配置里 api_base 指到它;FastAPI 听 8126",
               "冒烟判据: POST /virtual(category/tool_name/api_name/tool_input/"
               "strip/toolbench_key 六字段)返回 200 且 response 非空;key 不校验",
               "长活服务,进 tmux 跑;工具文档树在 NFS 克隆的 toolenv2404_filtered/"]),
    "splice-plan-job": dict(
        stage="live", py="bash", script="envs/serve_logs/splice_plan_job.sh",
        handoff=True, gpu=True,
        desc="八臂 plan 重跑作业(位置参数 gpu_idx;smoke 门控+字段硬闸)",
        notes=["不 touch PLAN_OK——放行标记是人工的"]),
    "launch-splice-clients": dict(
        stage="live", py="sys", script="envs/serve_logs/launch_splice_clients.py",
        handoff=True,
        desc="八臂三客户端发射器(客户端自己等 PLAN_OK+服务健康)"),
    "accept-vllm-qwen": dict(
        stage="live", py="sys", script="envs/serve_logs/accept_test.py",
        desc="Qwen 双服务验收门(8101/8102;reasoning+content 非空)"),
    "accept-vllm-tools": dict(
        stage="live", py="sys", script="envs/serve_logs/accept_tools_test.py",
        desc="tools 请求验收门(带 tool_choice 不许 400)"),
    "accept-vllm-gptoss": dict(
        stage="live", py="sys", script="envs/serve_logs/gptoss_accept_test.py",
        desc="gpt-oss 服务验收(8103)",
        notes=["只打印不退非零码——按 rc 判成败会永远判通过,要看输出"]),

    # ---- ops 台账/记录/发射 ----
    "gpu-jobs": dict(
        stage="ops", py="sys", script="ops/gpu_jobs.py",
        desc="GPU 台账(register/finish/watch/free/status 原样透传)",
        notes=["register 对拼错的 flag 静默忽略;free 会 exec bash 顶掉进程"]),
    "record": dict(
        stage="ops", py="sys", script="ops/record.py",
        desc="实验记录(start/finish/render/list/show 原样透传)",
        notes=["要 run_id 四处一致只能用 --run-id,--name 会加时间戳前缀",
               "同 run_id 二次 start 直接退出;finish 幂等可重复"]),
    "launch-probe": dict(
        stage="ops", py="sys", script="ops/launch_probe.py",
        gate=True, desc="训练四格排卡发射器(smoke/full;格表从本文件 CELLS 读)",
        notes=["它自己 ssh+tmux 发射,所以出手前过脏树门禁;--dry-run 不拦"]),
}

# ---------------------------------------------------------------- 配方注册表
# 记名多步链。params 里值为 None 的必须用 --set 给;args/done 里的 {占位符}
# 用 params 填,foreach 步骤按逗号列表展开({item}),shards=N 起 N 个分片进程。

RECIPES = {
    "splice-wrapup": dict(
        desc="拼回八臂收官链:extract -> 逐臂 exec(4 分片) -> score -> acceptance",
        params=dict(run_dir=None,
                    arms="nofill,skel_a,skel_bare,skel_b,skel_switch,switch_only",
                    cache="pipeline/inject/exec_cache/aw_gptoss.jsonl",
                    tag=""),
        steps=[
            dict(name="extract", task="extract-completed",
                 args=["--run-dir", "{run_dir}", "--arms", "{arms}",
                       "--tag", "{tag}"]),
            dict(name="exec_{item}", task="exec-calls", foreach="arms", shards=4,
                 args=["--plan", "{run_dir}/exec_in_{item}.jsonl",
                       "--out", "{run_dir}/exec_calls_{item}.jsonl",
                       "--cache", "{cache}", "--exp", "splice_{item}"],
                 done=dict(exists="{run_dir}/exec_calls_{item}.s0.jsonl")),
            dict(name="score", task="inject-score",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/INJECT_REPORT{tag}.json")),
            dict(name="acceptance", task="acceptance",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/ACCEPT_REPORT.json")),
        ]),
    "splice-score": dict(
        desc="只重打分:score -> acceptance(exec 已在时用)",
        params=dict(run_dir=None, tag=""),
        steps=[
            dict(name="score", task="inject-score",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/INJECT_REPORT{tag}.json")),
            dict(name="acceptance", task="acceptance",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/ACCEPT_REPORT.json")),
        ]),
    "annotate-chain": dict(
        desc="标注链:build -> param_label -> check_callstr(同一 --config)",
        params=dict(config=None),
        steps=[
            dict(name="build", task="ann-build", args=["--config", "{config}"]),
            dict(name="params", task="ann-params", args=["--config", "{config}"]),
            dict(name="check", task="ann-check-callstr",
                 args=["--config", "{config}"]),
        ]),
}

# ---------------------------------------------------------------- 引擎

def build_cmd(t, extra):
    prog = t.get("prog") or PY[t["py"]]
    cmd = [prog]
    if "script" in t:
        cmd.append(str(ROOT / t["script"]))
    return cmd + list(t.get("args", [])) + list(extra)


def task_env(t):
    env = os.environ.copy()
    env.update(t.get("env", {}))
    return env


def git_dirty():
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                       capture_output=True, text=True)
    return r.stdout.strip().splitlines() if r.returncode == 0 else None


def gate_dirty(extra):
    """脏树门禁。返回过滤掉 --allow-dirty 之后的参数;拦下时直接 SystemExit。"""
    allow = "--allow-dirty" in extra
    extra = [a for a in extra if a != "--allow-dirty"]
    if "--dry-run" in extra or allow:
        return extra
    lines = git_dirty()
    if lines is None:                       # git 都跑不动 -> 按脏处理,不放行
        raise SystemExit("git status 失败,按脏树处理拒绝出发射命令;"
                         "确认 git 环境,或强行加 --allow-dirty。")
    if lines:
        head = "\n".join("  " + l for l in lines[:8])
        more = f"\n  ...共 {len(lines)} 行" if len(lines) > 8 else ""
        raise SystemExit(
            f"工作树是脏的,拒绝出发射命令(发射前先 commit,CLAUDE.md 铁律):\n"
            f"{head}{more}\n强行要跑加 --allow-dirty。")
    return extra


def tail_of(path, n=40):
    """读日志末尾 n 条非空行。tqdm 用 \\r 覆盖同一行,先换成 \\n。"""
    p = Path(path)
    if not p.exists():
        return "(日志不存在)"
    with open(p, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 65536))
        txt = f.read().decode("utf-8", "replace")
    lines = [l for l in txt.replace("\r", "\n").split("\n") if l.strip()]
    return "\n".join(lines[-n:])


def run_direct(name, t, extra):
    cmd = build_cmd(t, extra)
    print(f"[{name}] cwd={t.get('cwd', ROOT)}")
    print("  " + shlex.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=t.get("cwd", str(ROOT)), env=task_env(t))
    return r.returncode


def print_handoff(name, t, extra):
    extra = gate_dirty(extra)
    cmd = build_cmd(t, extra)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"# {name}: 只拼命令不发射。发射走 gpu-run skill 全生命周期")
    print(f"# (探卡->挑卡->smoke->commit->tmux->双登记->监控->收尾)。HEAD={head}")
    for k, v in t.get("env", {}).items():
        print(f"# 需要环境变量: {k}={v}")
    for n in t.get("notes", []):
        print(f"# {n}")
    print(shlex.join(cmd))
    return 0


# ---------------------------------------------------------------- 配方引擎

def expand(s, params):
    try:
        return s.format(**params)
    except KeyError as e:
        raise SystemExit(f"配方占位符没给值: {e}(用 --set k=v)")


def plan_steps(rc, params):
    """把配方展开成具体步骤:[{name, task, cmds:[argv...], logs:[...], done}]。"""
    out = []
    for st in rc["steps"]:
        items = ([x.strip() for x in params[st["foreach"]].split(",") if x.strip()]
                 if "foreach" in st else [None])
        for it in items:
            p = dict(params, item=it) if it is not None else params
            t = TASKS[st["task"]]
            args = [expand(a, p) for a in st["args"]]
            base = build_cmd(t, args)
            n = st.get("shards", 0)
            if n:
                cmds = [base + ["--num-shards", str(n), "--shard-id", str(i)]
                        for i in range(n)]
            else:
                cmds = [base]
            done = None
            if st.get("done"):
                done = {k: expand(v, p) for k, v in st["done"].items()}
            out.append(dict(name=expand(st["name"], p), task=st["task"],
                            cmds=cmds, done=done,
                            env=t.get("env", {}), cwd=t.get("cwd", str(ROOT)),
                            handoff=t.get("handoff", t.get("gpu", False))))
    return out


def fp_of(cmds):
    return hashlib.sha1(json.dumps(cmds).encode()).hexdigest()[:12]


def save_state(d, state):
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    os.replace(tmp, d / "state.json")


def check_done(done):
    if not done:
        return True
    if "exists" in done:
        return (ROOT / done["exists"]).exists()
    return True


def run_recipe(name, argv):
    rc = RECIPES.get(name)
    if rc is None:
        raise SystemExit(f"没有这个配方: {name}(run.py recipes 看清单)")
    params = dict(rc["params"])
    rid, resume, dry = None, False, False
    it = iter(argv)
    for a in it:
        if a == "--set":
            kv = next(it, "")
            if "=" not in kv:
                raise SystemExit(f"--set 要 k=v,给的是 {kv!r}")
            k, v = kv.split("=", 1)
            if k not in params:
                raise SystemExit(f"配方 {name} 没有参数 {k},有的是 {list(params)}")
            params[k] = v
        elif a == "--id":
            rid = next(it, None)
        elif a == "--resume":
            resume = True
        elif a == "--dry-run":
            dry = True
        elif a == "--allow-dirty":
            pass                       # 配方目前全 CPU;留给将来 handoff 步
        else:
            raise SystemExit(f"配方不认识的参数: {a}(底层参数写进配方定义,不透传)")
    missing = [k for k, v in params.items() if v is None]
    if missing:
        raise SystemExit(f"配方 {name} 缺参数: {missing}(用 --set k=v)")

    steps = plan_steps(rc, params)
    if dry:
        for i, s in enumerate(steps):
            print(f"[{i + 1}/{len(steps)}] {s['name']}")
            for c in s["cmds"]:
                print("    " + shlex.join(c))
        return 0

    def params_of(p):
        try:
            return json.loads((p / "state.json").read_text()).get("params")
        except Exception:
            return None

    if resume and rid is None:
        # 只认 params 逐字一致的历史目录——按 mtime 瞎挑会挂到另一次运行上,
        # 把人家的 state.json 覆盖掉(审查坐实过这条)。
        olds = sorted(LOGD.glob(f"{name}__*"), key=lambda p: p.stat().st_mtime)
        match = [p for p in olds if params_of(p) == params]
        if not match:
            names = [p.name for p in olds[-5:]]
            raise SystemExit(f"--resume 找不到参数一致的 {name} 历史目录;"
                             f"用 --id 指定。最近的有: {names}")
        rid = match[-1].name.split("__", 1)[1]
    rid = rid or time.strftime("%Y%m%d_%H%M%S")
    d = LOGD / f"{name}__{rid}"
    if (d / "state.json").exists() and params_of(d) != params:
        raise SystemExit(f"{d.name} 里是另一组参数的运行(params={params_of(d)}),"
                         f"拒绝覆盖;换个 --id 或把参数对齐。")
    d.mkdir(parents=True, exist_ok=True)

    old = {}
    sp = d / "state.json"
    if resume and sp.exists():
        for s in json.loads(sp.read_text()).get("steps", []):
            old[(s["name"], s["fp"])] = s

    dirty = git_dirty() or []
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    state = dict(recipe=name, id=rid, params=params, git_commit=head,
                 git_dirty=bool(dirty), started_at=time.strftime("%F %T"),
                 steps=[dict(name=s["name"], fp=fp_of(s["cmds"]), state="pending",
                             rc=None, cmds=s["cmds"], logs=[], wall_s=None)
                        for s in steps])
    save_state(d, state)

    for i, s in enumerate(steps):
        rec = state["steps"][i]
        prev = old.get((rec["name"], rec["fp"]))
        if prev and prev.get("state") == "ok":
            rec.update(prev)
            rec["state"] = "ok"
            print(f"[{i + 1}/{len(steps)}] {s['name']} SKIP(已完成,指纹一致)")
            save_state(d, state)
            continue
        if s["handoff"]:
            rec["state"] = "handoff"
            save_state(d, state)
            print(f"[{i + 1}/{len(steps)}] {s['name']} 是发射类任务,配方停在这:")
            for c in s["cmds"]:
                print("    " + shlex.join(c))
            print("发射走 gpu-run;跑完后 run.py recipe "
                  f"{name} --id {rid} --resume 接着走。")
            return 3
        rec["state"], t0 = "running", time.time()
        rec["started_at"] = time.strftime("%F %T")
        save_state(d, state)
        procs, logs = [], []
        env = os.environ.copy()
        env.update(s["env"])
        for j, c in enumerate(s["cmds"]):
            suffix = f".s{j}" if len(s["cmds"]) > 1 else ""
            log = d / f"{i:02d}_{s['name']}{suffix}.log"
            logs.append(str(log))
            fh = open(log, "a")
            fh.write(f"# [{time.strftime('%F %T')}] step={s['name']} "
                     f"cmd: {shlex.join(c)}\n")
            fh.flush()
            procs.append((subprocess.Popen(c, cwd=s["cwd"], env=env,
                                           stdout=fh, stderr=fh), fh))
            print(f"[{i + 1}/{len(steps)}] {s['name']}"
                  f"{suffix or ''} -> {log.name}", flush=True)
        rcs = []
        for p, fh in procs:                 # 逐个收 rc,不用裸 wait(收不到码)
            rcs.append(p.wait())
            fh.close()
        rec["rc"] = rcs if len(rcs) > 1 else rcs[0]
        rec["logs"] = logs
        rec["wall_s"] = round(time.time() - t0, 1)
        ok = all(r == 0 for r in rcs) and check_done(s["done"])
        rec["state"] = "ok" if ok else "failed"
        save_state(d, state)
        if not ok:
            why = (f"rc={rec['rc']}" if any(rcs) else
                   f"rc 全 0 但产物没到位: {s['done']}")
            print(f"\nFAILED step {i + 1}/{len(steps)} {s['name']} {why} "
                  f"wall={rec['wall_s']}s")
            for lg in logs:
                print(f"  日志: {lg}")
            bad = next((logs[j] for j, r in enumerate(rcs) if r != 0), logs[-1])
            print(f"---- 末 40 行 ({Path(bad).name}) ----")
            print(tail_of(bad))
            print(f"修好后: python3 run.py recipe {name} --id {rid} --resume")
            return 1
    print(f"\n配方 {name} 全部 {len(steps)} 步完成。状态: {d / 'state.json'}")
    return 0


def cmd_status(argv):
    if argv:
        d = Path(argv[0])
        if not d.is_absolute():
            d = LOGD / argv[0]
    else:
        dirs = sorted(LOGD.glob("*__*"), key=lambda p: p.stat().st_mtime)
        if not dirs:
            raise SystemExit(f"{LOGD} 下还没有任何配方记录")
        d = dirs[-1]
    sp = d / "state.json"
    if not sp.exists():
        raise SystemExit(f"没有状态文件: {sp}")
    st = json.loads(sp.read_text())
    print(f"配方 {st['recipe']}  id={st['id']}  HEAD={st['git_commit']}"
          f"{'+dirty' if st['git_dirty'] else ''}  起于 {st['started_at']}")
    for i, s in enumerate(st["steps"]):
        wall = f" {s['wall_s']}s" if s.get("wall_s") else ""
        print(f"  [{i + 1}] {s['name']:<24} {s['state']:<8} rc={s['rc']}{wall}")
        if s["state"] == "failed" and s.get("logs"):
            print("  ---- 失败日志末 20 行 ----")
            print("  " + tail_of(s["logs"][-1], 20).replace("\n", "\n  "))
        if s["state"] == "handoff":
            for c in s["cmds"]:
                print("    待发射: " + shlex.join(c))
    return 0


# ---------------------------------------------------------------- 查看类

STAGE_ORDER = ("collect", "annotate", "train", "eval", "inject", "live", "ops")


def cmd_list(argv):
    want = argv[0] if argv else None
    for stg in STAGE_ORDER:
        if want and stg != want:
            continue
        rows = [(n, t) for n, t in TASKS.items() if t["stage"] == stg]
        if not rows:
            continue
        print(f"\n== {stg} ==")
        for n, t in rows:
            mark = ("[发射]" if t.get("handoff", t.get("gpu", False))
                    else "[GPU]" if t.get("gpu") else "")
            print(f"  {n:<22} {mark:<6} {t['desc']}")
    print("\n配方(run.py recipes 看详情):", ", ".join(RECIPES))
    return 0


def cmd_show(argv):
    if not argv or argv[0] not in TASKS:
        raise SystemExit(f"要一个任务名,有的是: {', '.join(TASKS)}")
    n, t = argv[0], TASKS[argv[0]]
    print(f"{n}: {t['desc']}  (stage={t['stage']})")
    print(f"  命令: {shlex.join(build_cmd(t, ['<参数...>']))}")
    print(f"  cwd: {t.get('cwd', ROOT)}")
    if t.get("env"):
        print(f"  env: {t['env']}")
    print(f"  gpu={t.get('gpu', False)} handoff={t.get('handoff', t.get('gpu', False))}"
          f" 脏树门禁={t.get('gate', t.get('handoff', t.get('gpu', False)))}")
    for note in t.get("notes", []):
        print(f"  - {note}")
    return 0


def cmd_recipes():
    for n, rc in RECIPES.items():
        print(f"\n{n}: {rc['desc']}")
        print(f"  参数: " + ", ".join(
            f"{k}(必填)" if v is None else f"{k}={v!r}"
            for k, v in rc["params"].items()))
        for st in rc["steps"]:
            extra = " x" + str(st["shards"]) if st.get("shards") else ""
            fe = f" foreach={st['foreach']}" if "foreach" in st else ""
            print(f"    {st['name']} -> {st['task']}{extra}{fe}")
    return 0


def cmd_selfcheck():
    bad = 0
    seen_prog = set()
    for n, t in TASKS.items():
        prog = t.get("prog") or PY[t["py"]]
        if prog not in seen_prog and prog not in ("python3", "bash"):
            if not Path(prog).exists():
                print(f"缺解释器/程序: {prog}  (任务 {n})")
                bad += 1
            seen_prog.add(prog)
        if "script" in t and not (ROOT / t["script"]).exists():
            print(f"缺脚本: {t['script']}  (任务 {n})")
            bad += 1
    for rn, rc in RECIPES.items():
        for st in rc["steps"]:
            if st["task"] not in TASKS:
                print(f"配方 {rn} 引用不存在的任务 {st['task']}")
                bad += 1
            if "foreach" in st and st["foreach"] not in rc["params"]:
                print(f"配方 {rn} 的 foreach={st['foreach']} 不在 params 里")
                bad += 1
    print(f"selfcheck: {len(TASKS)} 任务 / {len(RECIPES)} 配方, "
          f"{'全部就位' if not bad else f'{bad} 处缺失'}")
    return 1 if bad else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        return cmd_list(rest)
    if cmd == "show":
        return cmd_show(rest)
    if cmd == "recipes":
        return cmd_recipes()
    if cmd == "recipe":
        if not rest:
            raise SystemExit("recipe 要配方名(run.py recipes 看清单)")
        return run_recipe(rest[0], rest[1:])
    if cmd == "status":
        return cmd_status(rest)
    if cmd == "selfcheck":
        return cmd_selfcheck()
    t = TASKS.get(cmd)
    if t is None:
        raise SystemExit(f"不认识: {cmd}(run.py list 看任务,run.py recipes 看配方)")
    if t.get("handoff", t.get("gpu", False)):
        return print_handoff(cmd, t, rest)
    if t.get("gate") and "--dry-run" not in rest:
        rest = gate_dirty(rest)
    return run_direct(cmd, t, rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
