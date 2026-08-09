import os

# 事故 agent 结构性兜底(final-review C1,2026-08-09):sampler.spawn_agent()
# 拉起来的是真实付费 opus 子进程,任何测试文件都不许无意间真的触发它。
# 各测试文件里 mock 掉 spawn_agent 是第一道防线;这个环境变量是第二道——
# `tests` 是一个包,`python3 -m unittest tests.test_x` 一定会先执行这个
# __init__.py,所以在这里设一次就覆盖整个包下的所有测试文件,不必每个
# 文件各自记得设。sampler.spawn_agent() 见到这个变量非空就只写占位行,
# 不建子进程。
os.environ.setdefault("NEW1_NO_SPAWN", "1")
