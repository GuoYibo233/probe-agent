# 写作结构清单（化用自 Master-cai/Research-Paper-Writing-Skills）

> 来源仓库已 clone 在 `related_work/Research-Paper-Writing-Skills/`，
> 本文件只保留三块承重内容；范文与其余章节指南按下方路径随取随用。

## 一、Introduction 动笔前：倒推七问

写 intro 前先把七问答案各写成一行，**答不出的那条就是故事线的洞**，先补洞再动笔：

- [ ] 我们解决什么技术问题？为什么它没有现成解？
- [ ] 贡献是什么（新任务 / 新指标 / 新技术问题 / 新技术）？
- [ ] 贡献为什么能解决这个问题？带来什么新洞察？
- [ ] 用哪些已有方法把读者引到我们的挑战上？
- [ ] 已有方法失败的技术原因（不是现象）是什么？
- [ ] 我们的机制为什么在本质上可行？
- [ ] 主实验数字支撑上面哪一句断言？

正向落笔五段：任务与应用 → 已有方法引出挑战（限制+技术原因）→
我们的方案与机制 → 实验主结果 → 贡献清单。
每段首句必须直接陈述该段论点；一段只讲一件事。

## 二、两条审稿人红线（改稿循环必查）

- [ ] **没有"朴素方案→我们改进它"的写法**。先摆 naive solution 再讲改进，
  读者会把工作理解成增量补丁，好奇心归零。哪怕工作确实是增量的也不许这么写：
  直接从"已有方法因为 X 失败"跳到"我们的机制"。
- [ ] **没有"只讲抽象洞察不讲机制"的写法**。intro 里必须有具体机制步骤
  （Specifically, ...），堆新名词不解释机制会被审成 shallow / novelty illusion。

## 三、Related work 段落定式

每个主题段四步走，缺一步就重写：

1. 范围句：这个主题覆盖哪条线。
2. 代表工作：每篇一句话讲清**它做什么**（不是罗列引用）。
3. 局限：与**我们解决的那个挑战**直接相关的局限 + 技术原因。
4. 差异句：段末一句亮出我们和这条线的差别，用机制语言不用宣传语言。

主题 2–4 个，按技术主题分组不按年代；最强竞品不许藏。

## 四、其余章节指南路径（写到再读）

| 章节 | 路径（相对 related_work/Research-Paper-Writing-Skills/research-paper-writing/） |
|---|---|
| Abstract | references/abstract.md + examples/abstract/ 三模板 |
| Method | references/method.md |
| Experiments | references/experiments.md |
| Conclusion | references/conclusion.md |
| 行文连贯 | references/does-my-writing-flow-source.md |
| 自审 | references/paper-review.md |
| Intro 范文库 | references/examples/introduction/ 13 篇 |
