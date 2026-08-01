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
| live_success | 0.0893 |
| base_success | 0.2857 |
| live_success_paired | 0.0893 |
| inject_per_task | 0.0595 |
| billed_tok_sum | 494590 |
| base_out_tok_sum | 4789358 |
| n_spec | 10 |
| spec_exec_ok | 1.0 |
| spec_tool_agree | 0.0 |
| spec_call_agree | 0.0 |
| spec_recalled | 0.0 |
| spec_error_kinds | {} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 024c982_1 | probe | False | False | 9 | 0 | 890 | 15596 |
| 024c982_2 | probe | False | True | 30 | 0 | 1409 | 23295 |
| 024c982_3 | probe | False | False | 11 | 0 | 2082 | 5181 |
| 042a9fc_1 | probe | False | False | 17 | 0 | 2597 | 89381 |
| 042a9fc_2 | probe | False | False | 20 | 0 | 2298 | 31817 |
| 042a9fc_3 | probe | False | False | 15 | 0 | 2283 | 27816 |
| 09b0ee6_1 | probe | True | True | 13 | 0 | 1653 | 5847 |
| 09b0ee6_2 | probe | False | True | 9 | 0 | 1206 | 9513 |
| 09b0ee6_3 | probe | True | True | 9 | 0 | 1049 | 17628 |
| 0a9d82a_1 | probe | False | True | 11 | 0 | 1565 | 9925 |
| 0a9d82a_2 | probe | False | True | 9 | 0 | 948 | 29053 |
| 0a9d82a_3 | probe | False | False | 7 | 0 | 1446 | 13243 |
| 0d01c76_1 | probe | True | True | 12 | 0 | 1956 | 12687 |
| 0d01c76_2 | probe | True | True | 23 | 0 | 5358 | 21351 |
| 0d01c76_3 | probe | True | True | 13 | 0 | 1607 | 34251 |
| 0de03ea_1 | probe | False | False | 10 | 0 | 2770 | 20916 |
| 0de03ea_2 | probe | False | False | 5 | 0 | 614 | 18773 |
| 0de03ea_3 | probe | False | False | 10 | 0 | 1745 | 7754 |
| 1150ed6_1 | probe | False | False | 13 | 0 | 3251 | 35426 |
| 1150ed6_2 | probe | False | False | 12 | 0 | 3544 | 18318 |
| 1150ed6_3 | probe | False | True | 13 | 0 | 2879 | 27132 |
| 13547f5_1 | probe | False | True | 12 | 0 | 766 | 5692 |
| 13547f5_2 | probe | True | False | 11 | 0 | 890 | 73306 |
| 13547f5_3 | probe | True | True | 17 | 0 | 2264 | 6302 |
| 166f4ff_1 | probe | False | False | 7 | 0 | 1044 | 5529 |
| 166f4ff_2 | probe | False | False | 7 | 0 | 690 | 5680 |
| 166f4ff_3 | probe | False | False | 6 | 0 | 908 | 5228 |
| 21abae1_1 | probe | False | False | 7 | 0 | 839 | 18842 |
| 21abae1_2 | probe | False | False | 7 | 0 | 737 | 10414 |
| 21abae1_3 | probe | False | False | 6 | 0 | 624 | 10511 |
| 270f1ff_1 | probe | False | False | 1 | 0 | 829 | 34993 |
| 270f1ff_2 | probe | False | False | 13 | 0 | 2238 | 33694 |
| 270f1ff_3 | probe | False | False | 30 | 0 | 2065 | 36340 |
| 29a7b7e_1 | probe | False | True | 28 | 0 | 8628 | 27400 |
| 29a7b7e_2 | probe | True | False | 30 | 0 | 10427 | 19024 |
| 29a7b7e_3 | probe | True | False | 19 | 0 | 7393 | 16355 |
| 2c544f9_1 | probe | False | False | 26 | 0 | 4339 | 108328 |
| 2c544f9_2 | probe | False | False | 12 | 0 | 2841 | 31187 |
| 2c544f9_3 | probe | False | False | 20 | 0 | 4975 | 62994 |
| 2d9f728_1 | probe | False | False | 11 | 1 | 3585 | 22354 |
| 2d9f728_2 | probe | False | False | 12 | 0 | 2598 | 55276 |
| 2d9f728_3 | probe | False | False | 20 | 0 | 5422 | 43248 |
| 31dc501_1 | probe | False | True | 8 | 0 | 801 | 24559 |
| 31dc501_2 | probe | False | True | 11 | 0 | 1536 | 14910 |
| 31dc501_3 | probe | False | True | 10 | 0 | 1041 | 17396 |
| 325d6ec_1 | probe | False | True | 6 | 1 | 628 | 12394 |
| 325d6ec_2 | probe | False | False | 9 | 0 | 1219 | 9918 |
| 325d6ec_3 | probe | False | False | 14 | 0 | 3146 | 14248 |
| 32616b5_1 | probe | False | False | 15 | 0 | 2139 | 29076 |
| 32616b5_2 | probe | False | False | 16 | 0 | 4433 | 33822 |
| 32616b5_3 | probe | False | False | 30 | 0 | 8878 | 30370 |
| 3aa1a22_1 | probe | False | False | 10 | 0 | 1299 | 30156 |
| 3aa1a22_2 | probe | False | False | 17 | 0 | 3316 | 28242 |
| 3aa1a22_3 | probe | False | False | 13 | 0 | 2873 | 20774 |
| 3b8fb7a_1 | probe | False | False | 8 | 0 | 2504 | 33105 |
| 3b8fb7a_2 | probe | False | False | 12 | 0 | 6982 | 53306 |
| 3b8fb7a_3 | probe | False | True | 19 | 0 | 6663 | 39689 |
| 3d9a636_1 | probe | False | False | 18 | 0 | 4095 | 29234 |
| 3d9a636_2 | probe | False | True | 6 | 0 | 997 | 21401 |
| 3d9a636_3 | probe | False | False | 13 | 0 | 2024 | 36228 |
| 425a494_1 | probe | True | False | 8 | 0 | 753 | 5562 |
| 425a494_2 | probe | False | True | 6 | 1 | 1240 | 27472 |
| 425a494_3 | probe | False | False | 8 | 0 | 1278 | 7918 |
| 522e5e5_1 | probe | False | True | 6 | 0 | 775 | 14422 |
| 522e5e5_2 | probe | False | True | 5 | 0 | 818 | 16094 |
| 522e5e5_3 | probe | False | False | 5 | 0 | 589 | 14281 |
| 552869a_1 | probe | False | False | 7 | 0 | 981 | 11634 |
| 552869a_2 | probe | False | False | 9 | 0 | 1373 | 6799 |
| 552869a_3 | probe | False | False | 9 | 0 | 1113 | 4813 |
| 59fae45_1 | probe | False | True | 5 | 1 | 1086 | 8305 |
| 59fae45_2 | probe | False | True | 7 | 1 | 1708 | 17881 |
| 59fae45_3 | probe | False | True | 8 | 1 | 1522 | 16291 |
| 5a83b05_1 | probe | False | True | 9 | 0 | 1518 | 7318 |
| 5a83b05_2 | probe | False | True | 16 | 0 | 2401 | 4374 |
| 5a83b05_3 | probe | False | True | 10 | 0 | 2138 | 7939 |
| 634f342_1 | probe | False | False | 9 | 0 | 3272 | 69902 |
| 634f342_2 | probe | False | True | 30 | 0 | 13680 | 25931 |
| 634f342_3 | probe | False | False | 7 | 0 | 2144 | 21461 |
| 652485c_1 | probe | False | False | 30 | 0 | 12076 | 62218 |
| 652485c_2 | probe | False | False | 30 | 0 | 11245 | 59517 |
| 652485c_3 | probe | False | False | 30 | 0 | 24514 | 39618 |
| 6b6ca61_1 | probe | False | False | 30 | 0 | 13440 | 39037 |
| 6b6ca61_2 | probe | False | False | 21 | 0 | 11528 | 69750 |
| 6b6ca61_3 | probe | False | False | 16 | 0 | 7860 | 54829 |
| 6f4b9a5_1 | probe | False | False | 15 | 1 | 2622 | 21985 |
| 6f4b9a5_2 | probe | False | False | 9 | 0 | 1153 | 26468 |
| 6f4b9a5_3 | probe | False | False | 10 | 0 | 2454 | 32223 |
| 7847649_1 | probe | False | False | 13 | 0 | 2273 | 5176 |
| 7847649_2 | probe | True | False | 6 | 0 | 514 | 15631 |
| 7847649_3 | probe | False | False | 7 | 0 | 714 | 4563 |
| 83a7951_1 | probe | False | False | 15 | 0 | 5661 | 32935 |
| 83a7951_2 | probe | False | False | 20 | 0 | 3621 | 54882 |
| 83a7951_3 | probe | False | False | 9 | 0 | 2952 | 41370 |
| 8749218_1 | probe | False | True | 8 | 0 | 692 | 22794 |
| 8749218_2 | probe | False | True | 10 | 0 | 1355 | 27120 |
| 8749218_3 | probe | False | True | 11 | 0 | 1760 | 21951 |
| 8ce6779_1 | probe | False | False | 5 | 0 | 1364 | 44035 |
| 8ce6779_2 | probe | False | False | 14 | 0 | 1363 | 30098 |
| 8ce6779_3 | probe | False | False | 18 | 0 | 2073 | 28472 |
| 9016950_1 | probe | True | True | 12 | 0 | 1657 | 32313 |
| 9016950_2 | probe | False | False | 19 | 0 | 4553 | 40412 |
| 9016950_3 | probe | False | False | 10 | 0 | 4477 | 34910 |
| 90adc3f_1 | probe | False | False | 13 | 0 | 3542 | 13653 |
| 90adc3f_2 | probe | False | False | 8 | 0 | 1766 | 22471 |
| 90adc3f_3 | probe | False | False | 16 | 0 | 3395 | 32902 |
| 986aa4e_1 | probe | False | False | 9 | 0 | 1237 | 54113 |
| 986aa4e_2 | probe | False | False | 8 | 0 | 3752 | 71548 |
| 986aa4e_3 | probe | False | False | 13 | 0 | 7612 | 75990 |
| 9dabbc9_1 | probe | False | True | 14 | 0 | 3818 | 19519 |
| 9dabbc9_2 | probe | False | False | 14 | 0 | 3985 | 21459 |
| 9dabbc9_3 | probe | False | False | 11 | 0 | 1463 | 28714 |
| 9ef798c_1 | probe | False | True | 25 | 0 | 5398 | 26112 |
| 9ef798c_2 | probe | False | False | 18 | 0 | 3052 | 38053 |
| 9ef798c_3 | probe | False | False | 22 | 0 | 4967 | 98326 |
| a30375d_1 | probe | True | False | 13 | 0 | 1456 | 7725 |
| a30375d_2 | probe | True | False | 9 | 0 | 766 | 21907 |
| a30375d_3 | probe | True | False | 14 | 0 | 1315 | 75855 |
| afc4005_1 | probe | False | False | 8 | 0 | 631 | 11920 |
| afc4005_2 | probe | False | False | 13 | 0 | 2034 | 9209 |
| afc4005_3 | probe | False | False | 9 | 0 | 1240 | 24109 |
| b6d1104_1 | probe | False | False | 9 | 0 | 897 | 5856 |
| b6d1104_2 | probe | False | False | 10 | 0 | 1302 | 26032 |
| b6d1104_3 | probe | False | False | 9 | 0 | 1070 | 18806 |
| b9c5c9a_1 | probe | False | False | 20 | 0 | 6533 | 78109 |
| b9c5c9a_2 | probe | False | False | 14 | 0 | 4152 | 76753 |
| b9c5c9a_3 | probe | False | False | 18 | 0 | 6283 | 67265 |
| bde252e_1 | probe | False | False | 7 | 0 | 1646 | 63809 |
| bde252e_2 | probe | False | False | 9 | 0 | 2669 | 33853 |
| bde252e_3 | probe | False | False | 8 | 0 | 1397 | 93274 |
| c77c005_1 | probe | False | False | 8 | 0 | 3051 | 14051 |
| c77c005_2 | probe | False | True | 7 | 0 | 1803 | 12428 |
| c77c005_3 | probe | False | True | 5 | 0 | 1487 | 19445 |
| ccf4b82_1 | probe | False | False | 12 | 0 | 2607 | 23475 |
| ccf4b82_2 | probe | False | False | 10 | 0 | 1732 | 28854 |
| ccf4b82_3 | probe | False | True | 8 | 0 | 1201 | 33688 |
| cef9191_1 | probe | False | False | 9 | 0 | 1384 | 30538 |
| cef9191_2 | probe | False | True | 10 | 0 | 1010 | 10159 |
| cef9191_3 | probe | False | True | 18 | 0 | 3803 | 14634 |
| d18139b_1 | probe | False | False | 10 | 1 | 2462 | 43586 |
| d18139b_2 | probe | False | False | 7 | 0 | 622 | 24234 |
| d18139b_3 | probe | False | False | 9 | 0 | 1067 | 16118 |
| d194965_1 | probe | False | False | 15 | 0 | 6036 | 47486 |
| d194965_2 | probe | False | False | 22 | 0 | 5787 | 50222 |
| d194965_3 | probe | False | False | 19 | 0 | 5859 | 41996 |
| d6ac34d_1 | probe | False | False | 10 | 0 | 2142 | 12303 |
| d6ac34d_2 | probe | False | False | 6 | 0 | 690 | 11910 |
| d6ac34d_3 | probe | False | False | 7 | 0 | 2148 | 13326 |
| dac78d9_1 | probe | False | False | 10 | 0 | 2297 | 13228 |
| dac78d9_2 | probe | False | False | 6 | 0 | 625 | 6809 |
| dac78d9_3 | probe | False | False | 24 | 0 | 6315 | 8042 |
| f323bae_1 | probe | False | True | 6 | 0 | 1651 | 38212 |
| f323bae_2 | probe | False | False | 16 | 0 | 5068 | 23708 |
| f323bae_3 | probe | False | True | 16 | 0 | 2669 | 31488 |
| f3f60f0_1 | probe | False | True | 6 | 0 | 1099 | 16576 |
| f3f60f0_2 | probe | False | True | 6 | 1 | 1791 | 12391 |
| f3f60f0_3 | probe | False | True | 11 | 0 | 2176 | 7534 |
| f861c32_1 | probe | False | False | 17 | 0 | 5468 | 61497 |
| f861c32_2 | probe | False | False | 11 | 0 | 4301 | 34019 |
| f861c32_3 | probe | False | False | 10 | 0 | 1359 | 19731 |
| fd1f8fa_1 | probe | False | False | 5 | 0 | 684 | 42707 |
| fd1f8fa_2 | probe | False | False | 4 | 0 | 377 | 25197 |
| fd1f8fa_3 | probe | False | False | 15 | 0 | 1387 | 50415 |
| ff58e36_1 | probe | False | True | 22 | 0 | 4663 | 20354 |
| ff58e36_2 | probe | False | True | 16 | 1 | 3780 | 32719 |
| ff58e36_3 | probe | False | True | 6 | 0 | 1247 | 24444 |
| ffe6d5e_1 | probe | False | False | 8 | 0 | 1029 | 11978 |
| ffe6d5e_2 | probe | False | False | 7 | 0 | 1198 | 17999 |
| ffe6d5e_3 | probe | False | False | 11 | 0 | 1001 | 7383 |
