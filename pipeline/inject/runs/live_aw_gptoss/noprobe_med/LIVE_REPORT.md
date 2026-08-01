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
| live_success | 0.0714 |
| base_success | 0.2857 |
| live_success_paired | 0.0714 |
| inject_per_task | 0.0 |
| billed_tok_sum | 1369178 |
| base_out_tok_sum | 4789358 |
| n_spec | 0 |
| spec_exec_ok | None |
| spec_tool_agree | None |
| spec_call_agree | None |
| spec_recalled | None |
| spec_error_kinds | {} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 024c982_1 | no_probe | True | False | 11 | 0 | 2643 | 15596 |
| 024c982_2 | no_probe | False | True | 9 | 0 | 6031 | 23295 |
| 024c982_3 | no_probe | False | False | 16 | 0 | 15763 | 5181 |
| 042a9fc_1 | no_probe | False | False | 19 | 0 | 6045 | 89381 |
| 042a9fc_2 | no_probe | False | False | 30 | 0 | 9556 | 31817 |
| 042a9fc_3 | no_probe | False | False | 18 | 0 | 15063 | 27816 |
| 09b0ee6_1 | no_probe | True | True | 6 | 0 | 2007 | 5847 |
| 09b0ee6_2 | no_probe | False | True | 8 | 0 | 2597 | 9513 |
| 09b0ee6_3 | no_probe | True | True | 8 | 0 | 2704 | 17628 |
| 0a9d82a_1 | no_probe | False | True | 11 | 0 | 4656 | 9925 |
| 0a9d82a_2 | no_probe | False | True | 9 | 0 | 2297 | 29053 |
| 0a9d82a_3 | no_probe | False | False | 10 | 0 | 4704 | 13243 |
| 0d01c76_1 | no_probe | True | True | 17 | 0 | 6324 | 12687 |
| 0d01c76_2 | no_probe | True | True | 13 | 0 | 5662 | 21351 |
| 0d01c76_3 | no_probe | False | True | 13 | 0 | 3712 | 34251 |
| 0de03ea_1 | no_probe | False | False | 11 | 0 | 6311 | 20916 |
| 0de03ea_2 | no_probe | False | False | 7 | 0 | 5177 | 18773 |
| 0de03ea_3 | no_probe | False | False | 11 | 0 | 6012 | 7754 |
| 1150ed6_1 | no_probe | False | False | 12 | 0 | 3768 | 35426 |
| 1150ed6_2 | no_probe | False | False | 13 | 0 | 6144 | 18318 |
| 1150ed6_3 | no_probe | True | True | 12 | 0 | 2712 | 27132 |
| 13547f5_1 | no_probe | False | True | 10 | 0 | 3987 | 5692 |
| 13547f5_2 | no_probe | False | False | 10 | 0 | 7976 | 73306 |
| 13547f5_3 | no_probe | False | True | 9 | 0 | 3839 | 6302 |
| 166f4ff_1 | no_probe | False | False | 12 | 0 | 3795 | 5529 |
| 166f4ff_2 | no_probe | False | False | 8 | 0 | 5401 | 5680 |
| 166f4ff_3 | no_probe | False | False | 8 | 0 | 3828 | 5228 |
| 21abae1_1 | no_probe | False | False | 7 | 0 | 1907 | 18842 |
| 21abae1_2 | no_probe | False | False | 7 | 0 | 1462 | 10414 |
| 21abae1_3 | no_probe | False | False | 9 | 0 | 5400 | 10511 |
| 270f1ff_1 | no_probe | False | False | 30 | 0 | 14485 | 34993 |
| 270f1ff_2 | no_probe | False | False | 30 | 0 | 17182 | 33694 |
| 270f1ff_3 | no_probe | False | False | 14 | 0 | 3229 | 36340 |
| 29a7b7e_1 | no_probe | False | True | 10 | 0 | 2356 | 27400 |
| 29a7b7e_2 | no_probe | True | False | 13 | 0 | 5838 | 19024 |
| 29a7b7e_3 | no_probe | True | False | 17 | 0 | 9305 | 16355 |
| 2c544f9_1 | no_probe | False | False | 30 | 0 | 13115 | 108328 |
| 2c544f9_2 | no_probe | False | False | 24 | 0 | 14388 | 31187 |
| 2c544f9_3 | no_probe | False | False | 17 | 0 | 5643 | 62994 |
| 2d9f728_1 | no_probe | False | False | 16 | 0 | 10967 | 22354 |
| 2d9f728_2 | no_probe | False | False | 30 | 0 | 25967 | 55276 |
| 2d9f728_3 | no_probe | False | False | 13 | 0 | 9443 | 43248 |
| 31dc501_1 | no_probe | False | True | 11 | 0 | 4945 | 24559 |
| 31dc501_2 | no_probe | False | True | 11 | 0 | 8078 | 14910 |
| 31dc501_3 | no_probe | False | True | 4 | 0 | 3478 | 17396 |
| 325d6ec_1 | no_probe | False | True | 10 | 0 | 2864 | 12394 |
| 325d6ec_2 | no_probe | False | False | 13 | 0 | 4770 | 9918 |
| 325d6ec_3 | no_probe | False | False | 16 | 0 | 5705 | 14248 |
| 32616b5_1 | no_probe | False | False | 19 | 0 | 16285 | 29076 |
| 32616b5_2 | no_probe | False | False | 25 | 0 | 16013 | 33822 |
| 32616b5_3 | no_probe | False | False | 30 | 0 | 28301 | 30370 |
| 3aa1a22_1 | no_probe | False | False | 30 | 0 | 11784 | 30156 |
| 3aa1a22_2 | no_probe | False | False | 20 | 0 | 10176 | 28242 |
| 3aa1a22_3 | no_probe | False | False | 14 | 0 | 22882 | 20774 |
| 3b8fb7a_1 | no_probe | False | False | 28 | 0 | 17661 | 33105 |
| 3b8fb7a_2 | no_probe | False | False | 30 | 0 | 24690 | 53306 |
| 3b8fb7a_3 | no_probe | False | True | 13 | 0 | 10955 | 39689 |
| 3d9a636_1 | no_probe | False | False | 11 | 0 | 6866 | 29234 |
| 3d9a636_2 | no_probe | False | True | 4 | 0 | 2199 | 21401 |
| 3d9a636_3 | no_probe | False | False | 16 | 0 | 7845 | 36228 |
| 425a494_1 | no_probe | False | False | 7 | 0 | 4111 | 5562 |
| 425a494_2 | no_probe | False | True | 9 | 0 | 2183 | 27472 |
| 425a494_3 | no_probe | False | False | 9 | 0 | 2564 | 7918 |
| 522e5e5_1 | no_probe | False | True | 10 | 0 | 2363 | 14422 |
| 522e5e5_2 | no_probe | False | True | 9 | 0 | 5360 | 16094 |
| 522e5e5_3 | no_probe | False | False | 4 | 0 | 2376 | 14281 |
| 552869a_1 | no_probe | False | False | 8 | 0 | 2517 | 11634 |
| 552869a_2 | no_probe | False | False | 5 | 0 | 1415 | 6799 |
| 552869a_3 | no_probe | False | False | 5 | 0 | 1094 | 4813 |
| 59fae45_1 | no_probe | True | True | 11 | 0 | 4263 | 8305 |
| 59fae45_2 | no_probe | False | True | 9 | 0 | 2272 | 17881 |
| 59fae45_3 | no_probe | False | True | 30 | 0 | 5530 | 16291 |
| 5a83b05_1 | no_probe | False | True | 7 | 0 | 1839 | 7318 |
| 5a83b05_2 | no_probe | False | True | 12 | 0 | 7521 | 4374 |
| 5a83b05_3 | no_probe | False | True | 9 | 0 | 3230 | 7939 |
| 634f342_1 | no_probe | False | False | 2 | 0 | 2158 | 69902 |
| 634f342_2 | no_probe | False | True | 18 | 0 | 7094 | 25931 |
| 634f342_3 | no_probe | False | False | 28 | 0 | 59653 | 21461 |
| 652485c_1 | no_probe | False | False | 30 | 0 | 16921 | 62218 |
| 652485c_2 | no_probe | False | False | 21 | 0 | 13396 | 59517 |
| 652485c_3 | no_probe | False | False | 14 | 0 | 12295 | 39618 |
| 6b6ca61_1 | no_probe | False | False | 20 | 0 | 18359 | 39037 |
| 6b6ca61_2 | no_probe | False | False | 21 | 0 | 13976 | 69750 |
| 6b6ca61_3 | no_probe | False | False | 27 | 0 | 13632 | 54829 |
| 6f4b9a5_1 | no_probe | False | False | 10 | 0 | 5233 | 21985 |
| 6f4b9a5_2 | no_probe | False | False | 30 | 0 | 4455 | 26468 |
| 6f4b9a5_3 | no_probe | False | False | 18 | 0 | 10496 | 32223 |
| 7847649_1 | no_probe | True | False | 8 | 0 | 3101 | 5176 |
| 7847649_2 | no_probe | False | False | 9 | 0 | 2462 | 15631 |
| 7847649_3 | no_probe | False | False | 8 | 0 | 2570 | 4563 |
| 83a7951_1 | no_probe | False | False | 13 | 0 | 8853 | 32935 |
| 83a7951_2 | no_probe | False | False | 17 | 0 | 8855 | 54882 |
| 83a7951_3 | no_probe | False | False | 12 | 0 | 7073 | 41370 |
| 8749218_1 | no_probe | False | True | 20 | 0 | 15121 | 22794 |
| 8749218_2 | no_probe | False | True | 5 | 0 | 1958 | 27120 |
| 8749218_3 | no_probe | False | True | 26 | 0 | 10093 | 21951 |
| 8ce6779_1 | no_probe | False | False | 15 | 0 | 6182 | 44035 |
| 8ce6779_2 | no_probe | False | False | 8 | 0 | 2708 | 30098 |
| 8ce6779_3 | no_probe | False | False | 30 | 0 | 4676 | 28472 |
| 9016950_1 | no_probe | False | True | 14 | 0 | 11279 | 32313 |
| 9016950_2 | no_probe | False | False | 6 | 0 | 2850 | 40412 |
| 9016950_3 | no_probe | False | False | 17 | 0 | 7375 | 34910 |
| 90adc3f_1 | no_probe | False | False | 7 | 0 | 3307 | 13653 |
| 90adc3f_2 | no_probe | False | False | 10 | 0 | 2706 | 22471 |
| 90adc3f_3 | no_probe | False | False | 12 | 0 | 6249 | 32902 |
| 986aa4e_1 | no_probe | False | False | 9 | 0 | 7393 | 54113 |
| 986aa4e_2 | no_probe | False | False | 30 | 0 | 27832 | 71548 |
| 986aa4e_3 | no_probe | False | False | 30 | 0 | 40773 | 75990 |
| 9dabbc9_1 | no_probe | False | True | 9 | 0 | 2766 | 19519 |
| 9dabbc9_2 | no_probe | False | False | 9 | 0 | 8505 | 21459 |
| 9dabbc9_3 | no_probe | False | False | 13 | 0 | 4319 | 28714 |
| 9ef798c_1 | no_probe | False | True | 24 | 0 | 16602 | 26112 |
| 9ef798c_2 | no_probe | False | False | 12 | 0 | 3162 | 38053 |
| 9ef798c_3 | no_probe | False | False | 26 | 0 | 10773 | 98326 |
| a30375d_1 | no_probe | False | False | 8 | 0 | 2561 | 7725 |
| a30375d_2 | no_probe | True | False | 11 | 0 | 3418 | 21907 |
| a30375d_3 | no_probe | False | False | 6 | 0 | 1419 | 75855 |
| afc4005_1 | no_probe | True | False | 8 | 0 | 1662 | 11920 |
| afc4005_2 | no_probe | False | False | 10 | 0 | 5272 | 9209 |
| afc4005_3 | no_probe | False | False | 10 | 0 | 6624 | 24109 |
| b6d1104_1 | no_probe | False | False | 10 | 0 | 3521 | 5856 |
| b6d1104_2 | no_probe | False | False | 18 | 0 | 11549 | 26032 |
| b6d1104_3 | no_probe | False | False | 13 | 0 | 7053 | 18806 |
| b9c5c9a_1 | no_probe | False | False | 22 | 0 | 22172 | 78109 |
| b9c5c9a_2 | no_probe | False | False | 23 | 0 | 24604 | 76753 |
| b9c5c9a_3 | no_probe | False | False | 4 | 0 | 1866 | 67265 |
| bde252e_1 | no_probe | False | False | 18 | 0 | 25422 | 63809 |
| bde252e_2 | no_probe | False | False | 16 | 0 | 8204 | 33853 |
| bde252e_3 | no_probe | False | False | 15 | 0 | 10438 | 93274 |
| c77c005_1 | no_probe | False | False | 7 | 0 | 2911 | 14051 |
| c77c005_2 | no_probe | False | True | 15 | 0 | 8136 | 12428 |
| c77c005_3 | no_probe | False | True | 13 | 0 | 7491 | 19445 |
| ccf4b82_1 | no_probe | False | False | 14 | 0 | 6958 | 23475 |
| ccf4b82_2 | no_probe | False | False | 8 | 0 | 2340 | 28854 |
| ccf4b82_3 | no_probe | False | True | 16 | 0 | 9475 | 33688 |
| cef9191_1 | no_probe | False | False | 13 | 0 | 10485 | 30538 |
| cef9191_2 | no_probe | False | True | 9 | 0 | 8176 | 10159 |
| cef9191_3 | no_probe | False | True | 30 | 0 | 23225 | 14634 |
| d18139b_1 | no_probe | False | False | 23 | 0 | 15443 | 43586 |
| d18139b_2 | no_probe | False | False | 19 | 0 | 9555 | 24234 |
| d18139b_3 | no_probe | False | False | 13 | 0 | 10044 | 16118 |
| d194965_1 | no_probe | False | False | 15 | 0 | 5389 | 47486 |
| d194965_2 | no_probe | False | False | 18 | 0 | 14991 | 50222 |
| d194965_3 | no_probe | False | False | 16 | 0 | 5918 | 41996 |
| d6ac34d_1 | no_probe | False | False | 14 | 0 | 4538 | 12303 |
| d6ac34d_2 | no_probe | False | False | 30 | 0 | 4817 | 11910 |
| d6ac34d_3 | no_probe | False | False | 7 | 0 | 2618 | 13326 |
| dac78d9_1 | no_probe | False | False | 9 | 0 | 2986 | 13228 |
| dac78d9_2 | no_probe | False | False | 9 | 0 | 2598 | 6809 |
| dac78d9_3 | no_probe | False | False | 5 | 0 | 1510 | 8042 |
| f323bae_1 | no_probe | False | True | 18 | 0 | 13497 | 38212 |
| f323bae_2 | no_probe | False | False | 11 | 0 | 4948 | 23708 |
| f323bae_3 | no_probe | False | True | 22 | 0 | 13121 | 31488 |
| f3f60f0_1 | no_probe | False | True | 7 | 0 | 3129 | 16576 |
| f3f60f0_2 | no_probe | False | True | 9 | 0 | 2559 | 12391 |
| f3f60f0_3 | no_probe | False | True | 8 | 0 | 5108 | 7534 |
| f861c32_1 | no_probe | False | False | 19 | 0 | 12591 | 61497 |
| f861c32_2 | no_probe | False | False | 11 | 0 | 9251 | 34019 |
| f861c32_3 | no_probe | False | False | 30 | 0 | 22761 | 19731 |
| fd1f8fa_1 | no_probe | False | False | 2 | 0 | 2842 | 42707 |
| fd1f8fa_2 | no_probe | False | False | 14 | 0 | 4120 | 25197 |
| fd1f8fa_3 | no_probe | False | False | 15 | 0 | 9366 | 50415 |
| ff58e36_1 | no_probe | False | True | 2 | 0 | 2492 | 20354 |
| ff58e36_2 | no_probe | False | True | 2 | 0 | 1918 | 32719 |
| ff58e36_3 | no_probe | False | True | 30 | 0 | 7329 | 24444 |
| ffe6d5e_1 | no_probe | False | False | 8 | 0 | 3862 | 11978 |
| ffe6d5e_2 | no_probe | False | False | 6 | 0 | 1100 | 17999 |
| ffe6d5e_3 | no_probe | False | False | 8 | 0 | 3048 | 7383 |
