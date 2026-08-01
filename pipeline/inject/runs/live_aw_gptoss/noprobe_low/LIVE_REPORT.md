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
| live_success | 0.0655 |
| base_success | 0.2857 |
| live_success_paired | 0.0655 |
| inject_per_task | 0.0 |
| billed_tok_sum | 519734 |
| base_out_tok_sum | 4789358 |
| n_spec | 0 |
| spec_exec_ok | None |
| spec_tool_agree | None |
| spec_call_agree | None |
| spec_recalled | None |
| spec_error_kinds | {} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 024c982_1 | no_probe | False | False | 10 | 0 | 1186 | 15596 |
| 024c982_2 | no_probe | False | True | 19 | 0 | 1967 | 23295 |
| 024c982_3 | no_probe | False | False | 20 | 0 | 5699 | 5181 |
| 042a9fc_1 | no_probe | False | False | 17 | 0 | 3085 | 89381 |
| 042a9fc_2 | no_probe | False | False | 16 | 0 | 2815 | 31817 |
| 042a9fc_3 | no_probe | False | False | 15 | 0 | 2383 | 27816 |
| 09b0ee6_1 | no_probe | True | True | 9 | 0 | 1108 | 5847 |
| 09b0ee6_2 | no_probe | False | True | 9 | 0 | 1360 | 9513 |
| 09b0ee6_3 | no_probe | True | True | 10 | 0 | 978 | 17628 |
| 0a9d82a_1 | no_probe | False | True | 9 | 0 | 1356 | 9925 |
| 0a9d82a_2 | no_probe | False | True | 8 | 0 | 883 | 29053 |
| 0a9d82a_3 | no_probe | False | False | 8 | 0 | 2958 | 13243 |
| 0d01c76_1 | no_probe | True | True | 13 | 0 | 2095 | 12687 |
| 0d01c76_2 | no_probe | True | True | 12 | 0 | 1716 | 21351 |
| 0d01c76_3 | no_probe | True | True | 18 | 0 | 3572 | 34251 |
| 0de03ea_1 | no_probe | False | False | 12 | 0 | 3160 | 20916 |
| 0de03ea_2 | no_probe | False | False | 9 | 0 | 1370 | 18773 |
| 0de03ea_3 | no_probe | False | False | 12 | 0 | 3126 | 7754 |
| 1150ed6_1 | no_probe | False | False | 8 | 0 | 1013 | 35426 |
| 1150ed6_2 | no_probe | False | False | 16 | 0 | 3412 | 18318 |
| 1150ed6_3 | no_probe | False | True | 7 | 0 | 2111 | 27132 |
| 13547f5_1 | no_probe | False | True | 11 | 0 | 914 | 5692 |
| 13547f5_2 | no_probe | False | False | 12 | 0 | 834 | 73306 |
| 13547f5_3 | no_probe | False | True | 14 | 0 | 1841 | 6302 |
| 166f4ff_1 | no_probe | False | False | 6 | 0 | 605 | 5529 |
| 166f4ff_2 | no_probe | False | False | 10 | 0 | 969 | 5680 |
| 166f4ff_3 | no_probe | False | False | 8 | 0 | 799 | 5228 |
| 21abae1_1 | no_probe | False | False | 9 | 0 | 882 | 18842 |
| 21abae1_2 | no_probe | False | False | 10 | 0 | 1025 | 10414 |
| 21abae1_3 | no_probe | False | False | 10 | 0 | 803 | 10511 |
| 270f1ff_1 | no_probe | False | False | 14 | 0 | 1702 | 34993 |
| 270f1ff_2 | no_probe | False | False | 18 | 0 | 2605 | 33694 |
| 270f1ff_3 | no_probe | False | False | 25 | 0 | 3545 | 36340 |
| 29a7b7e_1 | no_probe | True | True | 23 | 0 | 8178 | 27400 |
| 29a7b7e_2 | no_probe | True | False | 15 | 0 | 4617 | 19024 |
| 29a7b7e_3 | no_probe | False | False | 7 | 0 | 2029 | 16355 |
| 2c544f9_1 | no_probe | False | False | 30 | 0 | 7673 | 108328 |
| 2c544f9_2 | no_probe | False | False | 22 | 0 | 3624 | 31187 |
| 2c544f9_3 | no_probe | False | False | 21 | 0 | 6756 | 62994 |
| 2d9f728_1 | no_probe | False | False | 9 | 0 | 3215 | 22354 |
| 2d9f728_2 | no_probe | False | False | 18 | 0 | 5868 | 55276 |
| 2d9f728_3 | no_probe | False | False | 27 | 0 | 19082 | 43248 |
| 31dc501_1 | no_probe | False | True | 12 | 0 | 1690 | 24559 |
| 31dc501_2 | no_probe | False | True | 14 | 0 | 1940 | 14910 |
| 31dc501_3 | no_probe | False | True | 9 | 0 | 806 | 17396 |
| 325d6ec_1 | no_probe | False | True | 16 | 0 | 5656 | 12394 |
| 325d6ec_2 | no_probe | False | False | 10 | 0 | 1466 | 9918 |
| 325d6ec_3 | no_probe | False | False | 12 | 0 | 3272 | 14248 |
| 32616b5_1 | no_probe | False | False | 18 | 0 | 5511 | 29076 |
| 32616b5_2 | no_probe | False | False | 22 | 0 | 7148 | 33822 |
| 32616b5_3 | no_probe | False | False | 19 | 0 | 8229 | 30370 |
| 3aa1a22_1 | no_probe | False | False | 8 | 0 | 2847 | 30156 |
| 3aa1a22_2 | no_probe | False | False | 13 | 0 | 4261 | 28242 |
| 3aa1a22_3 | no_probe | False | False | 11 | 0 | 2048 | 20774 |
| 3b8fb7a_1 | no_probe | False | False | 21 | 0 | 5603 | 33105 |
| 3b8fb7a_2 | no_probe | False | False | 17 | 0 | 4641 | 53306 |
| 3b8fb7a_3 | no_probe | False | True | 16 | 0 | 2038 | 39689 |
| 3d9a636_1 | no_probe | False | False | 15 | 0 | 5593 | 29234 |
| 3d9a636_2 | no_probe | False | True | 30 | 0 | 13877 | 21401 |
| 3d9a636_3 | no_probe | False | False | 7 | 0 | 1732 | 36228 |
| 425a494_1 | no_probe | False | False | 10 | 0 | 779 | 5562 |
| 425a494_2 | no_probe | False | True | 9 | 0 | 3011 | 27472 |
| 425a494_3 | no_probe | False | False | 10 | 0 | 915 | 7918 |
| 522e5e5_1 | no_probe | False | True | 7 | 0 | 624 | 14422 |
| 522e5e5_2 | no_probe | False | True | 7 | 0 | 1002 | 16094 |
| 522e5e5_3 | no_probe | False | False | 4 | 0 | 570 | 14281 |
| 552869a_1 | no_probe | False | False | 7 | 0 | 1019 | 11634 |
| 552869a_2 | no_probe | False | False | 8 | 0 | 1532 | 6799 |
| 552869a_3 | no_probe | False | False | 10 | 0 | 1065 | 4813 |
| 59fae45_1 | no_probe | False | True | 11 | 0 | 2578 | 8305 |
| 59fae45_2 | no_probe | False | True | 9 | 0 | 1498 | 17881 |
| 59fae45_3 | no_probe | False | True | 9 | 0 | 1542 | 16291 |
| 5a83b05_1 | no_probe | False | True | 15 | 0 | 2726 | 7318 |
| 5a83b05_2 | no_probe | True | True | 14 | 0 | 2715 | 4374 |
| 5a83b05_3 | no_probe | False | True | 13 | 0 | 1974 | 7939 |
| 634f342_1 | no_probe | False | False | 20 | 0 | 3880 | 69902 |
| 634f342_2 | no_probe | False | True | 29 | 0 | 11198 | 25931 |
| 634f342_3 | no_probe | False | False | 12 | 0 | 3252 | 21461 |
| 652485c_1 | no_probe | False | False | 30 | 0 | 9381 | 62218 |
| 652485c_2 | no_probe | False | False | 20 | 0 | 3528 | 59517 |
| 652485c_3 | no_probe | False | False | 30 | 0 | 7622 | 39618 |
| 6b6ca61_1 | no_probe | False | False | 28 | 0 | 6488 | 39037 |
| 6b6ca61_2 | no_probe | False | False | 22 | 0 | 9289 | 69750 |
| 6b6ca61_3 | no_probe | False | False | 25 | 0 | 9904 | 54829 |
| 6f4b9a5_1 | no_probe | False | False | 10 | 0 | 1864 | 21985 |
| 6f4b9a5_2 | no_probe | False | False | 10 | 0 | 1922 | 26468 |
| 6f4b9a5_3 | no_probe | False | False | 10 | 0 | 1925 | 32223 |
| 7847649_1 | no_probe | True | False | 9 | 0 | 1251 | 5176 |
| 7847649_2 | no_probe | False | False | 3 | 0 | 631 | 15631 |
| 7847649_3 | no_probe | False | False | 9 | 0 | 1539 | 4563 |
| 83a7951_1 | no_probe | False | False | 10 | 0 | 3550 | 32935 |
| 83a7951_2 | no_probe | False | False | 8 | 0 | 3004 | 54882 |
| 83a7951_3 | no_probe | False | False | 29 | 0 | 20205 | 41370 |
| 8749218_1 | no_probe | False | True | 19 | 0 | 5369 | 22794 |
| 8749218_2 | no_probe | False | True | 11 | 0 | 1597 | 27120 |
| 8749218_3 | no_probe | False | True | 17 | 0 | 4159 | 21951 |
| 8ce6779_1 | no_probe | False | False | 8 | 0 | 816 | 44035 |
| 8ce6779_2 | no_probe | False | False | 17 | 0 | 4522 | 30098 |
| 8ce6779_3 | no_probe | False | False | 19 | 0 | 5695 | 28472 |
| 9016950_1 | no_probe | False | True | 30 | 0 | 2076 | 32313 |
| 9016950_2 | no_probe | False | False | 20 | 0 | 8258 | 40412 |
| 9016950_3 | no_probe | False | False | 10 | 0 | 1122 | 34910 |
| 90adc3f_1 | no_probe | False | False | 9 | 0 | 886 | 13653 |
| 90adc3f_2 | no_probe | False | False | 7 | 0 | 1226 | 22471 |
| 90adc3f_3 | no_probe | False | False | 20 | 0 | 4834 | 32902 |
| 986aa4e_1 | no_probe | False | False | 7 | 0 | 840 | 54113 |
| 986aa4e_2 | no_probe | False | False | 6 | 0 | 1065 | 71548 |
| 986aa4e_3 | no_probe | False | False | 12 | 0 | 2813 | 75990 |
| 9dabbc9_1 | no_probe | False | True | 11 | 0 | 2630 | 19519 |
| 9dabbc9_2 | no_probe | False | False | 17 | 0 | 1853 | 21459 |
| 9dabbc9_3 | no_probe | False | False | 10 | 0 | 1512 | 28714 |
| 9ef798c_1 | no_probe | False | True | 16 | 0 | 1819 | 26112 |
| 9ef798c_2 | no_probe | False | False | 23 | 0 | 2521 | 38053 |
| 9ef798c_3 | no_probe | False | False | 22 | 0 | 6018 | 98326 |
| a30375d_1 | no_probe | True | False | 13 | 0 | 1817 | 7725 |
| a30375d_2 | no_probe | False | False | 10 | 0 | 583 | 21907 |
| a30375d_3 | no_probe | True | False | 9 | 0 | 674 | 75855 |
| afc4005_1 | no_probe | False | False | 7 | 0 | 647 | 11920 |
| afc4005_2 | no_probe | False | False | 10 | 0 | 777 | 9209 |
| afc4005_3 | no_probe | False | False | 11 | 0 | 2118 | 24109 |
| b6d1104_1 | no_probe | False | False | 8 | 0 | 790 | 5856 |
| b6d1104_2 | no_probe | False | False | 9 | 0 | 976 | 26032 |
| b6d1104_3 | no_probe | False | False | 7 | 0 | 1097 | 18806 |
| b9c5c9a_1 | no_probe | False | False | 21 | 0 | 9579 | 78109 |
| b9c5c9a_2 | no_probe | False | False | 17 | 0 | 4242 | 76753 |
| b9c5c9a_3 | no_probe | False | False | 15 | 0 | 4508 | 67265 |
| bde252e_1 | no_probe | False | False | 12 | 0 | 1895 | 63809 |
| bde252e_2 | no_probe | False | False | 9 | 0 | 3051 | 33853 |
| bde252e_3 | no_probe | False | False | 6 | 0 | 1166 | 93274 |
| c77c005_1 | no_probe | False | False | 6 | 0 | 1912 | 14051 |
| c77c005_2 | no_probe | False | True | 7 | 0 | 940 | 12428 |
| c77c005_3 | no_probe | False | True | 7 | 0 | 2123 | 19445 |
| ccf4b82_1 | no_probe | False | False | 15 | 0 | 5597 | 23475 |
| ccf4b82_2 | no_probe | False | False | 10 | 0 | 2068 | 28854 |
| ccf4b82_3 | no_probe | False | True | 9 | 0 | 2443 | 33688 |
| cef9191_1 | no_probe | False | False | 12 | 0 | 1859 | 30538 |
| cef9191_2 | no_probe | False | True | 5 | 0 | 890 | 10159 |
| cef9191_3 | no_probe | False | True | 13 | 0 | 1919 | 14634 |
| d18139b_1 | no_probe | False | False | 12 | 0 | 3468 | 43586 |
| d18139b_2 | no_probe | False | False | 10 | 0 | 2124 | 24234 |
| d18139b_3 | no_probe | False | False | 11 | 0 | 1455 | 16118 |
| d194965_1 | no_probe | False | False | 19 | 0 | 6342 | 47486 |
| d194965_2 | no_probe | False | False | 22 | 0 | 4689 | 50222 |
| d194965_3 | no_probe | False | False | 17 | 0 | 5792 | 41996 |
| d6ac34d_1 | no_probe | False | False | 9 | 0 | 1416 | 12303 |
| d6ac34d_2 | no_probe | False | False | 10 | 0 | 900 | 11910 |
| d6ac34d_3 | no_probe | False | False | 7 | 0 | 1086 | 13326 |
| dac78d9_1 | no_probe | False | False | 8 | 0 | 833 | 13228 |
| dac78d9_2 | no_probe | False | False | 7 | 0 | 705 | 6809 |
| dac78d9_3 | no_probe | False | False | 6 | 0 | 737 | 8042 |
| f323bae_1 | no_probe | False | True | 14 | 0 | 3757 | 38212 |
| f323bae_2 | no_probe | False | False | 15 | 0 | 3901 | 23708 |
| f323bae_3 | no_probe | False | True | 15 | 0 | 6281 | 31488 |
| f3f60f0_1 | no_probe | False | True | 14 | 0 | 4561 | 16576 |
| f3f60f0_2 | no_probe | False | True | 10 | 0 | 3282 | 12391 |
| f3f60f0_3 | no_probe | False | True | 9 | 0 | 1160 | 7534 |
| f861c32_1 | no_probe | False | False | 12 | 0 | 3392 | 61497 |
| f861c32_2 | no_probe | False | False | 5 | 0 | 608 | 34019 |
| f861c32_3 | no_probe | False | False | 5 | 0 | 1054 | 19731 |
| fd1f8fa_1 | no_probe | False | False | 8 | 0 | 1076 | 42707 |
| fd1f8fa_2 | no_probe | False | False | 12 | 0 | 3008 | 25197 |
| fd1f8fa_3 | no_probe | False | False | 12 | 0 | 1434 | 50415 |
| ff58e36_1 | no_probe | False | True | 6 | 0 | 1178 | 20354 |
| ff58e36_2 | no_probe | False | True | 17 | 0 | 4453 | 32719 |
| ff58e36_3 | no_probe | False | True | 16 | 0 | 5916 | 24444 |
| ffe6d5e_1 | no_probe | False | False | 6 | 0 | 524 | 11978 |
| ffe6d5e_2 | no_probe | False | False | 7 | 0 | 654 | 17999 |
| ffe6d5e_3 | no_probe | False | False | 12 | 0 | 1386 | 7383 |
