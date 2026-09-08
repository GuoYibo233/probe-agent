# demo：在 CPU 上用 debugger 走一遍训练器

## 这个目录用来在没有显卡的机器上一步一步看训练器怎么跑

要看的训练器是 `pipeline/train/train_causal_share.py`，cgen 与 cparam 两格共用的缓存复用训练器。缓存复用的意思是：一个事件（轨迹里的一步，带若干个切点，每个切点是一行样本）的全文只过一遍模型，每一行的目标段接在共享的前缀后面计算损失，同一段前缀在几行之间不重复计算。真实训练要加载 Qwen3-0.6B 到 4B 的底座、读取 NFS 上 1.2 GB 的 `train.jsonl`，两样都不适合在 debugger 里等。

训练器本身一个字都没有改。训练器本来就留了两扇门：`--base` 给一个目录路径的时候走 `build(path=...)` 加载任意目录里的模型，`--device cpu` 不碰显卡。演示只是把这两扇门后面的东西换成假件：

- 模型换成 `demo/tiny_qwen3/`：两层、hidden 64 的随机初始化 Qwen3，978 万参数（`prepare.py` 打印的 `9780928 params`），分词器是从真 Qwen3-0.6B-Base 拷贝过来的。结构与真底座同族，所以训练器要取的 `model.model` 与 `model.lm_head` 都在。
- 数据换成 `demo/data/train.jsonl` 与 `demo/data/val.jsonl`：合成的 AppWorld 风格样本，训练集 12 个事件 61 行，验证集 6 个事件 27 行。字段与真数据逐个相同；切点用 `rules.boundaries`，题干用 `rules.assemble`，调用串用 `build.make_call`，三个都是标注段的真函数，只有轨迹的内容是编写的。

两样假件都由 `demo/prepare.py` 一条命令构建出来，随种子固定，重新构建得到相同的文件。按工程铁律，大产物直接写 net 盘：`prepare.py` 会把 `demo/tiny_qwen3` 与 `demo/runs` 做成指向 `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/demo/` 下同名目录的软链，与 `pipeline/data`、`pipeline/runs` 同一个做法，home 里只留代码、数据 jsonl 与软链。

“训练的代码”在这里指的是现役这一条线（cgen / cparam 共用的缓存复用训练器）。同一份假件也能指给 ctool 格的 `train_causal_tool.py`，那个脚本的 `--base` 只接受 qwen / qwen17 / qwen4 三个名字，要先给那个脚本加上 `path=` 这一扇门。

## 两条命令就能把演示跑起来

第一条命令构建假件，十秒跑完（分词器从 NFS 拷贝，模型写到 net 盘）：

```
python3 run.py demo-prep
```

第二条是进 debugger。`.vscode/launch.json` 里有三个配置，在 VS Code 的“运行和调试”面板里选择“demo: train cgen on CPU (tiny model)”按 F5 就开始跑；看 cparam 格就选择第二个配置。两个配置都把 `CUDA_VISIBLE_DEVICES` 置空，所以进程看不见任何显卡。整程（对齐检查加两个 epoch 的训练）在 shiga 上 15 秒跑完。配置里的 `"type": "debugpy"` 要现在的 Python Debugger 扩展；扩展太旧的话把 `"type"` 改成 `"python"` 就能用。

不进 debugger、只想看训练器跑一遍的时候：

```
python3 run.py demo-train --mode cgen --out demo/runs/cgen
```

`--out` 目录里已经有 `train_log.jsonl` 的时候训练器会拒绝再训，这道门是防止两次产物混进同一个 `best/`。第二次跑要加 `--force`；launch.json 里的两个训练配置已经带上了 `--force`，可以反复按 F5。

## 每个参数都是为了让训练循环的某一层走到

launch.json 与 `demo-train` 用的是同一组参数：

- `--epochs 2 --eval-per-epoch 2`：两个 epoch，每个 epoch 评估两次，所以评估点、保存 best、下一个 epoch 换种子重新打乱这几处都会经过。
- `--events-per-mb 4 --accum 2`（训练器的默认值）：12 个训练事件切成 3 个逻辑小批，每 2 个逻辑小批做一次参数更新，所以一个 epoch 是 2 次更新，第二次更新只有 1 个逻辑小批，`n_g` 从 2 变成 1，不满组的分支能看到。
- `--tok-budget 768`：一个逻辑小批的 4 个事件按拼接长度装块，768 的预算下 epoch 0 的三个逻辑小批各切成 2 个物理块（`prepare.py` 打印的 `[2, 2, 2]`；epoch 1 重新打乱，块数可能不同），所以“一个逻辑小批拆成多个物理块、梯度累加”这一层不是空转。
- `--log-every 1`：每次更新都写一条 step 日志。
- `--gen-eval 4 --gen-bs 2`：epoch 末的评估额外对 4 行做生成式评估，生成式评估会调用 `model.generate`，所以生成路径也走到。
- `--align-events 3`：开训前的对齐检查只抽取 3 个验证事件。

## 断点按 main() 的顺序下在这十个函数上

想从第一行开始按执行顺序逐段读，看 `demo/WALKTHROUGH.md`：那份导读分 15 站，每一站给出行号、这几行在做什么、在假件上停下来会看到的数，以及按哪个键。下面这十个函数是导读的缩写版。

行号会变，函数名不变，所以断点按函数名下：

1. `train_causal_callgen.build`：加载分词器与模型。演示里 `--base` 是目录路径，走 `path=` 分支。
2. `run_align_check`：开训前的对齐检查。同一份验证事件分别走新路径（`_new_forward`，打包一次前向）与参照路径（`_ref_forward`，旧训练器逐行前向），逐行 loss 的差要小于 `--align-tol`。不过就 `sys.exit(2)`，报告写在 `ALIGN_CHECK.json`。
3. `share_data.load_events`：加载一个 split。按事件分组、全文分词、计算每行与全文的公共前缀长度 `p`、拼接出目标段 `seg_ids` / `seg_lab`。一个事件是 `dict(event, n_full, packed_len, prefix_len, full_ids, rows)`，`rows` 里每一行是七元组 `(sent_idx, text, p, seg_ids, seg_lab, w, gen)`。
4. `share_data.epoch_minibatches`：一个 epoch 用种子加 epoch 号打乱事件，每 4 个事件一个逻辑小批。
5. `share_data.chunk_by_budget`：一个逻辑小批按 token 预算贪心装块，每一块就是一个物理块。
6. `_forward_packed` 里调用的 `share_data.pack_event` 与 `share_data.batch_mask`：把一个事件拼接成一条序列（共享前缀加各行的目标段）并构建注意力掩码。`batch_mask` 返回的 `mask` 是 `[B, 1, L_pad, L_pad]` 的加性掩码，可看的位置是 0、不可看的位置是负无穷；`loss_idx` 是每个目标 token 的（batch 下标、query 位置、目标 id、行号）。掩码这一步是缓存复用训练器与逐行训练器的差别所在。
7. `backward_logical_minibatch` 调用 `block_row_ce`：一个物理块前向、逐 token CE 按行聚合、按行权重加权、反向。
8. `main()` 里的 `clip_grad_norm_`、`opt.step()`、`sch.step()`：一次参数更新。
9. `eval_ce` 与 `train_causal_callgen.eval_gen`：验证集全量加权 CE，以及 epoch 末的生成式评估。
10. `model.save_pretrained(out / "best")`：val_ce 创新低就保存一份。

看掩码最直观的办法是在 `batch_mask` 的 return 处停下来，对第一个事件执行 `(mask[0, 0] == 0).int()`，得到的 0/1 矩阵就是“哪个 token 能看到哪个 token”。

## CPU 上有几处分支和显卡上不同

看到下面这几处的时候不要当成 bug：

- `_attn_ctx` 在 CPU 上返回空上下文，`sdpa_kernel([EFFICIENT_ATTENTION])` 只在 cuda 上生效。
- `amp` 是 False，`torch.autocast("cuda", enabled=False)` 是空操作，掩码用 fp32。
- `_peak_gb` 在 CPU 上恒为 0，step 日志里的 `peak_mem_gb` 一直是 0.0。
- 对齐检查里 bf16 粗筛那一段只在 cuda 上跑，`ALIGN_CHECK.json` 里的 `bf16_mean_abs_diff` 是 null。
- 模型是随机初始化的，loss 与 val_ce 的数值没有意义，只看流程。

## 产物在 net 盘上，删掉重新构建就回来

`demo/runs/<mode>/` 里是 `train_log.jsonl`、`ALIGN_CHECK.json` 与 `best/`，和真实训练的产物同构；不进库、不进矩阵、不记账。`demo/tiny_qwen3` 与 `demo/runs` 是软链，实体在 net 盘的镜像目录里，两个软链都在 `.gitignore` 里；删掉之后重跑 `demo-prep` 就回来。`demo/data/*.jsonl` 进库，不跑脚本也能在编辑器里读样本。
