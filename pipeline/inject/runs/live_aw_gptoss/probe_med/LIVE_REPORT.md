# 活跑注入线报告

对照批次的服务条件与 harmony 日期行都与活跑不同(设计书 §1),
token 总量对比要带这条保留;billed 含触发后丢弃的溢出。
n_task_error 是临时故障(abort=task_error)的题数,这些题没进
live_success 的分母;重跑前删掉对应 live_*.jsonl 才会重试。

| 指标 | 值 |
|---|---|
| n_tasks | 168 |
| n_done | 168 |
| n_paired | 168 |
| n_task_error | 0 |
| live_success | 0.0476 |
| base_success | 0.2857 |
| live_success_paired | 0.0476 |
| inject_per_task | 0.7202 |
| billed_tok_sum | 1360901 |
| base_out_tok_sum | 4789358 |
| n_spec | 121 |
| spec_exec_ok | 1.0 |
| spec_tool_agree | 0.2893 |
| spec_call_agree | 0.1901 |
| spec_recalled | 0.2893 |
| spec_error_kinds | {} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 024c982_1 | probe | False | False | 11 | 1 | 2722 | 15596 |
| 024c982_2 | probe | False | True | 9 | 1 | 1499 | 23295 |
| 024c982_3 | probe | False | False | 10 | 1 | 4207 | 5181 |
| 042a9fc_1 | probe | False | False | 19 | 1 | 16253 | 89381 |
| 042a9fc_2 | probe | False | False | 30 | 0 | 16630 | 31817 |
| 042a9fc_3 | probe | False | False | 30 | 0 | 46400 | 27816 |
| 09b0ee6_1 | probe | True | True | 8 | 1 | 4017 | 5847 |
| 09b0ee6_2 | probe | False | True | 11 | 1 | 5749 | 9513 |
| 09b0ee6_3 | probe | True | True | 6 | 1 | 2634 | 17628 |
| 0a9d82a_1 | probe | False | True | 13 | 0 | 6807 | 9925 |
| 0a9d82a_2 | probe | False | True | 9 | 0 | 1870 | 29053 |
| 0a9d82a_3 | probe | False | False | 9 | 0 | 6144 | 13243 |
| 0d01c76_1 | probe | False | True | 13 | 0 | 6537 | 12687 |
| 0d01c76_2 | probe | False | True | 26 | 0 | 10421 | 21351 |
| 0d01c76_3 | probe | True | True | 12 | 1 | 3307 | 34251 |
| 0de03ea_1 | probe | False | False | 15 | 1 | 9489 | 20916 |
| 0de03ea_2 | probe | False | False | 8 | 1 | 2998 | 18773 |
| 0de03ea_3 | probe | False | False | 11 | 2 | 5140 | 7754 |
| 1150ed6_1 | probe | False | False | 6 | 2 | 1596 | 35426 |
| 1150ed6_2 | probe | False | False | 11 | 1 | 4077 | 18318 |
| 1150ed6_3 | probe | False | True | 10 | 4 | 7420 | 27132 |
| 13547f5_1 | probe | False | True | 12 | 0 | 5779 | 5692 |
| 13547f5_2 | probe | False | False | 15 | 0 | 18239 | 73306 |
| 13547f5_3 | probe | False | True | 19 | 0 | 12503 | 6302 |
| 166f4ff_1 | probe | False | False | 11 | 1 | 6938 | 5529 |
| 166f4ff_2 | probe | False | False | 7 | 0 | 4463 | 5680 |
| 166f4ff_3 | probe | False | False | 6 | 0 | 1536 | 5228 |
| 21abae1_1 | probe | False | False | 4 | 1 | 1103 | 18842 |
| 21abae1_2 | probe | False | False | 8 | 0 | 1842 | 10414 |
| 21abae1_3 | probe | False | False | 8 | 0 | 2517 | 10511 |
| 270f1ff_1 | probe | False | False | 12 | 2 | 3548 | 34993 |
| 270f1ff_2 | probe | False | False | 11 | 2 | 3502 | 33694 |
| 270f1ff_3 | probe | False | False | 30 | 1 | 9605 | 36340 |
| 29a7b7e_1 | probe | True | True | 15 | 0 | 5280 | 27400 |
| 29a7b7e_2 | probe | False | False | 5 | 0 | 1099 | 19024 |
| 29a7b7e_3 | probe | False | False | 15 | 0 | 9992 | 16355 |
| 2c544f9_1 | probe | False | False | 24 | 1 | 10923 | 108328 |
| 2c544f9_2 | probe | False | False | 30 | 1 | 20106 | 31187 |
| 2c544f9_3 | probe | False | False | 15 | 1 | 3827 | 62994 |
| 2d9f728_1 | probe | False | False | 30 | 1 | 28332 | 22354 |
| 2d9f728_2 | probe | False | False | 14 | 1 | 6857 | 55276 |
| 2d9f728_3 | probe | False | False | 13 | 1 | 6668 | 43248 |
| 31dc501_1 | probe | False | True | 10 | 0 | 5247 | 24559 |
| 31dc501_2 | probe | False | True | 13 | 0 | 12517 | 14910 |
| 31dc501_3 | probe | True | True | 9 | 0 | 1378 | 17396 |
| 325d6ec_1 | probe | False | True | 7 | 1 | 2290 | 12394 |
| 325d6ec_2 | probe | False | False | 7 | 1 | 3372 | 9918 |
| 325d6ec_3 | probe | False | False | 8 | 1 | 2515 | 14248 |
| 32616b5_1 | probe | False | False | 7 | 1 | 6261 | 29076 |
| 32616b5_2 | probe | False | False | 22 | 1 | 10807 | 33822 |
| 32616b5_3 | probe | False | False | 24 | 1 | 26302 | 30370 |
| 3aa1a22_1 | probe | False | False | 13 | 1 | 6036 | 30156 |
| 3aa1a22_2 | probe | False | False | 18 | 1 | 9933 | 28242 |
| 3aa1a22_3 | probe | False | False | 26 | 0 | 22877 | 20774 |
| 3b8fb7a_1 | probe | False | False | 30 | 0 | 15559 | 33105 |
| 3b8fb7a_2 | probe | False | False | 10 | 0 | 8344 | 53306 |
| 3b8fb7a_3 | probe | False | True | 17 | 0 | 11051 | 39689 |
| 3d9a636_1 | probe | False | False | 10 | 1 | 5002 | 29234 |
| 3d9a636_2 | probe | False | True | 12 | 1 | 5526 | 21401 |
| 3d9a636_3 | probe | False | False | 2 | 1 | 2314 | 36228 |
| 425a494_1 | probe | False | False | 7 | 0 | 2151 | 5562 |
| 425a494_2 | probe | False | True | 4 | 1 | 1288 | 27472 |
| 425a494_3 | probe | False | False | 8 | 2 | 3099 | 7918 |
| 522e5e5_1 | probe | False | True | 7 | 2 | 2560 | 14422 |
| 522e5e5_2 | probe | True | True | 6 | 1 | 2408 | 16094 |
| 522e5e5_3 | probe | False | False | 6 | 1 | 1917 | 14281 |
| 552869a_1 | probe | False | False | 9 | 2 | 3596 | 11634 |
| 552869a_2 | probe | False | False | 6 | 1 | 1142 | 6799 |
| 552869a_3 | probe | False | False | 5 | 1 | 1230 | 4813 |
| 59fae45_1 | probe | False | True | 10 | 0 | 6363 | 8305 |
| 59fae45_2 | probe | False | True | 11 | 1 | 4007 | 17881 |
| 59fae45_3 | probe | False | True | 7 | 0 | 3444 | 16291 |
| 5a83b05_1 | probe | False | True | 11 | 0 | 3686 | 7318 |
| 5a83b05_2 | probe | False | True | 11 | 0 | 3766 | 4374 |
| 5a83b05_3 | probe | False | True | 10 | 0 | 2343 | 7939 |
| 634f342_1 | probe | False | False | 22 | 1 | 22507 | 69902 |
| 634f342_2 | probe | False | True | 6 | 1 | 5176 | 25931 |
| 634f342_3 | probe | False | False | 17 | 3 | 6478 | 21461 |
| 652485c_1 | probe | False | False | 23 | 1 | 9891 | 62218 |
| 652485c_2 | probe | False | False | 22 | 2 | 27306 | 59517 |
| 652485c_3 | probe | False | False | 30 | 1 | 13386 | 39618 |
| 6b6ca61_1 | probe | False | False | 24 | 1 | 26696 | 39037 |
| 6b6ca61_2 | probe | False | False | 21 | 2 | 27119 | 69750 |
| 6b6ca61_3 | probe | False | False | 20 | 0 | 26353 | 54829 |
| 6f4b9a5_1 | probe | False | False | 13 | 0 | 5955 | 21985 |
| 6f4b9a5_2 | probe | False | False | 14 | 0 | 7459 | 26468 |
| 6f4b9a5_3 | probe | False | False | 16 | 0 | 10814 | 32223 |
| 7847649_1 | probe | False | False | 6 | 1 | 1525 | 5176 |
| 7847649_2 | probe | False | False | 7 | 1 | 2254 | 15631 |
| 7847649_3 | probe | False | False | 7 | 1 | 881 | 4563 |
| 83a7951_1 | probe | False | False | 13 | 1 | 8218 | 32935 |
| 83a7951_2 | probe | False | False | 12 | 2 | 5544 | 54882 |
| 83a7951_3 | probe | False | False | 11 | 0 | 6342 | 41370 |
| 8749218_1 | probe | False | True | 6 | 0 | 2806 | 22794 |
| 8749218_2 | probe | False | True | 6 | 1 | 2920 | 27120 |
| 8749218_3 | probe | False | True | 11 | 0 | 2534 | 21951 |
| 8ce6779_1 | probe | False | False | 13 | 0 | 7830 | 44035 |
| 8ce6779_2 | probe | False | False | 10 | 0 | 4007 | 30098 |
| 8ce6779_3 | probe | False | False | 16 | 0 | 8458 | 28472 |
| 9016950_1 | probe | False | True | 12 | 0 | 11401 | 32313 |
| 9016950_2 | probe | False | False | 10 | 0 | 5539 | 40412 |
| 9016950_3 | probe | False | False | 18 | 0 | 8185 | 34910 |
| 90adc3f_1 | probe | False | False | 15 | 0 | 7022 | 13653 |
| 90adc3f_2 | probe | False | False | 17 | 0 | 8077 | 22471 |
| 90adc3f_3 | probe | False | False | 8 | 0 | 5080 | 32902 |
| 986aa4e_1 | probe | False | False | 9 | 1 | 5124 | 54113 |
| 986aa4e_2 | probe | False | False | 11 | 1 | 8025 | 71548 |
| 986aa4e_3 | probe | False | False | 17 | 1 | 46645 | 75990 |
| 9dabbc9_1 | probe | False | True | 12 | 1 | 4393 | 19519 |
| 9dabbc9_2 | probe | False | False | 14 | 1 | 5093 | 21459 |
| 9dabbc9_3 | probe | False | False | 12 | 1 | 3523 | 28714 |
| 9ef798c_1 | probe | False | True | 17 | 1 | 9480 | 26112 |
| 9ef798c_2 | probe | False | False | 14 | 1 | 5334 | 38053 |
| 9ef798c_3 | probe | False | False | 13 | 0 | 10552 | 98326 |
| a30375d_1 | probe | True | False | 16 | 1 | 4394 | 7725 |
| a30375d_2 | probe | False | False | 10 | 1 | 3131 | 21907 |
| a30375d_3 | probe | False | False | 8 | 1 | 2182 | 75855 |
| afc4005_1 | probe | False | False | 12 | 0 | 5990 | 11920 |
| afc4005_2 | probe | False | False | 9 | 0 | 5198 | 9209 |
| afc4005_3 | probe | False | False | 9 | 0 | 2007 | 24109 |
| b6d1104_1 | probe | False | False | 13 | 1 | 6546 | 5856 |
| b6d1104_2 | probe | False | False | 13 | 1 | 5471 | 26032 |
| b6d1104_3 | probe | False | False | 11 | 2 | 5021 | 18806 |
| b9c5c9a_1 | probe | False | False | 11 | 0 | 9789 | 78109 |
| b9c5c9a_2 | probe | False | False | 30 | 0 | 28491 | 76753 |
| b9c5c9a_3 | probe | False | False | 28 | 0 | 22487 | 67265 |
| bde252e_1 | probe | False | False | 10 | 1 | 7514 | 63809 |
| bde252e_2 | probe | False | False | 15 | 1 | 6295 | 33853 |
| bde252e_3 | probe | False | False | 5 | 2 | 2472 | 93274 |
| c77c005_1 | probe | False | False | 7 | 1 | 3954 | 14051 |
| c77c005_2 | probe | False | True | 8 | 2 | 4314 | 12428 |
| c77c005_3 | probe | False | True | 11 | 2 | 3873 | 19445 |
| ccf4b82_1 | probe | False | False | 18 | 1 | 10471 | 23475 |
| ccf4b82_2 | probe | False | False | 17 | 1 | 10151 | 28854 |
| ccf4b82_3 | probe | False | True | 6 | 1 | 3158 | 33688 |
| cef9191_1 | probe | False | False | 10 | 1 | 3345 | 30538 |
| cef9191_2 | probe | True | True | 7 | 1 | 2490 | 10159 |
| cef9191_3 | probe | False | True | 12 | 1 | 4596 | 14634 |
| d18139b_1 | probe | False | False | 18 | 1 | 8594 | 43586 |
| d18139b_2 | probe | False | False | 28 | 1 | 10688 | 24234 |
| d18139b_3 | probe | False | False | 6 | 1 | 3394 | 16118 |
| d194965_1 | probe | False | False | 12 | 1 | 17291 | 47486 |
| d194965_2 | probe | False | False | 30 | 1 | 14314 | 50222 |
| d194965_3 | probe | False | False | 23 | 1 | 10310 | 41996 |
| d6ac34d_1 | probe | False | False | 30 | 1 | 4270 | 12303 |
| d6ac34d_2 | probe | False | False | 10 | 0 | 2733 | 11910 |
| d6ac34d_3 | probe | False | False | 30 | 1 | 6369 | 13326 |
| dac78d9_1 | probe | False | False | 5 | 0 | 1240 | 13228 |
| dac78d9_2 | probe | False | False | 5 | 1 | 1476 | 6809 |
| dac78d9_3 | probe | False | False | 8 | 1 | 2312 | 8042 |
| f323bae_1 | probe | False | True | 17 | 0 | 5716 | 38212 |
| f323bae_2 | probe | False | False | 15 | 0 | 11964 | 23708 |
| f323bae_3 | probe | False | True | 23 | 0 | 9823 | 31488 |
| f3f60f0_1 | probe | False | True | 7 | 1 | 2378 | 16576 |
| f3f60f0_2 | probe | False | True | 8 | 1 | 3909 | 12391 |
| f3f60f0_3 | probe | False | True | 7 | 1 | 2801 | 7534 |
| f861c32_1 | probe | False | False | 30 | 1 | 59017 | 61497 |
| f861c32_2 | probe | False | False | 22 | 0 | 24692 | 34019 |
| f861c32_3 | probe | False | False | 27 | 1 | 25811 | 19731 |
| fd1f8fa_1 | probe | False | False | 11 | 0 | 6530 | 42707 |
| fd1f8fa_2 | probe | False | False | 9 | 0 | 2189 | 25197 |
| fd1f8fa_3 | probe | False | False | 15 | 0 | 3940 | 50415 |
| ff58e36_1 | probe | False | True | 15 | 0 | 4455 | 20354 |
| ff58e36_2 | probe | False | True | 12 | 0 | 9273 | 32719 |
| ff58e36_3 | probe | False | True | 15 | 0 | 9952 | 24444 |
| ffe6d5e_1 | probe | False | False | 10 | 1 | 2767 | 11978 |
| ffe6d5e_2 | probe | False | False | 15 | 1 | 7747 | 17999 |
| ffe6d5e_3 | probe | False | False | 9 | 0 | 4767 | 7383 |
