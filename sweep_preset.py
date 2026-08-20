"""参数网格 -> 一批预设文件。一条命令把「同一个实验换一组生成设置」要用的
N 份预设一次生成好,每份都是 configs/presets/ 里的真实文件:进 git、可追溯、
run_id 带预设名(DATA.md 检查清单第 9 条),发射前脏树门禁自动逼 commit。

不发射、不占卡:生成完打印每个点的 --preset 用法,GPU 发射照旧走 gpu-run。
θ 扫描是另一回事(pipeline/inject/sweep_theta.py,任务名 sweep-run/sweep-curve),
这里扫的是采样设置(temperature/top_p/max_tokens/seed/reasoning_effort)。

用法:
  python3 run.py preset-sweep --base gptoss_default --grid temperature=0.2,0.7,1.0
  python3 run.py preset-sweep --base gptoss_default \
      --grid temperature=0.7,1.0 --grid top_p=0.9,1.0     # 笛卡尔积 4 份
生成名 <base>__<键><值>[__<键><值>...];已存在拒绝覆盖,--force 放行,
--dry-run 只打印不落盘。
"""

import argparse
import copy
import itertools
import json
import sys
import time
from pathlib import Path

import preset_loader as PL

# 允许进网格的键:只有采样设置。api/start_date 是口径开关不是采样旋钮,
# stop 是列表拼不进文件名——要扫它们就手开预设,别走网格。
SWEEPABLE = ("temperature", "top_p", "max_tokens", "seed", "reasoning_effort")


def parse_grid(spec):
    """"temperature=0.2,0.7" -> ("temperature", [0.2, 0.7]);值按 CLIENT_KEYS
    的期望类型转,转不动就报错退出。"""
    key, sep, raw = spec.partition("=")
    if not sep or not raw:
        raise SystemExit(f"--grid 要写成 键=值,值,...(现在是 {spec!r})")
    if key not in SWEEPABLE:
        raise SystemExit(f"--grid 只认采样键 {SWEEPABLE},不认 {key!r}"
                         "(api/start_date/stop 要扫就手开预设)")
    want = PL.CLIENT_KEYS[key]
    vals = []
    for v in raw.split(","):
        v = v.strip()
        try:
            vals.append(int(v) if want is int
                        else float(v) if isinstance(want, tuple) else v)
        except ValueError:
            raise SystemExit(f"--grid {key} 的值 {v!r} 转不成 {want}")
    return key, vals


def expand(grids):
    """[(键, 值列表), ...] -> 笛卡尔积的点列表,每个点是 {键: 值}。
    顺序钉死:按 --grid 出现顺序为轴,后一个轴转得快。"""
    keys = [k for k, _ in grids]
    return [dict(zip(keys, combo))
            for combo in itertools.product(*(vs for _, vs in grids))]


def point_name(base, point):
    """gptoss_default + {temperature: 0.2} -> gptoss_default__temperature0.2。
    键写全名不缩写:预设名就是口径说明,缩了别人读不懂。"""
    return base + "".join(f"__{k}{v}" for k, v in point.items())


def make_preset(base_dict, base_name, point):
    """在 base 预设的 json 上盖网格点,desc 重写成可追溯的一句话。"""
    p = copy.deepcopy(base_dict)
    p.setdefault("client", {})
    p["client"].update(point)
    kv = ",".join(f"{k}={v}" for k, v in point.items())
    p["desc"] = (f"sweep 点:{base_name} 基础上 {kv};由 run.py preset-sweep 生成"
                 f"({time.strftime('%Y-%m-%d')}),改口径重新生成,不手改")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True,
                    help="configs/presets/ 里的基础预设名")
    ap.add_argument("--grid", action="append", required=True,
                    metavar="键=值,值,...",
                    help=f"可重复,多条取笛卡尔积;键限 {SWEEPABLE}")
    ap.add_argument("--out-dir", default=str(PL.PRESET_DIR),
                    help="落盘目录(缺省 configs/presets/;测试用)")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的同名预设")
    ap.add_argument("--dry-run", action="store_true", help="只打印不落盘")
    a = ap.parse_args(argv)

    # 基础预设过一遍完整校验(load_preset 会做);写盘用原始 json,
    # 不用 load_preset 的返回——那份带 _name/_path 两个运行时字段
    PL.load_preset(a.base)
    base_dict = json.loads((PL.PRESET_DIR / f"{a.base}.json").read_text())

    grids = [parse_grid(s) for s in a.grid]
    dup = {k for k, _ in grids if sum(1 for kk, _ in grids if kk == k) > 1}
    if dup:
        raise SystemExit(f"同一个键给了两条 --grid: {sorted(dup)}")

    out_dir = Path(a.out_dir)
    models = PL.load_models()
    plans = []
    for point in expand(grids):
        name = point_name(a.base, point)
        preset = make_preset(base_dict, a.base, point)
        errs = PL.validate(preset, models)
        if errs:
            raise SystemExit(f"生成的预设 {name} 不合格:\n" + "\n".join(errs))
        path = out_dir / f"{name}.json"
        if path.exists() and not a.force:
            raise SystemExit(f"{path} 已存在;换 --base/--grid 或 --force 覆盖"
                             "(覆盖会改已入库口径,想清楚)")
        plans.append((name, path, preset))

    for name, path, preset in plans:
        if not a.dry_run:
            path.write_text(json.dumps(preset, ensure_ascii=False, indent=2)
                            + "\n")
        print(f"{'DRY ' if a.dry_run else ''}{path}  <- {preset['desc']}")
    print(f"\n{'会生成' if a.dry_run else '生成'} {len(plans)} 份预设。"
          "接下来三步:")
    print("1. git add configs/presets && commit(发射类任务的脏树门禁会拦未提交的)")
    print("2. 逐点跑:同一条任务命令换 --preset <名>;GPU 发射走 gpu-run")
    print("3. run_id 带上预设名(DATA.md 检查清单第 9 条),N 个点 N 个 run_id")
    return 0


if __name__ == "__main__":
    sys.exit(main())
