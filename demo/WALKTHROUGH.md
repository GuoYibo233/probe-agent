# demo 导读：按执行顺序把训练器从第一行读到最后一行

## 这份导读怎么用

这份导读按程序真实的执行顺序排，一共 15 站，每一站说清四件事：代码在哪个文件的哪几行、这几行在做什么、在演示假件上停下来会看到什么数、debugger 里按哪个键。读的顺序就是执行的顺序，所以从第 1 站开始顺着读，不要跳。

行号是 HEAD `c13404b` 时的行号，两个主文件（`pipeline/train/train_causal_share.py` 与 `pipeline/train/share_data.py`）最近一次改动在 `3f5dd79`。行号以后会漂，函数名不会，所以每一站都同时给函数名。

文中的数字有三个来源。事件、行、拼接长度、装块这一类数字是用训练器自己的函数在假件上算出来的，在对应断点处停下来能看到同样的数；训练过程的数字来自 `demo/runs/cgen/train_log.jsonl`；对齐检查的数字来自 `demo/runs/cgen/ALIGN_CHECK.json`。模型是随机初始化的，所有损失值只说明流程走通了，不说明别的。

debugger 的操作只用五个动作。F5 是继续运行到下一个断点，F10 是执行当前行然后停在下一行（不进入被调用的函数），F11 是进入当前行调用的函数，Shift+F11 是从当前函数退回到调用处，调试控制台（Debug Console）可以随时输入表达式求值。launch.json 里 `justMyCode` 是 false，所以 F11 能进入 transformers 和 torch 的代码；遇到 `tok(...)`（分词器）和 `json.loads` 这类调用用 F10 跳过，进去看不到与训练器有关的东西。

从零开始读的办法是：在 `pipeline/train/train_causal_share.py:859`（`main()` 的第一行）设置一个断点，选择 launch.json 里的“demo: train cgen on CPU (tiny model)”按 F5，然后一路按 F10；每到导读里点名的调用处按 F11 进入，看完按 Shift+F11 回来。循环体第一遍逐行看完之后，后面的迭代用条件断点跳过：在红点上右键选择“编辑断点”，填一个表达式，只有表达式为真的时候才停。

## 先把要用到的名字定下来

下面每个名字在全文里只用一个说法。

- 事件：轨迹里的一步，也就是一段思考加上思考结束时的一个工具调用。`train.jsonl` 里 `event` 字段相同的行属于同一个事件。
- 行：一个事件在某个切点截断得到的一条样本，`text` 是截断到这个切点的题干，`label_call` 是调用串。一个事件有几个切点就有几行，`sent_idx` 是行在事件里的序号，从 0 数。
- 全文：一个事件里 `sent_idx` 最大那一行的 `text`，也就是思考写完整的题干。每一行的 `text` 都是全文的前缀。
- 目标串：一行要学着生成的东西。cgen 格是 `label_call` 加一个 eos。
- 尾巴：接在 `text` 后面、目标串前面的分隔串，cgen 格是 `"\n[CALL] "`（常量 `CALL_SEP`）。
- 公共前缀长度 `p`：一行的“`text` 加尾巴”分词之后，与全文分词结果从头数起相同的 token 个数。
- 目标段：一行在拼接序列里的那一截，等于尾巴的 token 加目标串的 token，只有目标串的 token 算损失。
- 拼接序列：一个事件的全文前缀加上全部行的目标段，一个事件一条。
- 逻辑小批：`--events-per-mb` 个事件（演示里是 4 个），损失按这一批所有行的权重求加权平均。
- 物理块：逻辑小批按 token 预算切出来的一组事件，一块过一次前向。
- 补齐长度：一个物理块里最长的拼接序列向上补到 16 的倍数，块内所有序列右侧都补到同一个补齐长度。
- 加性掩码：形状 `[块内事件数, 1, 补齐长度, 补齐长度]` 的矩阵，可看的位置是 0，不可看的位置是负无穷，加在注意力分数上。
- 一次更新：`--accum` 个逻辑小批（演示里是 2 个）的梯度累加之后做一次参数更新。
- 对齐检查：开训前把同一份数据分别按新路径（拼接序列一次前向）和参照路径（旧训练器逐行前向）算逐行损失，比较两者是否一致。
- 新路径与参照路径：对齐检查里的两条计算路线，新路径是本训练器，参照路径是旧训练器 `train_causal_callgen.py` 的 `collate` 加 `inst_ce`。

## 第 1 站：main() 先解析参数，定下学习率、种子和设备

位置：`pipeline/train/train_causal_share.py:858` 到 952，函数 `main()`。

第 859 到 935 行逐个登记命令行参数，第 936 行 `lora_util.add_args(ap)` 再挂上 `--lora` 一族参数，第 937 行解析。第 938 行 `lora_util.resolve_lr`（`pipeline/train/lora_util.py:53`）定学习率：命令行没有给 `--lr`，也没有开 `--lora`，所以取全参默认值 `train_causal_callgen.FULL_LR`，等于 1e-5。

第 940 到 942 行把 `train_causal_callgen.SEED`（等于 42）同时喂给 torch 和 random。第 945 到 948 行是一道门：`--out` 目录里已经有 `train_log.jsonl` 并且没有给 `--force`，就直接退出。launch.json 给了 `--force`，所以演示每次都能过这道门。第 950 到 952 行定设备：`dev` 是 `"cpu"`，`amp`（是否用 bf16 自动混合精度）是 False，`mask_dtype`（掩码的数据类型）是 float32。

停下来看什么：在第 954 行停下，调试控制台输入 `args` 能看到全部参数，`lr` 是 1e-05。

## 第 2 站：build() 加载分词器和小模型

位置：`pipeline/train/train_causal_share.py:954` 到 957 调用，函数体在 `pipeline/train/train_causal_callgen.py:216` 到 238。

第 954 行判断 `--base` 给的是名字还是路径：`"demo/tiny_qwen3"` 不在 `train_causal_callgen.MODELS`（qwen、qwen17、qwen4 三个名字）里，所以 `base_kw` 是 `dict(path="demo/tiny_qwen3")`。在第 956 行按 F11 进入 `build`。

`build` 的第 226 行取模型目录，第 227 行加载分词器，第 228 到 231 行把 pad 定成 eos、截断方向定成左截、补齐方向定成右补。演示的分词器是从真 Qwen3-0.6B-Base 拷贝来的，pad 和 eos 都是 151643。第 232 行再设一次种子，第 234 行 `AutoModelForCausalLM.from_pretrained` 用 float32 加载权重并且把注意力实现钉成 `sdpa`，终端会打印 `Loading weights: 100%|...| 24/24`。第 238 行返回分词器、模型（已经搬到 cpu）和模型路径。

停下来看什么：回到第 959 行，调试控制台输入 `sum(p.numel() for p in model.parameters())` 得到 9780928；`model.config` 里 `hidden_size` 64、`num_hidden_layers` 2、`num_attention_heads` 4、`num_key_value_heads` 2、`vocab_size` 151669；`model.model` 是 `Qwen3Model`（主干），`model.lm_head` 是输出层。这两个属性后面第 10 站会分开调用。

## 第 3 站：run_align_check() 证明打包前向与逐行前向算出同样的损失

位置：`pipeline/train/train_causal_share.py:963` 调用，函数体在第 681 到 853 行。

这一站是开训前的门：同一份验证事件分别按新路径和参照路径算逐行损失，两者的最大差要小于门槛，不然写报告然后 `sys.exit(2)`。按 F11 进入之后，下面按代码的先后顺序说。

第 688 行 `model.eval()`，第 692 行把 float32 矩阵乘法精度设成最高（对齐检查要拿 fp32 的结果做严格比较）。

第 698 行 `_align_candidates`（第 554 到 581 行）从 `val.jsonl` 里抽事件：先按 `event` 分组，每组取 `sent_idx` 最大的行的 `text` 当全文，全文 token 数不超过 2048（`ALIGN_LEN_FILTER`）的事件进候选，`random.Random(42).sample` 抽 `--align-events` 个。演示抽到 3 个事件：`appworld_demo/appworld_demo17_1_r0|s1`（6 行）、`appworld_demo/appworld_demo12_1_r0|s1`（4 行）、`appworld_demo/appworld_demo16_1_r0|s0`（3 行），一共 13 行。

第 701 行 `_write_align_tmpfile`（第 584 到 594 行）把这 13 行按 `(event, sent_idx)` 排序写进一个临时文件，文件名以 `kvshare_align_` 开头，放在系统临时目录，第 848 行会删掉。两条路径读同一个文件，所以行的顺序天然一致。

第 709 行用新路径的 `share_data.load_events` 装载第 701 行写出的临时文件（第 5 站详细讲 `load_events`），第 714 行用参照路径的 `train_causal_callgen.CallDS`（`pipeline/train/train_causal_callgen.py:118`）装载同一个临时文件。`CallDS` 每一行存成六元组 `(text, tgt, w, label_call, ready, has_lm)`，`tgt` 是 `label_call` 分词再加 eos。第 716 到 726 行核对两边的行数、行的顺序、丢弃计数是否一致。

第 728 行 `_ref_forward`（第 597 到 665 行）是参照路径的前向，4 行一批（`REF_BATCH`）。第 634 行调用旧训练器的 `collate`（`train_causal_callgen.py:181`）：每一行把 `text + CALL_SEP` 分词、左截到 `max_len - len(tgt)`，后面接上 `tgt`，`labels` 在题干部分是 -100、在目标部分是目标 token，批内右补齐。第 636 行整批过模型，拿到全部位置的 logits；第 638 到 641 行做“预测下一个 token”的错位：位置 `t-1` 的 logits 对应位置 `t` 的标签，只在标签不是 -100 的位置算交叉熵。第 653 行再调用一次旧训练器的 `inst_ce`（`train_causal_callgen.py:241`），拿到每行的平均交叉熵；第 654 到 661 行断言本地公式聚合的逐行结果与 `inst_ce` 的返回值相差不超过 1e-6，超过就抛 `RefBaselineDriftError`。第 730 行再用 1 行一批跑一遍 `_ref_forward`，得到“不补齐”的基线，用来判断补齐本身带来多大的差。

第 732 行 `_new_forward`（第 668 到 678 行）是新路径的前向：每个事件单独调用一次 `_forward_packed`（第 10 站）再用 `_aggregate_rows` 聚合成逐行结果。

第 734 到 763 行比较：`row_diff` 是逐行最大绝对差，`tok_diff` 是逐 token 最大绝对差，`baseline_diff` 是 4 行一批与 1 行一批之间的差，`ref_scale` 是参照路径逐行损失绝对值的平均数（相对判据的分母）。`--align-rule abs` 下 `abs_ok` 要求 `row_diff <= 2e-5` 并且 `tok_diff <= 3e-4`。第 767 行的 bf16 粗筛只在 cuda 上跑，CPU 上跳过，所以报告里两个 bf16 字段是 null。第 784 到 798 行写 `ALIGN_CHECK.json`，第 800 到 823 行 PASS 为假就退出。第 846 到 853 行的 `finally` 删临时文件、恢复矩阵精度、`model.train()`。

停下来看什么：在第 734 行停下，`row_new`、`row_ref`、`row_ref_solo` 是三个长度 13 的列表，`tok_new` 和 `tok_ref` 长度 161。演示的报告：`max_abs_diff` 0.0，`max_tok_diff` 9.5367431640625e-07，`baseline_max_abs_diff` 0.0，`ref_scale` 11.913296479445238，PASS true。

## 第 4 站：LoRA 和梯度检查点两个分支在演示里都不走

位置：`pipeline/train/train_causal_share.py:964` 到 990。

第 964 行 `--align-only` 没给，继续。第 967 行 `args.lora` 是 False，`lora_wrap` 是 None，模型全参训练。第 968 行 `--grad-ckpt` 没给，跳过。第 973 行 `model.train()`。第 975 到 979 行只读工具模式（`--readonly-env`）没开，三个变量都是 None。第 981 到 990 行不是 `--smoke`，所以 `order` 是 `"random"`，`n_tr` 和 `n_ev` 都是 0（不限事件数），`epochs` 是 2。

## 第 5 站：load_events() 把 jsonl 变成事件和行

位置：`pipeline/train/train_causal_share.py:992` 到 997 调用两次（训练集、验证集），函数体在 `pipeline/train/share_data.py:156` 到 334。

在第 992 行按 F11 进入。函数体分六段，顺序写死，原因写在第 159 到 162 行的注释里：随机数的消耗顺序决定抽样结果。

第一段（第 204 到 217 行）分组：逐行读 jsonl，按 `event` 分组，事件的顺序是文件里第一次出现的顺序，组内按 `sent_idx` 升序，全文取 `sent_idx` 最大那一行的 `text`。演示训练集得到 12 个事件。

第二段（第 220 到 223 行）抽查前缀性质：`random.Random(42)` 最多抽 50 个事件，断言每一行的 `text` 都是全文的前缀。演示只有 12 个事件，所以 12 个全查。

第三段（第 230 到 237 行）全文分词：`full_token_ids` 得到 `full_ids`，长度超过 `--max-len`（8192）的事件整条丢弃并计入 `dropped_events`。演示没有丢。

第四段（第 240 到 247 行）取子集：`limit` 是 0，跳过。

第五段（第 254 到 295 行）逐行分词，这是最要细看的一段，在第 263 行停下来按 F10 一行一行走。cgen 格：第 264 行 `tail` 是 `CALL_SEP`，第 265 行 `tgt_str` 是这一行的 `label_call`，第 267 到 269 行 `tgt_ids` 是 `label_call` 分词再加 eos。第 279 行目标超过 160 个 token（`MAX_TGT_TOK`）的行丢弃。第 282 行把 `text + tail` 整个分词得到 `old_ids`，第 284 行 `_lcp`（第 51 到 57 行）逐 token 比较 `old_ids` 与 `full_ids`，得到公共前缀长度 `p`，第 285 行 `tail_ids` 是 `old_ids` 从 `p` 开始往后的全部 token。第 290 到 291 行拼目标段：`seg_ids = tail_ids + tgt_ids`，`seg_lab` 在 `tail_ids` 的位置上是 -100、在 `tgt_ids` 的位置上是目标 token 本身。第 293 行把这一行存成七元组 `(sent_idx, text, p, seg_ids, seg_lab, w, gen)`，`gen` 是给生成式评估用的字典。

第六段（第 302 到 306 行）算事件级的两个长度：`prefix_len` 是所有行 `p` 的最大值，`packed_len` 是 `prefix_len` 加上所有目标段的长度之和。第 309 到 330 行是三道硬停（0 行、cparam 剥离失败率、拼接长度超上界），第 332 到 334 行返回事件列表和计数。

停下来看什么，以训练集第一个事件 `appworld_demo/appworld_demo00_1_r0|s1` 为例（在第 304 行停下，条件断点表达式填 `e["event"].endswith("demo00_1_r0|s1")`）。全文 147 个 token（`n_full`），4 行的 `p` 分别是 109、123、136、146，`prefix_len` 146，每行的目标段都是 15 个 token（尾巴 5 个加目标 10 个），`packed_len` 等于 146 加 4 乘 15 等于 206。目标串四行相同，都是 `apis.todoist.show_tasks(status=pending)`，`w` 都是 0.25。

第 285 行的 `tail_ids` 有一个值得在断点上亲眼看一下的细节。`CALL_SEP` 单独分词是 5 个 token（`[198, 58, 25427, 60, 220]`），但是第一行的 `tail_ids` 解码出来是 `."\n\n[CALL] `，尾巴把 `text` 末尾的 `."` 也包了进来。原因是 `text` 的末尾字符和分隔串连在一起分词的时候，边界处的 token 与全文里的 token 不一样，所以公共前缀在 `."` 之前就断了，`p` 是 109 而不是 `text` 自己的 token 数。这就是第 284 行要逐 token 比较而不是数 `text` 的 token 数的原因。最后一行（`sent_idx` 3）的 `p` 是 146，比全文的 147 少 1，同样是边界处重新分词造成的。

训练集装完是 12 个事件 61 行，验证集 6 个事件 27 行，四个丢弃计数全是 0，这四个数会写进 `train_log.jsonl` 的 `start` 记录。

## 第 6 站：sample_gen_eval_rows() 抽出生成式评估要用的 4 行

位置：`pipeline/train/train_causal_share.py:999` 调用，函数体在第 245 到 263 行。

第 257 行把验证集 6 个事件的 27 行摊平成一个列表，第 258 到 260 行 `random.Random(42).shuffle` 之后取前 `--gen-eval` 个（4 个），第 262 行每行打包成 `(text, None, None, tgt)`。演示抽到的 4 个目标串依次是 `apis.phone.send_message(phone_number=555-0134, message=Please get on venmo.)`、`apis.venmo.show_account()`、`apis.venmo.show_account()`、`apis.supervisor.show_profile()`。

## 第 7 站：算出更新次数，建优化器和学习率计划，写 start 记录

位置：`pipeline/train/train_causal_share.py:1015` 到 1063。

第 1015 行评估用的 token 预算是训练预算的 2 倍，等于 1536。第 1017 行 `max_tgt_tok` 取 cgen 的 160。第 1020 到 1023 行算更新次数：`M`（一个 epoch 的逻辑小批数）是 12 除以 4 向上取整等于 3，`U`（一个 epoch 的更新次数）是 3 除以 2 向上取整等于 2，`steps` 是 2 乘 2 个 epoch 等于 4。

第 1025 到 1027 行：`lora_util.opt_params` 不开 LoRA 时原样返回全部参数（24 个张量），`AdamW` 学习率 1e-5、权重衰减 0.01，`get_linear_schedule_with_warmup` 的预热步数是 `int(4 * 0.05)` 等于 0，总步数 4。线性学习率计划在第 `s` 次 `sch.step()` 之后把学习率乘以 `(4 - s) / 4`，所以四次更新实际用的学习率依次是 1e-5、7.5e-6、5e-6、2.5e-6。`train_log.jsonl` 里 step 记录的 `lr` 字段是在 `sch.step()` 之后读的（第 1147 行），所以第 1 步记的是 7.5e-6，第 4 步记的是 0.0，记的都是下一步要用的值。

第 1029 行用追加模式打开 `train_log.jsonl`，所以带 `--force` 重跑之后旧记录还在，文件里会有两次运行的记录。第 1031 到 1035 行的 `log()` 每次写一行 JSON 并且打印到终端。第 1037 到 1062 行写 `start` 记录，字段是本站算出的设置、第 1 站的参数和第 3 站对齐检查的结果。第 1063 行 `heartbeat.emit(0, 4, "step")`（`ops/heartbeat.py:17`）往标准输出打一行以 `@hb ` 开头的 JSON，给集群上的采样器判活用，演示里没有采样器在读，可以不管。

## 第 8 站：每个 epoch 先打乱事件、切逻辑小批、定评估点

位置：`pipeline/train/train_causal_share.py:1092` 到 1111。

第 1093 行 `share_data.epoch_minibatches`（`pipeline/train/share_data.py:453` 到 464）：复制事件列表，`random.Random(42 + ep).shuffle` 打乱，每 4 个切成一个逻辑小批。演示 epoch 0 的三个逻辑小批依次是（只写事件编号）demo07、demo05、demo02、demo08；demo09、demo06、demo11、demo03；demo04、demo00、demo01、demo10。epoch 1 换种子 43 重新打乱，顺序不同。

第 1101 到 1104 行定评估点：`k` 从 1 到 `E`（`--eval-per-epoch`，等于 2），评估点 `p = ceil(U * k / E)`，得到字典 `{1: 1, 2: 2}`，意思是每个 epoch 里第 1 次更新之后评估一次（`frac` 1），第 2 次更新之后再评估一次（`frac` 2）。第 1106 到 1111 行是这一个 epoch 的计数器归零。

## 第 9 站：一次参数更新是两个逻辑小批的梯度累加

位置：`pipeline/train/train_causal_share.py:1112` 到 1134。

第 1113 到 1115 行从逻辑小批列表里取一组：`group_size` 取 `--accum`（2）和剩余逻辑小批数两者中较小的值，所以 epoch 里第一组是 2 个逻辑小批，第二组只有 1 个，`n_g` 跟着变成 1。`n_g` 后面会除进损失里，保证不满组的时候梯度的尺度和满组一样。

第 1118 到 1127 行对组里每个逻辑小批做三件事。第 1119 行 `W` 是当前逻辑小批全部行的权重之和，一个事件的行权重加起来是 1（`w` 等于 1 除以行数），4 个事件所以 `W` 约等于 4（差在 `w` 四舍五入到 6 位小数）。第 1120 行 `share_data.chunk_by_budget`（`pipeline/train/share_data.py:467` 到 496）切物理块：事件按 `packed_len` 降序排，贪心装块，判据是“块内事件数 乘 补齐长度”不超过 `--tok-budget`（768）。演示 epoch 0 第一个逻辑小批的四个 `packed_len` 是 349、238、236、203：前两个补齐到 352，2 乘 352 等于 704 不超过 768，放进第一块；再加第三个变成 3 乘 352 等于 1056 超了，所以第三、第四个另起一块（补齐到 240）。三个逻辑小批各切成 2 块。epoch 1 的第二个逻辑小批是 239、236、203、137，前三个 3 乘 240 等于 720 放在同一块，137 单独一块。

第 1121 行 `backward_logical_minibatch`（第 178 到 213 行）按 F11 进入：第 205 行遍历物理块，第 207 行 `block_row_ce`（第 10 站）算出这一块每行的平均交叉熵 `ce_per_row` 和每行的权重 `w`，第 208 行 `loss_c` 是加权求和再除以整个逻辑小批的 `W`，第 210 行 `(loss_c / n_g).backward()` 反向。几个物理块的梯度就这样累加在参数的 `.grad` 上，再和组里另一个逻辑小批的梯度累加。第 211 到 212 行把 `loss_c` 累加进当前逻辑小批的损失，把行数累加。

回到 `main()`，第 1128 行 `clip_grad_norm_` 把整体梯度范数裁到 1.0，返回裁剪前的范数，`train_log.jsonl` 里 `grad_norm` 记的就是裁剪前的范数（第 1 步是 2.1414，大于 1.0，所以这一步梯度被缩小到原来的 1 除以 2.1414）。第 1129 行 `opt.step()` 更新参数，第 1130 行 `sch.step()` 推进学习率计划，第 1131 行梯度清零，第 1132 行 `gstep` 加 1。

停下来看什么：第 1121 行停下，`len(group)`、`n_g`、`W`、`[[ev["packed_len"] for ev in b] for b in blocks]`。第 1128 行停下，`gstep`、`sch.get_last_lr()`，再按 F10 跨过第 1130 行之后重新看 `sch.get_last_lr()`。

## 第 10 站：_forward_packed() 把一个物理块拼成序列、构建掩码、算逐 token 交叉熵

位置：`pipeline/train/train_causal_share.py:169` 到 175 的 `block_row_ce`，第 123 到 157 行的 `_forward_packed`，第 160 到 166 行的 `_aggregate_rows`；拼接和掩码在 `pipeline/train/share_data.py:339` 到 450。

这一站是本训练器与旧训练器的差别所在，值得把每一行都走一遍。以第 5 站的事件 demo00 为例，先用一个只有这一个事件的块来理解，再看真实的块。

第 135 行对块内每个事件调用 `share_data.pack_event`（`share_data.py:339` 到 369）。拼接序列 `tokens` 是全文的前 `prefix_len` 个 token 再接上每一行的目标段，demo00 是 146 加 4 乘 15 等于 206 个 token。`positions` 是每个 token 的位置号：前缀是 0 到 145，第 `k` 行的目标段从这一行自己的 `p` 开始接着数，四段的起点分别是 109、123、136、146。这样第 `k` 行的目标段看到的位置号和旧训练器里“`text` 加尾巴加目标”单独分词时完全一样。`labels` 前缀部分全是 -100，目标段部分是 `seg_lab`。`row_index` 标每个 token 属于第几行，前缀是 -1。`seg_bounds` 是每一段在 `tokens` 里的半开区间，demo00 是 `[(146, 161), (161, 176), (176, 191), (191, 206)]`。

第 136 行 `_l_pad` 把块内最长的拼接序列补到 16 的倍数，demo00 单独成块时是 208。第 137 行 `share_data.batch_mask`（`share_data.py:402` 到 450）构建四样东西。`input_ids` 形状 `[块内事件数, 补齐长度]`，补齐位填 0。`position_ids` 补齐位从所属事件最后一个真实位置号接着数。`mask` 由 `_allowed_from_packed`（`share_data.py:372` 到 393）决定，三条规则合起来：前缀内部是普通的因果注意力（只看自己和前面的）；目标段里的 token 只看同一行里自己和前面的 token；目标段里的 token 还能看前缀里位置小于这一行 `p` 的 token。段与段之间互相看不见，前缀看不见任何目标段。补齐位作为 query 只看自己（整行都不可看会让 softmax 出 NaN）。可看的位置填 0，不可看的填负无穷。`loss_idx` 列出每个要算损失的目标 token：`labels[t]` 不是 -100 的时候，记 `(事件下标, t - 1, labels[t], row_index[t])`，意思是位置 `t - 1` 的隐状态负责预测位置 `t` 的 token，这和参照路径第 638 到 639 行的错位是同一件事。

停下来看什么（在 `share_data.py:450` 停下，条件断点表达式填 `len(packed_list) == 1 and len(packed_list[0][0]) == 206`）。`input_ids.shape` 是 `(1, 208)`，`mask.shape` 是 `(1, 1, 208, 208)`，`len(loss_idx)` 是 40（4 行乘 10 个目标 token），`loss_idx[0]` 是 `(0, 150, 13725, 0)`（位置 150 是第一行目标段里尾巴的最后一个 token，13725 是目标串的第一个 token），`loss_idx[-1]` 是 `(0, 204, 151643, 3)`（第四行的 eos）。`(mask[0, 0] == 0).int()` 是 0/1 矩阵，`(mask[0, 0] == 0).int().sum(1)` 是每个位置能看到的 token 数：前缀第 `i` 个位置看到 `i + 1` 个；四段的第一个 token 分别看到 110、124、137、147 个，等于各自的 `p` 加 1。

回到 `_forward_packed`。第 138 到 140 行把三样东西搬到设备上，掩码转成 `mask_dtype`（CPU 上是 float32）。第 141 行 `_base_model_and_head` 取出主干 `model.model` 和输出层 `model.lm_head`。第 143 行只调用主干，传入 `input_ids`、加性掩码、`position_ids`，`use_cache=False`，拿到 `last_hidden_state`，形状 `[块内事件数, 补齐长度, 64]`。第 146 到 148 行按 `loss_idx` 取出批下标、query 位置、目标 id 三个张量，第 149 到 153 行把每个目标 token 的行号换算成块内的全局行号（第一个事件的行在前，第二个事件的行接着数）。第 154 行只在损失位置取隐状态，第 155 行只对损失位置过输出层得到 logits，形状 `[目标 token 数, 151669]`，不算全部位置的 logits。第 156 行逐 token 交叉熵，第 157 行返回 `ce`、`global_row`、块内总行数。

第 172 行 `_aggregate_rows` 用 `index_add` 按行号求和再除以每行的 token 数，得到每行的平均交叉熵，与 `inst_ce` 的口径相同。第 173 行取出每行的权重 `w`。

真实的块是什么样：演示 epoch 0 第一个逻辑小批的第一块是 `packed_len` 349 和 238 的两个事件（各 5 行），补齐长度 352，`input_ids.shape` 是 `(2, 352)`，`mask.shape` 是 `(2, 1, 352, 352)`，第 157 行的 `ce.shape` 是 `(170,)`（170 个目标 token），块内 10 行，`global_row` 的取值是 0 到 9。

第 138 行的断点第一次停下来是在第 3 站的对齐检查里（`events` 只有 1 个事件），第 13 站的评估也经过第 138 行。只想看训练里的前向，给断点加条件 `model.training`：对齐检查和评估都在 `model.eval()` 下运行，只有训练循环在 `model.train()` 下运行。

## 第 11 站：掩码和 position_ids 进入 transformers 之后走到哪里

位置：在 `pipeline/train/train_causal_share.py:143` 按 F11。这一站可以跳过，只有想确认“训练器构建的掩码真的被注意力层原样用了”的时候才需要。

进入 `Qwen3Model.forward`（`cprobe-env/lib/python3.11/site-packages/transformers/models/qwen3/modeling_qwen3.py:378`）。第 392 行查词嵌入。第 397 行的 `if position_ids is None` 不成立，训练器给的位置号保留。第 403 到 415 行调用 `create_causal_mask`（`transformers/masking_utils.py:871`），`create_causal_mask` 第 936 行调用 `_preprocess_mask_arguments`（第 767 行），第 818 行判断传进来的掩码是四维张量，直接原样返回，第 939 到 940 行提前退出。所以训练器的加性掩码一个数都没有被改。第 421 行用 `position_ids` 算旋转位置编码，训练器让每个目标段从自己的 `p` 接着数位置号，在第 421 行起作用。第 423 到 432 行依次过 2 层 `Qwen3DecoderLayer`。

`Qwen3DecoderLayer.forward`（第 305 行）是标准的“归一化、注意力、残差、归一化、MLP、残差”。`Qwen3Attention.forward`（第 252 行）：第 263 到 265 行算 q、k、v 并且对 q、k 做归一化，第 268 行加旋转位置编码，第 273 到 275 行按 `config._attn_implementation`（`sdpa`）选注意力函数，第 277 行调用。

注意力函数是 `sdpa_attention_forward`（`transformers/integrations/sdpa_attention.py:79`）。第 97 到 100 行：4 个查询头对 2 个键值头，`use_gqa_in_sdpa`（第 28 到 38 行）在传了掩码的情况下返回 False，所以键和值被 `repeat_kv` 复制成 4 个头。第 120 行 `is_causal` 变成 False，原因是掩码不为空，因果关系全部由掩码表达。第 154 到 163 行调用 `torch.nn.functional.scaled_dot_product_attention`，`attn_mask` 就是训练器的加性掩码。CPU 上 `_attn_ctx`（`train_causal_share.py:98`）返回空上下文，内核由 torch 自己选。

## 第 12 站：每次更新写一条 step 日志

位置：`pipeline/train/train_causal_share.py:1136` 到 1152。

`--log-every 1`，所以每次更新都写。第 1137 行 `loss` 是这一组里各逻辑小批 `loss_c` 的平均（第 1 步是 11.931）。第 1138 到 1142 行是吞吐：`ips` 是当前 epoch 到现在每秒处理的行数，`ips_win` 是上一条日志以来的每秒行数，`eps` 是每秒事件数。第 1143 行 `_peak_gb` 在 CPU 上恒为 0.0。第 1146 到 1149 行写记录，`rows` 是当前 epoch 累计的行数（第 1 步 42，第 2 步 61），`lr` 是下一步的学习率（第 7 站说明过），`grad_norm` 是裁剪前的梯度范数。第 1150 行再打一行心跳。

演示四次更新的 `loss` 依次是 11.931、11.9355、11.9387、11.9094，都在 `ln(151669)` 等于 11.929 附近。11.929 是在 151669 个词上均匀分布的交叉熵，随机初始化的模型算出的损失就落在均匀分布的交叉熵附近。

## 第 13 站：eval_ce() 和 eval_gen() 在评估点上给出 val_ce 和命中率

位置：`pipeline/train/train_causal_share.py:1154` 到 1175，`eval_ce` 在第 217 到 242 行，`eval_gen` 在 `pipeline/train/train_causal_callgen.py:309` 到 332。

第 1154 行 `u`（当前 epoch 已完成的更新次数）在评估点字典里才评估，`frac` 是对应的序号。第 1156 行 `eval_ce` 按 F11 进入：第 226 行 `model.eval()`，第 228 行用 1536 的预算给验证集 6 个事件切块，演示切成两块，第一块是 `packed_len` 281、247、237、209、166 的五个事件（补齐到 288，5 乘 288 等于 1440 不超过 1536，再加一个就超了），第二块只有 108 的那一个事件。第 231 到 234 行每块调用 `block_row_ce`，分子累加“每行交叉熵乘权重”，分母累加权重，第 242 行返回加权平均，这就是 `val_ce`。第 237 行切回 `model.train()`。演示四次评估的 `val_ce` 依次是 11.9023、11.9013、11.9006、11.9003。

第 1160 到 1161 行决定这次评估做不做生成：`--gen-eval-at last`，只有 `frac` 等于 `E`（epoch 末）的那次才做，所以每个 epoch 做一次。第 1165 行 cgen 格用 `train_causal_callgen.eval_gen`：第 313 到 314 行把补齐方向临时改成左补、打开 kv 缓存（生成必须这样），第 316 到 320 行每 `--gen-bs`（2）行一批，把 `text + CALL_SEP` 分词、左截到 `max_len - 96`，第 322 行 `model.generate` 贪心生成最多 96 个新 token（`MAX_GEN_TOK`），遇到 eos 停，第 326 到 329 行解码新生成的部分，取第一行去掉首尾空白，与目标串逐字符比较，相同算命中。第 330 到 332 行恢复补齐方向和缓存设置，返回命中率。演示 4 行都不命中，`val_exact_call` 是 0.0，记录里 `gen_n` 是 4，`gen_s` 是生成用的秒数。

## 第 14 站：val_ce 创新低就保存 best/

位置：`pipeline/train/train_causal_share.py:1176` 到 1206。

第 1176 行 `vce < best`，`best` 初始是正无穷，所以第一次评估一定保存。第 1179 到 1185 行：不开 LoRA 时 `model.save_pretrained(out / "best")` 写 `config.json`、`generation_config.json`、`model.safetensors`，`tok.save_pretrained` 写分词器的四个文件。第 1186 到 1204 行写 `meta.json`，记录底座、数据目录、种子、epoch、`frac`、`gstep`、三个批设置和注意力实现。第 1205 行写 `save_best` 记录。演示四次评估的 `val_ce` 一次比一次低，所以四次都保存，`best/` 最终是第 4 步之后的权重，`meta.json` 里 `epoch` 1、`frac` 2、`gstep` 4。

## 第 15 站：done 记录和心跳收尾

位置：`pipeline/train/train_causal_share.py:1208` 到 1211。

写 `done` 记录：`best_val_ce` 11.9003，`best_ep` 1，`best_frac` 2，`total_rows` 122（两个 epoch 各 61 行），`wall_s` 是从第 1065 行到第 1208 行的秒数（两次运行分别是 5.41 和 5.63 秒）。最后一行心跳带 `status="done"`。程序结束。

## cparam 格与 cgen 格只在五处不同

选择 launch.json 里的第二个配置就是 cparam 格，同一个训练器，`--mode cparam`。差别在这五处。

第一处在 `share_data.py:270` 到 278：尾巴是 `param_prompt_tail(label)`，等于 `CALL_SEP + label + "("`（`train_causal_param.py:89`）；目标串是 `param_target(label, label_call)`（`train_causal_param.py:94`），把 `label_call` 开头的 `label + "("` 剥掉，剩下的参数部分连同右括号做目标；剥不掉的行丢弃并计入 `assembly_mismatch`。也就是说 cparam 格把工具名放进题干，只学参数。第二处在 `train_causal_share.py:1017` 到 1018，目标长度上限取 `train_causal_param.MAX_TGT_TOK`，数值同样是 160。第三处在第 1165 到 1166 行，生成式评估用 `train_causal_param.eval_gen`（`train_causal_param.py:235`），提示用 `param_prompt_tail` 拼，比较的是元组第 5 位的参数串。第四处在对齐检查第 712 到 714 行，参照路径用 `ParamDS`，第 725 到 726 行多核对一项 `assembly_mismatch` 计数。第五处是记录：`start` 记录多两个 `assembly_mismatch` 字段（第 1057 到 1059 行），`meta.json` 多一个 `param_only`（第 1201 到 1202 行）。

## 假件是 prepare.py 用标注段的真函数构建出来的

读训练器不需要读 `demo/prepare.py`，但是想知道假数据里每个字段怎么来的可以看这四个函数。`_synth_event`（`demo/prepare.py:135` 到 153）随机选一条任务、一个工具、零到两轮历史，拼出一段思考，第一句是任务转述、最后一句点名工具。`make_rows`（第 156 到 175 行）逐字段照 `pipeline/annotate/build.py` 的 `make_samples`：切点用 `rules.boundaries`，题干用 `rules.assemble`，调用串用 `build.make_call`，`w` 等于 1 除以切点数。`write_data`（第 178 到 195 行）用种子 20260907 写 12 个训练事件和 6 个验证事件。`write_model`（第 198 到 223 行）用 `Qwen3Config` 建两层、hidden 64 的模型，`torch.manual_seed` 之后 `from_config` 随机初始化，和真分词器一起保存。`self_check`（第 226 到 256 行）用训练器自己的 `build`、`load_events`、`chunk_by_budget` 把假件装一遍并打印长度和装块数。
