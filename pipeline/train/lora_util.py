"""LoRA 适配器:三个因果训练脚本(ctool/cgen/cparam)共用的旗标、包装与合并。

三个脚本的 `--lora` 一族旗标、七件套 target modules、合并落盘的做法都从这一份
出,别处不许再抄一份(同构表必漂移,而那种漂移是静默的)。

**peft 是懒依赖**:本模块顶上不 import peft,所有 peft 的 import 都写在函数体
内部,而那些函数只在 `--lora` 分支里被调用。不传 `--lora` 时本模块与三个训练
脚本自己都不碰 peft。

⚠️ 但"进程里没有 peft"这句话不成立,而且不由我们决定:transformers 5.14.1 的
`trainer_utils.py` 第 66 行在环境里装了 peft 时会 `from peft import PeftModel`,
三个脚本 import 的 `get_linear_schedule_with_warmup` 正好经 `optimization.py`
走到那一行。所以 cprobe-env 里装上 peft 之后,不传 `--lora` 也会把 peft 拉进
sys.modules——那是 transformers 自己的链,与本模块的分支无关,也不改任何数值。

**存档契约不变**是这套东西的硬约束:LoRA 训完不落适配器,而是先 `merge_and_unload`
把适配器并回底座,再按各格原来的方式 `save_pretrained`。所以评测端零改动——
`best/` 下的文件与全参训练存的逐项同构。

**为什么合并要先深拷一份**:`merge_and_unload()` 是就地拆的(把 lora 权重加进
base_layer、再把 lora.Linear 换回 nn.Linear),原件当场失去适配器。而三个脚本
都是"每轮评估后按指标存 best、然后接着训下一轮",原件还要继续训,所以只能拿
深拷的副本去合并。副本用完立刻释放。
"""

# Qwen3 的标准七件:注意力四件 + MLP 三件
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                  "gate_proj", "up_proj", "down_proj"]

DEFAULT_RANK = 16
DEFAULT_ALPHA = 32
DEFAULT_DROPOUT = 0.05
DEFAULT_LR = 2e-4          # 开 --lora 时替掉全参 lr 的默认值


def add_args(ap):
    """把 `--lora` 一族挂到 argparse 上(三个脚本共用同一套名字与默认值)。"""
    g = ap.add_argument_group("LoRA")
    g.add_argument("--lora", action="store_true",
                   help="用 LoRA 训底座(只训适配器,存档前合并回底座;"
                        "默认关=全参微调,行为与加这套旗标之前一致)")
    g.add_argument("--lora-rank", type=int, default=DEFAULT_RANK,
                   help=f"LoRA 秩 r(默认 {DEFAULT_RANK})")
    g.add_argument("--lora-alpha", type=int, default=DEFAULT_ALPHA,
                   help=f"LoRA 缩放 alpha(默认 {DEFAULT_ALPHA})")
    g.add_argument("--lora-dropout", type=float, default=DEFAULT_DROPOUT,
                   help=f"LoRA dropout(默认 {DEFAULT_DROPOUT})")
    g.add_argument("--lora-lr", type=float, default=DEFAULT_LR,
                   help=f"开 --lora 时的学习率(默认 {DEFAULT_LR});"
                        "命令行显式给了 --lr 就以 --lr 为准")


def resolve_lr(args, full_default):
    """定学习率:显式 `--lr` 最大,其次 `--lora` 用 `--lora-lr`,再其次全参默认。

    三个脚本的 `--lr` 默认值改成 None 就是为了分得清"没传"与"传了个跟默认
    一样的值"——不然开 `--lora` 时没法知道该不该用 `--lora-lr`。
    """
    if args.lr is not None:
        return args.lr
    return args.lora_lr if args.lora else full_default


def wrap(hf_model, args):
    """就地给 hf_model 注入 LoRA 适配器,返回 peft 包装(只留给合并用)。

    `get_peft_model` 是**就地**注入:hf_model 这个对象本身的七类 nn.Linear 被
    换成 lora.Linear,非适配器参数一律 requires_grad=False。所以调用方原来那个
    变量继续照常用(forward / generate / config / gradient_checkpointing 全不变),
    只有存档改走 `save_merged()`。返回的包装除了合并没有别的用途。
    """
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(
        r=args.lora_rank, lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=list(TARGET_MODULES), bias="none")
    return get_peft_model(hf_model, cfg)


def merged_copy(wrapped):
    """深拷一份 peft 包装再 `merge_and_unload`,返回合并好的 HF 模型。

    原件不动(还要接着训),返回的副本是普通 HF 模型,`save_pretrained` 出来的
    文件与全参训练存的逐项同构。用完调用方自己 del 掉——正常走 `save_merged()`。
    """
    import copy
    return copy.deepcopy(wrapped).merge_and_unload()


def save_merged(wrapped, dest, dev):
    """合并副本存到 dest,存完当场扔掉并把显存还回去(三个脚本的存档入口)。

    副本必须在这个函数里就地释放:调用方要是拿着它跨轮次不放,下一轮再合并时
    显存里会同时躺三份底座(原件 + 上一份副本 + 新副本),4B 在 48G 卡上直接爆。
    """
    merged = merged_copy(wrapped)
    merged.save_pretrained(dest)
    del merged
    if str(dev).startswith("cuda"):
        import torch
        torch.cuda.empty_cache()


def prepare_grad_ckpt(hf_model):
    """LoRA + gradient checkpointing 的必要一步:让 embedding 输出 require_grad。

    checkpoint 段里没有一个输入 require_grad 时整段不建图,LoRA 参数收不到梯度
    而且**不报错**(全参训练撞不上这条,因为 embedding 本身就可训)。

    transformers 5.14.1 的 `gradient_checkpointing_enable()` 在 main_input_name
    是 input_ids 时已经自己调了一次(modeling_utils.py 第 3353-3361 行),所以
    这里只是补一道保险;已经挂过钩子就不重复挂(重复挂会把旧钩子的句柄丢掉)。
    """
    if getattr(hf_model, "_require_grads_hook", None) is not None:
        return
    if hasattr(hf_model, "enable_input_require_grads"):
        hf_model.enable_input_require_grads()


def opt_params(params, use_lora):
    """进优化器的参数表:开 LoRA 时只收 requires_grad 的(适配器 + 各格自己的头)。

    不开 LoRA 时原样返回,顺序不变——AdamW 的状态是按顺序建的,顺序变了
    等于换了一次实验。
    """
    ps = list(params)
    return [p for p in ps if p.requires_grad] if use_lora else ps


def meta_block(args, lr):
    """meta.json 里的 "lora" 块;不开 `--lora` 时调用方根本不写这个键。"""
    return dict(rank=args.lora_rank, alpha=args.lora_alpha,
                dropout=args.lora_dropout, lr=lr,
                target_modules=list(TARGET_MODULES))
