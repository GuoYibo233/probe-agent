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
| billed_tok_sum | 5719476 |
| base_out_tok_sum | 4789358 |
| n_spec | 0 |
| spec_exec_ok | None |
| spec_tool_agree | None |
| spec_call_agree | None |
| spec_recalled | None |
| spec_error_kinds | {} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 024c982_1 | no_probe | True | False | 10 | 0 | 18852 | 15596 |
| 024c982_2 | no_probe | False | True | 7 | 0 | 4113 | 23295 |
| 024c982_3 | no_probe | False | False | 11 | 0 | 31355 | 5181 |
| 042a9fc_1 | no_probe | False | False | 29 | 0 | 56022 | 89381 |
| 042a9fc_2 | no_probe | False | False | 11 | 0 | 59190 | 31817 |
| 042a9fc_3 | no_probe | False | False | 22 | 0 | 64168 | 27816 |
| 09b0ee6_1 | no_probe | True | True | 8 | 0 | 13254 | 5847 |
| 09b0ee6_2 | no_probe | False | True | 8 | 0 | 14880 | 9513 |
| 09b0ee6_3 | no_probe | True | True | 8 | 0 | 20645 | 17628 |
| 0a9d82a_1 | no_probe | True | True | 9 | 0 | 35890 | 9925 |
| 0a9d82a_2 | no_probe | False | True | 7 | 0 | 16488 | 29053 |
| 0a9d82a_3 | no_probe | False | False | 8 | 0 | 11881 | 13243 |
| 0d01c76_1 | no_probe | False | True | 30 | 0 | 22010 | 12687 |
| 0d01c76_2 | no_probe | False | True | 13 | 0 | 29997 | 21351 |
| 0d01c76_3 | no_probe | True | True | 14 | 0 | 31449 | 34251 |
| 0de03ea_1 | no_probe | False | False | 8 | 0 | 22323 | 20916 |
| 0de03ea_2 | no_probe | False | False | 12 | 0 | 32312 | 18773 |
| 0de03ea_3 | no_probe | False | False | 12 | 0 | 62851 | 7754 |
| 1150ed6_1 | no_probe | False | False | 11 | 0 | 47786 | 35426 |
| 1150ed6_2 | no_probe | False | False | 6 | 0 | 8251 | 18318 |
| 1150ed6_3 | no_probe | False | True | 8 | 0 | 21033 | 27132 |
| 13547f5_1 | no_probe | False | True | 11 | 0 | 63149 | 5692 |
| 13547f5_2 | no_probe | True | False | 14 | 0 | 26877 | 73306 |
| 13547f5_3 | no_probe | False | True | 30 | 0 | 9501 | 6302 |
| 166f4ff_1 | no_probe | False | False | 8 | 0 | 7569 | 5529 |
| 166f4ff_2 | no_probe | False | False | 9 | 0 | 12673 | 5680 |
| 166f4ff_3 | no_probe | False | False | 12 | 0 | 17905 | 5228 |
| 21abae1_1 | no_probe | False | False | 7 | 0 | 22035 | 18842 |
| 21abae1_2 | no_probe | False | False | 6 | 0 | 8503 | 10414 |
| 21abae1_3 | no_probe | False | False | 6 | 0 | 3952 | 10511 |
| 270f1ff_1 | no_probe | False | False | 12 | 0 | 21673 | 34993 |
| 270f1ff_2 | no_probe | False | False | 30 | 0 | 59626 | 33694 |
| 270f1ff_3 | no_probe | False | False | 10 | 0 | 28036 | 36340 |
| 29a7b7e_1 | no_probe | True | True | 22 | 0 | 59481 | 27400 |
| 29a7b7e_2 | no_probe | False | False | 17 | 0 | 32891 | 19024 |
| 29a7b7e_3 | no_probe | False | False | 16 | 0 | 37075 | 16355 |
| 2c544f9_1 | no_probe | False | False | 17 | 0 | 55697 | 108328 |
| 2c544f9_2 | no_probe | False | False | 12 | 0 | 56433 | 31187 |
| 2c544f9_3 | no_probe | False | False | 12 | 0 | 57204 | 62994 |
| 2d9f728_1 | no_probe | False | False | 15 | 0 | 46469 | 22354 |
| 2d9f728_2 | no_probe | False | False | 30 | 0 | 50513 | 55276 |
| 2d9f728_3 | no_probe | False | False | 20 | 0 | 33311 | 43248 |
| 31dc501_1 | no_probe | False | True | 12 | 0 | 24755 | 24559 |
| 31dc501_2 | no_probe | False | True | 10 | 0 | 15510 | 14910 |
| 31dc501_3 | no_probe | False | True | 12 | 0 | 40936 | 17396 |
| 325d6ec_1 | no_probe | False | True | 9 | 0 | 15898 | 12394 |
| 325d6ec_2 | no_probe | False | False | 10 | 0 | 27893 | 9918 |
| 325d6ec_3 | no_probe | False | False | 7 | 0 | 14813 | 14248 |
| 32616b5_1 | no_probe | False | False | 12 | 0 | 61184 | 29076 |
| 32616b5_2 | no_probe | False | False | 30 | 0 | 36381 | 33822 |
| 32616b5_3 | no_probe | False | False | 11 | 0 | 61148 | 30370 |
| 3aa1a22_1 | no_probe | False | False | 14 | 0 | 32799 | 30156 |
| 3aa1a22_2 | no_probe | False | False | 14 | 0 | 27206 | 28242 |
| 3aa1a22_3 | no_probe | False | False | 13 | 0 | 29515 | 20774 |
| 3b8fb7a_1 | no_probe | False | False | 13 | 0 | 57757 | 33105 |
| 3b8fb7a_2 | no_probe | False | False | 15 | 0 | 45445 | 53306 |
| 3b8fb7a_3 | no_probe | False | True | 21 | 0 | 33829 | 39689 |
| 3d9a636_1 | no_probe | False | False | 17 | 0 | 46689 | 29234 |
| 3d9a636_2 | no_probe | False | True | 12 | 0 | 63160 | 21401 |
| 3d9a636_3 | no_probe | False | False | 10 | 0 | 54007 | 36228 |
| 425a494_1 | no_probe | False | False | 6 | 0 | 6010 | 5562 |
| 425a494_2 | no_probe | False | True | 12 | 0 | 19974 | 27472 |
| 425a494_3 | no_probe | False | False | 6 | 0 | 9202 | 7918 |
| 522e5e5_1 | no_probe | True | True | 7 | 0 | 9749 | 14422 |
| 522e5e5_2 | no_probe | False | True | 8 | 0 | 8168 | 16094 |
| 522e5e5_3 | no_probe | False | False | 8 | 0 | 21213 | 14281 |
| 552869a_1 | no_probe | False | False | 9 | 0 | 17800 | 11634 |
| 552869a_2 | no_probe | False | False | 9 | 0 | 14919 | 6799 |
| 552869a_3 | no_probe | False | False | 8 | 0 | 18252 | 4813 |
| 59fae45_1 | no_probe | False | True | 15 | 0 | 58999 | 8305 |
| 59fae45_2 | no_probe | True | True | 9 | 0 | 38120 | 17881 |
| 59fae45_3 | no_probe | False | True | 11 | 0 | 15238 | 16291 |
| 5a83b05_1 | no_probe | True | True | 13 | 0 | 20912 | 7318 |
| 5a83b05_2 | no_probe | False | True | 14 | 0 | 30268 | 4374 |
| 5a83b05_3 | no_probe | False | True | 26 | 0 | 60057 | 7939 |
| 634f342_1 | no_probe | False | False | 14 | 0 | 62796 | 69902 |
| 634f342_2 | no_probe | False | True | 13 | 0 | 41136 | 25931 |
| 634f342_3 | no_probe | False | False | 9 | 0 | 32219 | 21461 |
| 652485c_1 | no_probe | False | False | 7 | 0 | 20366 | 62218 |
| 652485c_2 | no_probe | False | False | 20 | 0 | 56392 | 59517 |
| 652485c_3 | no_probe | False | False | 13 | 0 | 35815 | 39618 |
| 6b6ca61_1 | no_probe | False | False | 13 | 0 | 63304 | 39037 |
| 6b6ca61_2 | no_probe | False | False | 18 | 0 | 62921 | 69750 |
| 6b6ca61_3 | no_probe | False | False | 10 | 0 | 58975 | 54829 |
| 6f4b9a5_1 | no_probe | False | False | 14 | 0 | 37335 | 21985 |
| 6f4b9a5_2 | no_probe | False | False | 16 | 0 | 53879 | 26468 |
| 6f4b9a5_3 | no_probe | True | False | 11 | 0 | 14438 | 32223 |
| 7847649_1 | no_probe | False | False | 7 | 0 | 15444 | 5176 |
| 7847649_2 | no_probe | False | False | 11 | 0 | 11998 | 15631 |
| 7847649_3 | no_probe | False | False | 30 | 0 | 16719 | 4563 |
| 83a7951_1 | no_probe | False | False | 12 | 0 | 61605 | 32935 |
| 83a7951_2 | no_probe | False | False | 17 | 0 | 36414 | 54882 |
| 83a7951_3 | no_probe | False | False | 20 | 0 | 55626 | 41370 |
| 8749218_1 | no_probe | False | True | 6 | 0 | 11573 | 22794 |
| 8749218_2 | no_probe | False | True | 5 | 0 | 12206 | 27120 |
| 8749218_3 | no_probe | False | True | 19 | 0 | 45472 | 21951 |
| 8ce6779_1 | no_probe | False | False | 10 | 0 | 58042 | 44035 |
| 8ce6779_2 | no_probe | False | False | 23 | 0 | 43466 | 30098 |
| 8ce6779_3 | no_probe | False | False | 14 | 0 | 25424 | 28472 |
| 9016950_1 | no_probe | False | True | 14 | 0 | 58043 | 32313 |
| 9016950_2 | no_probe | False | False | 11 | 0 | 56066 | 40412 |
| 9016950_3 | no_probe | False | False | 16 | 0 | 33919 | 34910 |
| 90adc3f_1 | no_probe | False | False | 9 | 0 | 8052 | 13653 |
| 90adc3f_2 | no_probe | False | False | 11 | 0 | 33041 | 22471 |
| 90adc3f_3 | no_probe | False | False | 10 | 0 | 18910 | 32902 |
| 986aa4e_1 | no_probe | False | False | 16 | 0 | 24770 | 54113 |
| 986aa4e_2 | no_probe | False | False | 23 | 0 | 29913 | 71548 |
| 986aa4e_3 | no_probe | False | False | 11 | 0 | 56291 | 75990 |
| 9dabbc9_1 | no_probe | False | True | 11 | 0 | 22742 | 19519 |
| 9dabbc9_2 | no_probe | False | False | 7 | 0 | 17304 | 21459 |
| 9dabbc9_3 | no_probe | False | False | 23 | 0 | 63904 | 28714 |
| 9ef798c_1 | no_probe | False | True | 22 | 0 | 58619 | 26112 |
| 9ef798c_2 | no_probe | False | False | 5 | 0 | 6655 | 38053 |
| 9ef798c_3 | no_probe | False | False | 30 | 0 | 44178 | 98326 |
| a30375d_1 | no_probe | False | False | 7 | 0 | 8096 | 7725 |
| a30375d_2 | no_probe | True | False | 11 | 0 | 19636 | 21907 |
| a30375d_3 | no_probe | False | False | 9 | 0 | 25429 | 75855 |
| afc4005_1 | no_probe | False | False | 7 | 0 | 5941 | 11920 |
| afc4005_2 | no_probe | False | False | 6 | 0 | 4711 | 9209 |
| afc4005_3 | no_probe | False | False | 9 | 0 | 8828 | 24109 |
| b6d1104_1 | no_probe | False | False | 13 | 0 | 58451 | 5856 |
| b6d1104_2 | no_probe | False | False | 13 | 0 | 54671 | 26032 |
| b6d1104_3 | no_probe | False | False | 15 | 0 | 64621 | 18806 |
| b9c5c9a_1 | no_probe | False | False | 13 | 0 | 63382 | 78109 |
| b9c5c9a_2 | no_probe | False | False | 11 | 0 | 60294 | 76753 |
| b9c5c9a_3 | no_probe | False | False | 19 | 0 | 62540 | 67265 |
| bde252e_1 | no_probe | False | False | 16 | 0 | 57477 | 63809 |
| bde252e_2 | no_probe | False | False | 9 | 0 | 28001 | 33853 |
| bde252e_3 | no_probe | False | False | 18 | 0 | 59697 | 93274 |
| c77c005_1 | no_probe | False | False | 12 | 0 | 17587 | 14051 |
| c77c005_2 | no_probe | False | True | 18 | 0 | 45601 | 12428 |
| c77c005_3 | no_probe | False | True | 17 | 0 | 32428 | 19445 |
| ccf4b82_1 | no_probe | False | False | 10 | 0 | 57839 | 23475 |
| ccf4b82_2 | no_probe | False | False | 23 | 0 | 57014 | 28854 |
| ccf4b82_3 | no_probe | False | True | 13 | 0 | 27443 | 33688 |
| cef9191_1 | no_probe | False | False | 6 | 0 | 8952 | 30538 |
| cef9191_2 | no_probe | False | True | 10 | 0 | 17415 | 10159 |
| cef9191_3 | no_probe | False | True | 10 | 0 | 11731 | 14634 |
| d18139b_1 | no_probe | False | False | 12 | 0 | 62931 | 43586 |
| d18139b_2 | no_probe | False | False | 9 | 0 | 12340 | 24234 |
| d18139b_3 | no_probe | False | False | 16 | 0 | 39930 | 16118 |
| d194965_1 | no_probe | False | False | 12 | 0 | 61214 | 47486 |
| d194965_2 | no_probe | False | False | 14 | 0 | 62983 | 50222 |
| d194965_3 | no_probe | False | False | 18 | 0 | 37937 | 41996 |
| d6ac34d_1 | no_probe | False | False | 8 | 0 | 17703 | 12303 |
| d6ac34d_2 | no_probe | False | False | 8 | 0 | 28682 | 11910 |
| d6ac34d_3 | no_probe | False | False | 5 | 0 | 6275 | 13326 |
| dac78d9_1 | no_probe | False | False | 20 | 0 | 47775 | 13228 |
| dac78d9_2 | no_probe | False | False | 6 | 0 | 18319 | 6809 |
| dac78d9_3 | no_probe | False | False | 7 | 0 | 17487 | 8042 |
| f323bae_1 | no_probe | False | True | 17 | 0 | 60105 | 38212 |
| f323bae_2 | no_probe | False | False | 10 | 0 | 9827 | 23708 |
| f323bae_3 | no_probe | False | True | 30 | 0 | 12567 | 31488 |
| f3f60f0_1 | no_probe | False | True | 11 | 0 | 15171 | 16576 |
| f3f60f0_2 | no_probe | False | True | 14 | 0 | 14707 | 12391 |
| f3f60f0_3 | no_probe | False | True | 8 | 0 | 15659 | 7534 |
| f861c32_1 | no_probe | False | False | 13 | 0 | 62371 | 61497 |
| f861c32_2 | no_probe | False | False | 16 | 0 | 27021 | 34019 |
| f861c32_3 | no_probe | False | False | 8 | 0 | 18944 | 19731 |
| fd1f8fa_1 | no_probe | False | False | 12 | 0 | 56203 | 42707 |
| fd1f8fa_2 | no_probe | False | False | 20 | 0 | 38587 | 25197 |
| fd1f8fa_3 | no_probe | False | False | 11 | 0 | 25217 | 50415 |
| ff58e36_1 | no_probe | False | True | 20 | 0 | 61562 | 20354 |
| ff58e36_2 | no_probe | False | True | 13 | 0 | 31392 | 32719 |
| ff58e36_3 | no_probe | False | True | 16 | 0 | 61120 | 24444 |
| ffe6d5e_1 | no_probe | False | False | 7 | 0 | 14861 | 11978 |
| ffe6d5e_2 | no_probe | False | False | 10 | 0 | 56469 | 17999 |
| ffe6d5e_3 | no_probe | False | False | 8 | 0 | 27231 | 7383 |
