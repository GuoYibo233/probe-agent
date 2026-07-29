# C3 任务对生成脚本 —— 冒烟报告(T12a 脚本部分,2026-07-30)

规范:`benchmark_design/L3L4_and_metrics_draft.md` §1(L3 组合相似)/ §2(L4 假相似)。
本轮交付三个生成脚本 + 本报告,全部纯 CPU、零 GPU 进程、零 API 调用。

**随机种子固定 20260729**(三个脚本的 `--seed` 默认值)。三个脚本都做过重跑一致性验证,
同参数两次运行输出 **md5 逐字节相同**;ALFWorld 脚本还验证了 `--workers 1` 与 `--workers 8`
输出相同(见下面「坑 1」)。

## 0. 交付清单

| 文件 | 作用 | 跑它的 venv |
|---|---|---|
| `gen_l4_alfworld.py` | L4 位置改换对(§2.2 第 1 类),真引擎回放验证 | `fig1_pilot/fig1-env` |
| `gen_l4_2wiki.py` | L4 极性翻转(§2.3 第 1 类)+ 易混实体替换(§2.3 第 2 类) | `jlens-env` |
| `gen_l3_2wiki.py` | L3 两跳拼接(§1.3 第 1 类) | `jlens-env` |
| `GEN_REPORT.md` | 本报告 | — |

本轮跑出来的数据(同目录,不进 git):

| 数据文件 | 条数 | 说明 |
|---|---|---|
| `l4_alfworld_pairs.jsonl` | 10 | 冒烟:单模板 `pick_and_place_simple` |
| `l4_alfworld_pairs_wide800.jsonl` | 259 | 全模板 800 候选对的抽样,用于规模与档位估计 |
| `l4_2wiki_pairs.jsonl` | 6494 | 极性翻转 1690 + 易混替换 4804(种子集 \|S\|=20000) |
| `l3_2wiki_items.jsonl` | 4244 | 两跳拼接(种子集 \|S\|=20000) |

每个数据文件旁边有同名 `.stats.json`,记全部参数、丢弃原因计数与耗时。

**τ 过滤(§2.1 第 1 条,表面相似度)本轮不做**,等 bge-large-en-v1.5 就位后补。
三个脚本都已留 `--sim-filter TAU` 接口:当前传入只会打告警并把 τ 记进每条记录的
`sim_filter` 字段(`{"applied": false, "tau": ...}`),不做任何过滤。接上以后
只需在收录判据里加一道 `sim(x', x) >= τ`,记录结构不用动。

---

## 1. `gen_l4_alfworld.py` —— L4 位置改换对

### 做法

编辑族 ε = 「换 trial」:同一个任务目录(`任务类型-物体-可移动容器-容器-场景号`)下的不同
`trial_T*`,由不同随机种子生成物体摆放。对每个**有序**对 (种子 trial, 目标 trial):

1. 在种子 trial 上跟随 alfworld 自带的 handcoded expert 走到 `won`,拿到存储解 π*(文本动作串);
2. 逐字比对两边引擎生成的任务指令,不同就丢(不是位置改换编辑);
3. 把 π* 原样喂进目标 trial 的真引擎,**终局 `won == False` 才收录**(§2.1 第 2 条);
4. d\* = 首次矛盾信号(动作不在 `admissible_commands`,或观察是 `Nothing happens.` 一类
   无变化反馈)之前已执行的比例;按 §2.4 定 T1(<0.25)/ T2(0.25–1)/ T3(全程无信号)。

有序枚举,因为方向不对称:实测同一对 trial 反过来当种子,d\* 从 0.25 变成 0.5。

### 冒烟结果(单模板 `pick_and_place_simple`,split=train)

```
评估 51 个候选有序对 → 有效陷阱 10 对(128.6s 单进程 / 27.1s @ 8 workers)
档位分布   T2 10
丢弃原因   instruction_mismatch 27,replay_succeeded 14
```

有效率 **10/51 = 19.6%**;若只看指令确实逐字相同的候选,有效率 **10/24 = 41.7%**。

### 全模板抽样(6 个任务模板,800 个候选对,24 workers,392s)

```
800 → 有效陷阱 259(32.4%)
档位分布   T2 210,T1 49,T3 0
丢弃原因   instruction_mismatch 361,replay_succeeded 103,seed_expert_failed 77
d*         中位数 0.500,范围 0.008 – 0.971
π* 长度    中位数 13 步
```

按任务模板拆:

| 模板 | 有效对 | T1 | T2 | T3 |
|---|---|---|---|---|
| pick_and_place_simple | 65 | 2 | 63 | 0 |
| pick_clean_then_place_in_recep | 63 | 4 | 59 | 0 |
| pick_two_obj_and_place | 41 | 31 | 10 | 0 |
| pick_heat_then_place_in_recep | 39 | 5 | 34 | 0 |
| pick_cool_then_place_in_recep | 32 | 4 | 28 | 0 |
| look_at_obj_in_light | 19 | 3 | 16 | 0 |

### 全量规模估计

候选有序对(已按 alfworld 官方口径排掉 movable/Sliced 与 `solvable=false`):

| split | 候选有序对 |
|---|---|
| train | 5766 |
| valid_unseen | 256 |
| valid_seen | 6 |
| valid_train | 0 |
| **合计** | **6028** |

按抽样有效率 32.4% 推算,全量 `--full` 可产出 **约 1950 对**有效 L4 位置改换对。
墙钟成本:24 workers 下实测 0.49 s/对 → 全量约 **50 分钟**;单核约 11.8 s/对。

命令:
```bash
fig1_pilot/fig1-env/bin/python benchmark_design/gen_l4_alfworld.py \
    --full --workers 24 --out benchmark_design/l4_alfworld_full.jsonl
```

### 冒烟 10 条(供人工核对,带 d\* 与档位)

每条格式:任务目录 / 指令 / π\* / 首次矛盾点 / d\* / 档位。

1. `pick_and_place_simple-CellPhone-None-Safe-323` trial_T20190907_2345→trial_T20190907_2345
   指令 `put a cellphone in safe.` π\*(10 步)
   `go to sidetable 1 | go to sidetable 2 | go to safe 1 | open safe 1 | close safe 1 | go to dresser 1 | take cellphone 2 from dresser 1 | go to safe 1 | open safe 1 | move cellphone 2 to safe 1`
   首次矛盾 @6 `take cellphone 2 from dresser 1` [not_admissible] → `Nothing happens.` **d\*=0.600 T2**

2. `pick_and_place_simple-Candle-None-Toilet-409` trial_T20190908_1422→trial_T20190908_0142
   指令 `put a candle in toilet.` π\*(13 步)
   `go to toilet 1 | go to drawer 1 | open drawer 1 | close drawer 1 | go to drawer 2 | open drawer 2 | close drawer 2 | go to drawer 3 | open drawer 3 | take candle 2 from drawer 3 | close drawer 3 | go to toilet 1 | move candle 2 to toilet 1`
   首次矛盾 @9 `take candle 2 from drawer 3` [not_admissible] **d\*=0.692 T2**

3. `pick_and_place_simple-RemoteControl-None-Dresser-217` trial_T20190909_0538→trial_T20190909_0537
   指令 `put some remotecontrol on dresser.` π\*(4 步)
   `go to sofa 1 | take remotecontrol 1 from sofa 1 | go to dresser 1 | move remotecontrol 1 to dresser 1`
   首次矛盾 @1 `take remotecontrol 1 from sofa 1` [not_admissible] **d\*=0.250 T2**

4. `pick_and_place_simple-Watch-None-CoffeeTable-222` trial_T20190908_0324→trial_T20190908_0323
   指令 `put a watch in coffeetable.` π\*(6 步)
   `go to sidetable 1 | go to sidetable 2 | go to sidetable 3 | take watch 2 from sidetable 3 | go to coffeetable 1 | move watch 2 to coffeetable 1`
   首次矛盾 @3 `take watch 2 from sidetable 3` [not_admissible] **d\*=0.500 T2**

5. `pick_and_place_simple-TissueBox-None-SideTable-229` trial_T20190908_1141→trial_T20190908_1140
   指令 `put a tissuebox in sidetable.` π\*(21 步,搜完 4 个抽屉才找到)
   `… | go to coffeetable 1 | take tissuebox 2 from coffeetable 1 | go to sidetable 1 | move tissuebox 2 to sidetable 1`
   首次矛盾 @18 `take tissuebox 2 from coffeetable 1` [not_admissible] **d\*=0.857 T2**

6. `pick_and_place_simple-ButterKnife-None-SideTable-28` trial_T20190908_1330→trial_T20190908_1331
   指令 `put some butterknife on sidetable.` π\*(4 步)
   `go to sinkbasin 1 | take butterknife 2 from sinkbasin 1 | go to sidetable 1 | move butterknife 2 to sidetable 1`
   首次矛盾 @1 `take butterknife 2 from sinkbasin 1` [not_admissible] **d\*=0.250 T2**

7. `pick_and_place_simple-SprayBottle-None-GarbageCan-428` trial_T20190909_1015→trial_T20190909_1015
   指令 `put a spraybottle in garbagecan.` π\*(9 步)
   `go to toilet 1 | go to garbagecan 1 | go to countertop 1 | go to cabinet 1 | open cabinet 1 | take spraybottle 1 from cabinet 1 | close cabinet 1 | go to garbagecan 1 | move spraybottle 1 to garbagecan 1`
   首次矛盾 @5 `take spraybottle 1 from cabinet 1` [not_admissible] **d\*=0.556 T2**

8. `pick_and_place_simple-Watch-None-CoffeeTable-222` trial_T20190908_0323→trial_T20190908_0324
   (第 4 条的反向对,d\* 不同,印证有序枚举的必要性)
   指令 `put a watch in coffeetable.` π\*(5 步)
   `go to sidetable 1 | go to sidetable 2 | take watch 1 from sidetable 2 | go to coffeetable 1 | move watch 1 to coffeetable 1`
   首次矛盾 @2 `take watch 1 from sidetable 2` [not_admissible] **d\*=0.400 T2**

9. `pick_and_place_simple-ToiletPaper-None-Toilet-419` trial_T20190908_0023→trial_T20190908_0024
   指令 `put a toiletpaper in toilet.` π\*(8 步)
   `go to toiletpaperhanger 1 | go to toilet 1 | go to sidetable 1 | go to garbagecan 1 | go to drawer 1 | take toiletpaper 1 from drawer 1 | go to toilet 1 | move toiletpaper 1 to toilet 1`
   首次矛盾 @5 `take toiletpaper 1 from drawer 1` [not_admissible] **d\*=0.625 T2**

10. `pick_and_place_simple-WineBottle-None-Shelf-7` trial_T20190908_1146→trial_T20190907_2001
    指令 `put a winebottle in shelf.` π\*(16 步)
    `… | go to cabinet 1 | open cabinet 1 | take winebottle 1 from cabinet 1 | close cabinet 1 | go to shelf 1 | move winebottle 1 to shelf 1`
    首次矛盾 @12 `take winebottle 1 from cabinet 1` [not_admissible] **d\*=0.750 T2**

十条的失败机制完全一致,而且正是设计想要的:**导航段照抄有效、`take X from <老位置>` 一步扑空**。
记忆里的搜索路线白走了 25%–86% 的轨迹才穿帮。

---

## 2. `gen_l4_2wiki.py` —— 极性翻转 + 易混实体替换

数据:`voidful/2WikiMultihopQA`,从 NFS 缓存 `/net/tokyo100-10g/data/str01_01/y-guo/hf`
离线加载(`HF_DATASETS_OFFLINE=1`,**没有联网补拉,缓存是完整的**)。
本轮种子集 S = train 前 20000 条。

### 结果

```
|S| = 20000,三元组库 40220 个 (subject, relation) 键,耗时 12.7s
polarity_flip      1690 条   全部 T3
confusable_entity  4804 条   T1 4668 / T2 136
```

丢弃原因:

| 极性翻转 | 计数 | | 易混替换 | 计数 |
|---|---|---|---|---|
| non_date_relation(比较的是国籍等非日期属性,答案是 yes/no) | 4242 | | no_confusable_subject | 2367 |
| malformed_evidence | 279 | | no_resolvable_new_chain | 1507 |
| dates_tied_or_ambiguous | 6 | | subject_not_in_question | 674 |
| | | | chain_not_joined | 233 |

### 编程验证(这是收录判据,不是事后统计)

**极性翻转**用 evidences 的日期三元组做两道验证:

1. *方向词规则必须先能复现种子的 gold answer* —— 从问句里抽出唯一的比较方向词
   (`first / earlier / later / more recently / older / younger` 等),按它选日期的
   min 或 max,结果必须等于数据集给的答案。**1690/1690 全部通过,零条 `rule_disagrees_with_gold`**。
   这条是独立于我自己实现的交叉检验:如果日期解析或方向语义写错了,这里会立刻爆掉。
2. *翻转后 gold 必须变成另一个实体* —— 1690/1690 通过(要求两个日期在共同粒度上严格可比,
   打平的 6 条已丢)。

因此「旧解(复述记忆里的答案)在新题上必然错」的验证通过率 = **100%(1690/1690)**,
且经独立重算复核(规范化后 `seed_answer != l4_answer` 全成立)。

**易混实体替换**在全局三元组库里沿新链求解:要求 (X', r1) 与 (M', r2) 都**唯一**确定 object,
且新答案与旧答案规范化后不等。通过率 = **100%(4804/4804,不通过的在生成阶段就被丢弃)**。

档位不靠假设:脚本去查 X' 到底出没出现在种子任务的 gold 文档池(`context` 列)里。
**4668 条确认 X' 不在种子文档里 → T1**(hop1 一检索就穿帮);
**136 条 X' 恰好也在种子文档池里 → 降级 T2**,d\* 记 0.5(hop1 糊弄得过去,hop2 才错)。

### 极性翻转 10 条(种子 20260729 随机抽)

| # | 种子问题 → 答案 | L4 问题 → 答案 | 编辑 | 证据日期 |
|---|---|---|---|---|
| 1 | Who was born earlier, Milan Mikulík or Rich Fownes? → Milan Mikulík | Who was born **later**, … → Rich Fownes | earlier→later | Mikulík 1980-11-10 / Fownes 1983-10-26 |
| 2 | Who is younger, Adrian Zaugg or Michael Treanor? → Adrian Zaugg | Who is **older**, … → Michael Treanor | younger→older | Zaugg 1986-11-04 / Treanor 1979-04-17 |
| 3 | Who was born earlier, Bruno Galliker or Patrice Killoffer? → Bruno Galliker | Who was born **later**, … → Patrice Killoffer | earlier→later | Galliker 1931 / Killoffer 1966 |
| 4 | Who died earlier, Kumaratunga Munidasa or Andrea Bernardo Schierhoff? → Kumaratunga Munidasa | Who died **later**, … → Andrea Bernardo Schierhoff | earlier→later | 1944-03-02 / 1986-12-01 |
| 5 | Which film was released earlier, Amada Bata or The Devil's Honey? → Amada Bata | … released **later**, … → The Devil's Honey | earlier→later | 1964 / 1986 |
| 6 | Which film came out earlier, The Final Storm (Film) or The Midnight Taxi? → The Midnight Taxi | … came out **later**, … → The Final Storm (film) | earlier→later | 2010 / 1928 |
| 7 | Which film came out first, Star Wars: Episode II – Attack of the Clones or The Three Masks? → The Three Masks | … came out **later**, … → Star Wars: Episode II | first→later | 2002 / 1929 |
| 8 | Which film came out first, Facing The Sea or Gare Du Nord (Film)? → Facing The Sea | … came out **later**, … → Gare du Nord (film) | first→later | 1951 / 2013 |
| 9 | Which film was released first, Pro Peníze or The Guv'Nor (Film)? → Pro Peníze | … released **later**, … → The Guv'nor (film) | first→later | 1912 / 1935 |
| 10 | Which film came out earlier, A Lady Of Chance or Days To Remember? → A Lady Of Chance | … came out **later**, … → Days to Remember | earlier→later | 1928 / 1987 |

十条全是 T3:证据文档一字未动,检索照样命中,过程零警报,只有终局判分能看出错。

### 易混实体替换 10 条(同一随机抽样)

| # | 档 | 种子问题 → 答案 | L4 问题 → 答案 | 替换(共享 token) |
|---|---|---|---|---|
| 1 | T1 | Who is the paternal grandmother of Henry Fitzroy, 1st Duke of Grafton? → Henrietta Maria of France | Who is the paternal grandmother of **Henry V of England**? → Agnes of Poitou | henry |
| 2 | T1 | Which country the director of film Cocoon: The Return is from? → Canadian | … film **The Return (2006 film)** … → British | return(末位 token) |
| 3 | T1 | Where was the place of death of the director of film Las Seis Suegras De Barba Azul? → Rio de Janeiro | … film **Las Apariencias engañan** … → Buenos Aires | las |
| 4 | T1 | Where was the place of death of the director of film The Flying Marine? → Los Angeles | … film **Flying Blind** … → Oxnard | flying |
| 5 | T1 | Where did the director of film The Valley Of The Bees die? → Prague | … film **Abraham's Valley** … → Porto | valley |
| 6 | T1 | What is the date of birth of the director of film Zwemplaats Voor Jongelingen Te Amsterdam? → 1866-11-05 | … film **The Dealer from Amsterdam** … → 1884-09-25 | amsterdam(末位) |
| 7 | T1 | What is the place of birth of Marie Louise D'Aspremont's husband? → Nancy | **Adrienne Marie Louise Grandpierre-Deverzy**'s husband … → Valenciennes | louise, marie |
| 8 | T1 | When did the director of film The Desert Pirate die? → 1937-08-05 | … film **Captain Pirate** … → 1967-02-10 | pirate(末位) |
| 9 | T1 | What nationality is the director of film In My Sleep? → American | … film **I Have to Sleep, My Angel** … → Bosnia | sleep |
| 10 | T1 | What is the date of death of the director of film The Ivory Snuff Box? → 1961-08-04 | … film **The Black Box** … → 1918-03-28 | box(末位) |

每条的新链(X', r1, M') → (M', r2, A') 都在 `l4_chain` 字段里,可编程判分。

### 全量规模

见 §4「全量规模汇总」。

---

## 3. `gen_l3_2wiki.py` —— L3 两跳拼接

### 做法(严格照 §1.1 四步)

1. **抽成分**:把 S 里每题的 evidences 拆成单跳三元组,每条记住来自哪个种子问题。
2. **采样组合**:枚举 hop1=(s1,r1,o1) 与 hop2=(s2,r2,o2),要求拼接点 o1 ≡ s2,
   且**两条单跳来自不同的种子问题** —— 同一题里的两跳本来就连着,拼出来不算新组合。
3. **可行性过滤(§1.1 第 3 条)**:拼接点一致;目标关系有 gold 三元组出处;
   两跳在三元组库里都**唯一可解**(否则新题没有唯一答案,没法编程判分);
   组合从未出现过 —— 默认拿**整个 split 的 167454 条题**查重,比规范只查 S 更严。
4. **记零件出处**:`hop1_from` / `hop2_from` / `template_from` 三个种子问题 id 全部落盘。

问句表面形式**不手写模板,从数据集里挖**:2wiki 的 compositional 题本身就是
"(a,r1,b) → (b,r2,c)" 的自然语言化,把头实体挖成占位符就得到该 (r1,r2) 的官方模板。
这样 L3 问句与种子集同分布,不引入「人写措辞」这个混淆变量;每条记录里带
`template_freq_in_S`(该模板在 S 里出现多少次)与 `template_variants_in_S`(该关系对有几种写法)。

### 结果

```
|S| = 20000
挖出 94 对 (r1, r2) 的官方模板
拼接点候选实体 17078 个
查重范围 split(167454 条题)
产出 4244 条 L3,耗时 11.3s
```

丢弃原因:`junction_quota` 43633(同一拼接点最多出 2 条的多样性配额)、
`combination_already_seen` 46962(组合数据集里已有)、`same_seed_question` 17059、
`duplicate_output` 3861、`hop2_not_unique` 2390、`no_template_for_relation_pair` 661、
`hop1_not_unique` 300、`cycles_back` 4。

关系对分布头部:`director → country of citizenship`、`director → date of birth`、
`director → date of death`、`director → place of birth`、`composer → date of birth`、
`performer → country of citizenship`。头重尾轻,是 2wiki 本身的关系分布决定的。

### 冒烟 10 条(种子 20260729 随机抽)

| # | L3 问题 | 答案 | 链(hop1 ⊕ hop2) | 零件出处(hop1 / hop2 / 模板) |
|---|---|---|---|---|
| 1 | Which country the director of film Center Stage (1991 film) is from? | Chinese | (Center Stage, director, Stanley Kwan) ⊕ (Stanley Kwan, country of citizenship, Chinese) | 53fa0012 / 551b61d4 / 31772f96 |
| 2 | Which country the director of film Oh Doctor! (1925 film) is from? | American | (Oh Doctor!, director, Harry A. Pollard) ⊕ (…, country of citizenship, American) | 5ab33d57 / 1be6ae8e / 31772f96 |
| 3 | Which country the director of film African Manhunt is from? | America | (African Manhunt, director, Seymour Friedman) ⊕ (…, country of citizenship, America) | 62effc50 / 4151b863 / 31772f96 |
| 4 | Which country the director of film 1941 (film) is from? | American | (1941, director, Steven Spielberg) ⊕ (…, country of citizenship, American) | 6e3d5e39 / 430dedd8 / 31772f96 |
| 5 | What is the date of birth of the director of film Aatmiyulu? | 27 July 1917 | (Aatmiyulu, director, V. Madhusudhan Rao) ⊕ (…, date of birth, 27 July 1917) | 7579be15 / 527bafa3 / cd75daa0 |
| 6 | What nationality is the performer of song Ganz Wien? | Austrian | (Ganz Wien, performer, Falco) ⊕ (Falco, country of citizenship, Austrian) | 87566c7a / 20a77418 / 5d35d680 |
| 7 | What is the date of birth of the director of film The Tree of Life (film)? | November 30, 1943 | (The Tree of Life, director, Terrence Malick) ⊕ (…, date of birth, …) | 8ae6a81a / 33832d48 / cd75daa0 |
| 8 | What is the date of birth of the director of film Jerry Maguire? | July 13, 1957 | (Jerry Maguire, director, Cameron Crowe) ⊕ (…, date of birth, …) | b7825112 / 7ce2e95b / cd75daa0 |
| 9 | Which country the director of film The Stroll is from? | Russia | (The Stroll, director, Alexei Uchitel) ⊕ (…, country of citizenship, Russia) | cefc0b00 / 333d46a6 / 31772f96 |
| 10 | When did the director of film Sinews of Steel die? | November 22, 1959 | (Sinews of Steel, director, Frank O'Connor) ⊕ (…, date of death, …) | ea1248c2 / ccef615e / 56da8310 |

(id 是种子问题 `_id` 的前 8 位,全量 id 在 jsonl 的 `provenance` 字段。)

每条都满足 L3 的定义:两个零件各自在种子集里被单独问过,合起来这条链在整个 2wiki
train split 里从未作为一道题出现过。

---

## 4. 全量规模汇总

| 域 / 编辑族 | 本轮产量 | 全量估计 | 依据 |
|---|---|---|---|
| ALFWorld 位置改换 | 10(冒烟)/ 259(800 候选抽样) | **约 1950 对** | 6028 个候选有序对 × 32.4% 实测有效率;24 workers 约 50 分钟 |
| 2wiki 极性翻转 | 1690(\|S\|=20000) | **14095**(实跑) | train 全量 167454 条 |
| 2wiki 易混替换 | 4804(\|S\|=20000) | **51751**(实跑) | 同上 |
| 2wiki L3 两跳拼接 | 4244(\|S\|=20000) | **19520**(实跑) | 同上 |

2wiki 三族在整个 train split 上的**实跑结果**(不是外推,已实际跑完一遍):

| 族 | \|S\|=20000 | \|S\|=167454(全 train) | 倍率 | 耗时 |
|---|---|---|---|---|
| 极性翻转 | 1690 | **14095**(全 T3) | 8.3× | 159s(与易混替换同一次跑) |
| 易混实体替换 | 4804 | **51751**(T1 49363 / T2 2388) | 10.8× | 同上 |
| L3 两跳拼接 | 4244 | **19520** | 4.6× | 107s |

极性翻转基本随 \|S\| 线性放大(8.3× vs 8.4× 的数据量),因为每条种子独立成对。
易混替换超线性(10.8×),因为三元组库变大后更多种子能找到可解的新链。
L3 只有 4.6×,是 `--max-per-junction 2` 的多样性配额压着——全 train 下
`junction_quota` 丢掉 321 万条候选,放开配额可以再上一个量级,但会被少数热门实体刷屏。

全量跑法(约 4.5 分钟,峰值内存不到 10 GB):
```bash
jlens-env/bin/python benchmark_design/gen_l4_2wiki.py --seed-pool 0 --out <path>
jlens-env/bin/python benchmark_design/gen_l3_2wiki.py --seed-pool 0 --out <path>
```

也就是说:**L4 和 L3 的 QA 侧供给远远过剩**(6.5 万 + 1.9 万),真正的瓶颈在 ALFWorld 侧
(约 1950 对)和档位配平(见坑 8)。发布版该做的是按 T1:T2:T3 与关系对分层**下采样**,
不是想办法多产。

---

## 5. 遇到的坑

**坑 1(最阴的一个):ALFWorld 的 handcoded expert 走全局 `random`,而全局 random 每个进程
用 urandom 自动播种。** 后果是同参数两次运行给出不同的专家演示,进而不同的收录集合——
第一次做重跑一致性检查就撞上了:两次各 10 对,有 1 对不一样(一次判 `replay_succeeded` 丢弃,
一次判有效)。这类不一致极容易被当成「引擎有随机性,没办法」放过去。
解法:按内容确定性重播全局 RNG(`_reseed(内容键)`,种子 = 基种子 XOR crc32(键)),
在每次 rollout 与每次 replay 前各播一次。这样既跨运行可复现,又与处理顺序、并行度无关。
已验证:两次单进程运行 md5 相同,且 `--workers 1` 与 `--workers 8` 输出 md5 也相同。

**坑 2:同一个任务目录并不保证指令逐字相同。** ALFWorld 的 templated goal 有多种表面写法,
同一目录下的两个 trial 可能一个是 `put a alarmclock in desk.`、另一个是
`put some alarmclock on desk.`。这直接违反 §2.2 第 1 类「指令逐字相同」的编辑定义。
脚本改成从引擎实际返回的观察里抠出指令逐字比对,不同就丢——这一条吃掉了 **45%** 的候选对
(800 里丢 361)。如果按目录名想当然地假设指令相同,产出的「位置改换对」会有近一半其实是
指令也变了的混合编辑,L4 读数会归因错误。

**坑 3:同目录不同 trial 的布局经常是一样的,旧解照样成功。** 800 个候选里 103 个
(12.9%)回放直接 `won=True`。§2.1 第 2 条的陷阱有效性检查不是形式主义,是刚需——
不做的话这批「陷阱」里有一成多其实是无害的重复任务,负迁移读数会被稀释成假阴性。

**坑 4:`game.tw-pddl` 里自带的 `walkthrough` 字段不能直接用。** 它的物体编号与运行时
demangler 的命名不保证一致,实测同一 trial walkthrough 写 `alarmclock 2`、活体 expert 给
`alarmclock 1`。用它当 π\* 会凭空造出假的「不可执行」。改用活体 rollout;
`--demo-source walkthrough` 作为对照通道保留。

**坑 5:handcoded expert 自己也会失败。** 全模板抽样里 77/800(9.6%)的种子 trial 上
expert 在 150 步内没走到 `won`(集中在 heat / cool / clean / two_obj 这些长流程模板)。
这些种子没有 π\*,谈不上「旧解」,直接丢。单模板 `pick_and_place_simple` 冒烟时一条没遇到,
所以这个坑只有做全模板才会暴露。

**坑 6:实体替换会留下张冠李戴的括号消歧后缀。** 种子问句写
`… film G.I. Jane (1951 Film)?`,evidences 里的 subject 只是 `G.I. Jane`;只替换前半截会得到
`… film It Happened to Jane (1951 Film)?` —— 而那片子是 1959 年的。反向的坑同样存在:
`Lover Man (Oh, Where Can You Be?)` 的括号是名字的一部分,只换前半截会造出
`Old Man (Oh, Where Can You Be?)` 这种怪物。解法:定位到实体后把紧随其后的整个括号块
一并纳入替换区间。修完这两类问句都干净了(见 §2 的 10 条样例)。

**坑 7:T1 档不能靠嘴说。** 规范 §2.4 把易混实体替换默认归为 T1(「文档里没这个名字」),
但这是个可验证的事实,不是定义。脚本去查 X' 在不在种子任务的 gold 文档池里:
4804 条里有 **136 条 X' 恰好也出现在种子文档里**,这些按判据应该降级 T2。
不查的话这 136 条会污染 T1 档的剂量-响应曲线。

**坑 8:T3 档在 ALFWorld 位置改换上产量为零。** 800 个候选、259 个有效对,**T3 一条没有**。
机制很清楚:位置改换的失败点永远是 `take X from <老位置>` 这一步,而这一步在引擎里必然
不在 `admissible_commands` 里,`Nothing happens.` 是个响亮的警报。
§2.4 要求发布版按 T1:T2:T3 配平,所以 **ALFWorld 的 T3 必须靠 §2.2 的另外两类编辑
(动词翻转 pick_heat↔pick_cool、数量翻转 单↔双)去补**,那两类才会产生「走完全程无警报、
只有终局判分失败」的静默错误。这一条建议写进 T12b 的任务口径。
目前 T3 的唯一来源是 2wiki 极性翻转(1690 条,全 T3),两个域的档位分布严重不对称。

**坑 9:ALFWorld 的位置改换对几乎只存在于 train split。** 候选有序对 train 5766 /
valid_unseen 256 / valid_seen 6 / valid_train 0 —— 因为其余 split 的任务目录大多只有
一个 trial。这意味着 L4 ALFWorld 探针段与 seeding 段都得从 train 里取,split 卫生要在
流构造那一层保证(靠任务目录划分,不能靠 split 划分)。

**坑 10:环境不能合一。** `fig1-env` 没有 `datasets`,`jlens-env`(datasets 5.0.0)没有
`alfworld`。两边各跑各的,报告里的命令已标注对应 venv。HF 缓存是完整的,
`HF_DATASETS_OFFLINE=1` 直接加载成功,**本轮没有联网补拉任何数据**。

---

## 6. 未完成 / 下一步

1. **τ 过滤(§2.1 第 1 条)**:等 bge-large-en-v1.5 就位。接口 `--sim-filter TAU` 三个脚本都留好了,
   记录结构不用改。同时要先测出各域 L2 重复对的相似度分布 p50 才能定 τ。
2. **ALFWorld 另两类编辑(§2.2 第 2/3 类)**:动词翻转与数量翻转,是 T3 档的唯一来源(坑 8)。
3. **2wiki 锚点角色改换(§2.3 第 3 类)**:本轮未做,规范判它是 T2,可补平 2wiki 的档位分布。
4. **L3 的另两类(§1.3 第 2/3 类)**:比较对重配、三跳延长,本轮只做了第 1 类两跳拼接。
5. **关系对多样性**:L3 目前头部被 `director → *` 主导,发布版可能要按关系对做分层配额。
