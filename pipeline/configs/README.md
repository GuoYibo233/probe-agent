# pipeline/configs/ — 数据批次配置

这个目录管数据批次（一份 json = 环境 × 模型的一次标注/建库设定：
轨迹源目录、题单模式、落点、种子），`ann-build` 等任务用 `--config` 吃。
生成设置（模型地址、vLLM 启动参数、采样参数）不在这里——在仓库根的
`configs/`（models.json + presets/），别放错地方。
