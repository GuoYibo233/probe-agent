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
| live_success | 0.119 |
| base_success | 0.2857 |
| live_success_paired | 0.119 |
| inject_per_task | 1.3452 |
| billed_tok_sum | 5322678 |
| base_out_tok_sum | 4789358 |
| n_spec | 226 |
| spec_exec_ok | 0.9867 |
| spec_tool_agree | 0.1947 |
| spec_call_agree | 0.1195 |
| spec_recalled | 0.1947 |
| spec_error_kinds | {'AttributeError': 1, 'http_422': 2} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 024c982_1 | probe | False | False | 20 | 2 | 62723 | 15596 |
| 024c982_2 | probe | False | True | 10 | 1 | 14764 | 23295 |
| 024c982_3 | probe | False | False | 11 | 1 | 12029 | 5181 |
| 042a9fc_1 | probe | False | False | 20 | 2 | 65808 | 89381 |
| 042a9fc_2 | probe | False | False | 22 | 2 | 62292 | 31817 |
| 042a9fc_3 | probe | False | False | 17 | 2 | 16523 | 27816 |
| 09b0ee6_1 | probe | True | True | 9 | 2 | 15322 | 5847 |
| 09b0ee6_2 | probe | True | True | 8 | 1 | 8259 | 9513 |
| 09b0ee6_3 | probe | True | True | 8 | 1 | 11839 | 17628 |
| 0a9d82a_1 | probe | True | True | 13 | 1 | 35117 | 9925 |
| 0a9d82a_2 | probe | True | True | 10 | 1 | 59223 | 29053 |
| 0a9d82a_3 | probe | False | False | 11 | 1 | 34311 | 13243 |
| 0d01c76_1 | probe | False | True | 14 | 2 | 16102 | 12687 |
| 0d01c76_2 | probe | False | True | 12 | 2 | 62641 | 21351 |
| 0d01c76_3 | probe | True | True | 9 | 2 | 14044 | 34251 |
| 0de03ea_1 | probe | False | False | 29 | 2 | 38458 | 20916 |
| 0de03ea_2 | probe | False | False | 8 | 1 | 17524 | 18773 |
| 0de03ea_3 | probe | False | False | 8 | 1 | 17446 | 7754 |
| 1150ed6_1 | probe | False | False | 5 | 1 | 8312 | 35426 |
| 1150ed6_2 | probe | False | False | 11 | 1 | 24424 | 18318 |
| 1150ed6_3 | probe | False | True | 8 | 1 | 8466 | 27132 |
| 13547f5_1 | probe | False | True | 13 | 2 | 30039 | 5692 |
| 13547f5_2 | probe | False | False | 14 | 1 | 30922 | 73306 |
| 13547f5_3 | probe | False | True | 12 | 1 | 26083 | 6302 |
| 166f4ff_1 | probe | False | False | 5 | 1 | 7515 | 5529 |
| 166f4ff_2 | probe | False | False | 7 | 1 | 16744 | 5680 |
| 166f4ff_3 | probe | False | False | 8 | 1 | 23274 | 5228 |
| 21abae1_1 | probe | False | False | 6 | 1 | 8706 | 18842 |
| 21abae1_2 | probe | False | False | 6 | 2 | 7192 | 10414 |
| 21abae1_3 | probe | False | False | 5 | 1 | 12555 | 10511 |
| 270f1ff_1 | probe | False | False | 14 | 1 | 29540 | 34993 |
| 270f1ff_2 | probe | False | False | 15 | 1 | 59051 | 33694 |
| 270f1ff_3 | probe | False | False | 13 | 2 | 63649 | 36340 |
| 29a7b7e_1 | probe | False | True | 10 | 1 | 10782 | 27400 |
| 29a7b7e_2 | probe | False | False | 11 | 1 | 27292 | 19024 |
| 29a7b7e_3 | probe | True | False | 13 | 1 | 14977 | 16355 |
| 2c544f9_1 | probe | False | False | 11 | 1 | 24651 | 108328 |
| 2c544f9_2 | probe | False | False | 11 | 1 | 22715 | 31187 |
| 2c544f9_3 | probe | False | False | 14 | 1 | 50081 | 62994 |
| 2d9f728_1 | probe | False | False | 14 | 2 | 30263 | 22354 |
| 2d9f728_2 | probe | False | False | 15 | 1 | 48112 | 55276 |
| 2d9f728_3 | probe | False | False | 8 | 3 | 20811 | 43248 |
| 31dc501_1 | probe | False | True | 9 | 2 | 23334 | 24559 |
| 31dc501_2 | probe | True | True | 9 | 2 | 12709 | 14910 |
| 31dc501_3 | probe | False | True | 26 | 1 | 17784 | 17396 |
| 325d6ec_1 | probe | False | True | 10 | 2 | 13674 | 12394 |
| 325d6ec_2 | probe | False | False | 13 | 1 | 62993 | 9918 |
| 325d6ec_3 | probe | False | False | 4 | 1 | 7284 | 14248 |
| 32616b5_1 | probe | False | False | 12 | 1 | 27321 | 29076 |
| 32616b5_2 | probe | False | False | 11 | 1 | 60477 | 33822 |
| 32616b5_3 | probe | False | False | 12 | 1 | 63318 | 30370 |
| 3aa1a22_1 | probe | False | False | 12 | 1 | 64143 | 30156 |
| 3aa1a22_2 | probe | False | False | 14 | 2 | 48761 | 28242 |
| 3aa1a22_3 | probe | False | False | 25 | 2 | 56266 | 20774 |
| 3b8fb7a_1 | probe | False | False | 18 | 1 | 59089 | 33105 |
| 3b8fb7a_2 | probe | False | False | 11 | 1 | 59623 | 53306 |
| 3b8fb7a_3 | probe | False | True | 15 | 1 | 60976 | 39689 |
| 3d9a636_1 | probe | False | False | 9 | 2 | 42529 | 29234 |
| 3d9a636_2 | probe | False | True | 10 | 3 | 18721 | 21401 |
| 3d9a636_3 | probe | False | False | 14 | 2 | 30792 | 36228 |
| 425a494_1 | probe | False | False | 7 | 1 | 15084 | 5562 |
| 425a494_2 | probe | False | True | 6 | 1 | 18859 | 27472 |
| 425a494_3 | probe | False | False | 13 | 2 | 63142 | 7918 |
| 522e5e5_1 | probe | False | True | 10 | 1 | 13279 | 14422 |
| 522e5e5_2 | probe | False | True | 12 | 1 | 33421 | 16094 |
| 522e5e5_3 | probe | False | False | 8 | 1 | 10205 | 14281 |
| 552869a_1 | probe | False | False | 7 | 1 | 6724 | 11634 |
| 552869a_2 | probe | False | False | 5 | 2 | 7952 | 6799 |
| 552869a_3 | probe | False | False | 4 | 1 | 3688 | 4813 |
| 59fae45_1 | probe | True | True | 8 | 1 | 12682 | 8305 |
| 59fae45_2 | probe | False | True | 10 | 1 | 32246 | 17881 |
| 59fae45_3 | probe | False | True | 9 | 1 | 22915 | 16291 |
| 5a83b05_1 | probe | False | True | 6 | 1 | 14342 | 7318 |
| 5a83b05_2 | probe | False | True | 9 | 1 | 8224 | 4374 |
| 5a83b05_3 | probe | True | True | 17 | 2 | 30870 | 7939 |
| 634f342_1 | probe | False | False | 16 | 2 | 58241 | 69902 |
| 634f342_2 | probe | False | True | 13 | 1 | 55920 | 25931 |
| 634f342_3 | probe | False | False | 8 | 1 | 29664 | 21461 |
| 652485c_1 | probe | False | False | 22 | 2 | 55924 | 62218 |
| 652485c_2 | probe | False | False | 24 | 2 | 39585 | 59517 |
| 652485c_3 | probe | False | False | 10 | 2 | 57916 | 39618 |
| 6b6ca61_1 | probe | False | False | 30 | 1 | 57770 | 39037 |
| 6b6ca61_2 | probe | False | False | 16 | 1 | 62948 | 69750 |
| 6b6ca61_3 | probe | False | False | 16 | 3 | 38958 | 54829 |
| 6f4b9a5_1 | probe | True | False | 10 | 1 | 13886 | 21985 |
| 6f4b9a5_2 | probe | True | False | 15 | 1 | 33972 | 26468 |
| 6f4b9a5_3 | probe | False | False | 20 | 1 | 41463 | 32223 |
| 7847649_1 | probe | False | False | 8 | 2 | 17184 | 5176 |
| 7847649_2 | probe | False | False | 2 | 2 | 2813 | 15631 |
| 7847649_3 | probe | False | False | 8 | 1 | 18283 | 4563 |
| 83a7951_1 | probe | False | False | 28 | 1 | 47563 | 32935 |
| 83a7951_2 | probe | False | False | 30 | 1 | 40051 | 54882 |
| 83a7951_3 | probe | False | False | 13 | 2 | 57010 | 41370 |
| 8749218_1 | probe | False | True | 8 | 1 | 28715 | 22794 |
| 8749218_2 | probe | False | True | 11 | 1 | 60412 | 27120 |
| 8749218_3 | probe | False | True | 6 | 1 | 18195 | 21951 |
| 8ce6779_1 | probe | False | False | 21 | 1 | 43448 | 44035 |
| 8ce6779_2 | probe | False | False | 16 | 1 | 37410 | 30098 |
| 8ce6779_3 | probe | False | False | 11 | 1 | 23553 | 28472 |
| 9016950_1 | probe | False | True | 19 | 2 | 54131 | 32313 |
| 9016950_2 | probe | False | False | 11 | 1 | 23199 | 40412 |
| 9016950_3 | probe | False | False | 13 | 1 | 57746 | 34910 |
| 90adc3f_1 | probe | True | False | 10 | 2 | 31580 | 13653 |
| 90adc3f_2 | probe | False | False | 11 | 2 | 32487 | 22471 |
| 90adc3f_3 | probe | False | False | 15 | 2 | 60550 | 32902 |
| 986aa4e_1 | probe | False | False | 17 | 2 | 62832 | 54113 |
| 986aa4e_2 | probe | False | False | 16 | 1 | 37333 | 71548 |
| 986aa4e_3 | probe | False | False | 18 | 1 | 45647 | 75990 |
| 9dabbc9_1 | probe | False | True | 13 | 1 | 66654 | 19519 |
| 9dabbc9_2 | probe | False | False | 30 | 1 | 67242 | 21459 |
| 9dabbc9_3 | probe | False | False | 11 | 1 | 15516 | 28714 |
| 9ef798c_1 | probe | False | True | 10 | 1 | 11854 | 26112 |
| 9ef798c_2 | probe | False | False | 15 | 1 | 19224 | 38053 |
| 9ef798c_3 | probe | False | False | 30 | 1 | 50206 | 98326 |
| a30375d_1 | probe | True | False | 10 | 1 | 39032 | 7725 |
| a30375d_2 | probe | False | False | 9 | 1 | 8354 | 21907 |
| a30375d_3 | probe | False | False | 9 | 1 | 16594 | 75855 |
| afc4005_1 | probe | False | False | 5 | 1 | 8140 | 11920 |
| afc4005_2 | probe | False | False | 7 | 1 | 9868 | 9209 |
| afc4005_3 | probe | False | False | 7 | 1 | 21795 | 24109 |
| b6d1104_1 | probe | False | False | 13 | 1 | 46693 | 5856 |
| b6d1104_2 | probe | False | False | 14 | 1 | 31897 | 26032 |
| b6d1104_3 | probe | False | False | 13 | 1 | 26739 | 18806 |
| b9c5c9a_1 | probe | False | False | 24 | 2 | 61866 | 78109 |
| b9c5c9a_2 | probe | False | False | 24 | 2 | 43988 | 76753 |
| b9c5c9a_3 | probe | False | False | 17 | 1 | 48323 | 67265 |
| bde252e_1 | probe | False | False | 18 | 1 | 30430 | 63809 |
| bde252e_2 | probe | False | False | 30 | 2 | 60931 | 33853 |
| bde252e_3 | probe | False | False | 25 | 1 | 64839 | 93274 |
| c77c005_1 | probe | False | False | 12 | 1 | 62961 | 14051 |
| c77c005_2 | probe | True | True | 8 | 1 | 13663 | 12428 |
| c77c005_3 | probe | False | True | 12 | 1 | 20904 | 19445 |
| ccf4b82_1 | probe | False | False | 14 | 1 | 25001 | 23475 |
| ccf4b82_2 | probe | False | False | 9 | 1 | 13144 | 28854 |
| ccf4b82_3 | probe | False | True | 12 | 1 | 10323 | 33688 |
| cef9191_1 | probe | True | False | 10 | 1 | 26414 | 30538 |
| cef9191_2 | probe | False | True | 10 | 1 | 28130 | 10159 |
| cef9191_3 | probe | True | True | 8 | 1 | 18840 | 14634 |
| d18139b_1 | probe | False | False | 11 | 2 | 25708 | 43586 |
| d18139b_2 | probe | False | False | 6 | 2 | 6327 | 24234 |
| d18139b_3 | probe | False | False | 13 | 2 | 50425 | 16118 |
| d194965_1 | probe | False | False | 11 | 2 | 55110 | 47486 |
| d194965_2 | probe | False | False | 10 | 2 | 22422 | 50222 |
| d194965_3 | probe | False | False | 12 | 1 | 29521 | 41996 |
| d6ac34d_1 | probe | False | False | 9 | 1 | 7591 | 12303 |
| d6ac34d_2 | probe | False | False | 5 | 1 | 5166 | 11910 |
| d6ac34d_3 | probe | False | False | 19 | 1 | 34618 | 13326 |
| dac78d9_1 | probe | False | False | 5 | 1 | 10827 | 13228 |
| dac78d9_2 | probe | True | False | 8 | 3 | 6805 | 6809 |
| dac78d9_3 | probe | False | False | 6 | 1 | 7361 | 8042 |
| f323bae_1 | probe | False | True | 13 | 1 | 30351 | 38212 |
| f323bae_2 | probe | False | False | 22 | 1 | 51130 | 23708 |
| f323bae_3 | probe | False | True | 9 | 1 | 12313 | 31488 |
| f3f60f0_1 | probe | True | True | 11 | 3 | 16846 | 16576 |
| f3f60f0_2 | probe | False | True | 11 | 3 | 14111 | 12391 |
| f3f60f0_3 | probe | True | True | 5 | 1 | 6603 | 7534 |
| f861c32_1 | probe | False | False | 12 | 1 | 57108 | 61497 |
| f861c32_2 | probe | False | False | 14 | 1 | 58218 | 34019 |
| f861c32_3 | probe | False | False | 28 | 2 | 65098 | 19731 |
| fd1f8fa_1 | probe | False | False | 9 | 1 | 15783 | 42707 |
| fd1f8fa_2 | probe | False | False | 21 | 2 | 62204 | 25197 |
| fd1f8fa_3 | probe | False | False | 5 | 1 | 14204 | 50415 |
| ff58e36_1 | probe | False | True | 21 | 2 | 40237 | 20354 |
| ff58e36_2 | probe | False | True | 19 | 1 | 58338 | 32719 |
| ff58e36_3 | probe | False | True | 7 | 1 | 7271 | 24444 |
| ffe6d5e_1 | probe | False | False | 7 | 1 | 8784 | 11978 |
| ffe6d5e_2 | probe | False | False | 10 | 1 | 18315 | 17999 |
| ffe6d5e_3 | probe | False | False | 14 | 1 | 13921 | 7383 |
