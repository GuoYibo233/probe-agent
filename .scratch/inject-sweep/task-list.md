# The 20 test tasks of the inject sweep

Drawn on 2026-09-29 by `random.Random(42).sample(ids, 20)` over the 168 lines
of `external/appworld/data/datasets/test_normal.txt` (sha1
82d8dd1c32e4ac78cd3e2d52d02421ca35b9b20d), then sorted. Python 3 stdlib
`random`, so the draw is reproducible from the seed and the file.

```
0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3, 3aa1a22_2,
425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2, 83a7951_2, 9dabbc9_2,
a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1, f3f60f0_3, ff58e36_3
```

For the setting files (the `tasks:` list of the baseline's sample section and
of every inject section), in YAML:

```yaml
tasks: [0a9d82a_1, 2d9f728_2, 2d9f728_3, 325d6ec_1, 325d6ec_2, 325d6ec_3,
        3aa1a22_2, 425a494_1, 425a494_3, 6b6ca61_2, 6f4b9a5_3, 7847649_2,
        83a7951_2, 9dabbc9_2, a30375d_3, d6ac34d_2, dac78d9_2, f323bae_1,
        f3f60f0_3, ff58e36_3]
```

Note for the owner: AppWorld ids are `<scenario>_<variant>`; variants of one
scenario share the same apps and data. The draw over task instances gave 15
scenarios for 20 tasks (325d6ec has three variants, 2d9f728 and 425a494 two
each). A draw over scenarios first would spread the 20 tasks over 20
scenarios. The instance draw stands unless the owner asks for the other.
