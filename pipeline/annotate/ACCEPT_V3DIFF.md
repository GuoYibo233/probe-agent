# ACCEPT_V3DIFF -- consistency acceptance of the annotate stage against the old v3 data

Basis: run the new code (rules.py + build.py's jsonl_events/bfcl_events/make_samples)
on v3's original inputs (full_v1 + full_v2_topup, no model filtering, no
splitting), and compare against the four piles of `envs/bert_data/v3/<env>`
merged together, keyed on (event, sent_idx); compare the nine fields
text/label/w/depth/n_sents/traj/unit/model/step, new fields are not compared.

One basis patch: the collection directory collected after v3's database was
built (2026-07-30 00:38) (bfcl_gptoss, landed 03:48) is not in the old data at
all, so the whole batch is stripped out before comparing, and the stripped
list is listed per environment in the table below. The criterion is not a
hardcoded directory name; it is taken from the old data's own set of
collection directories.


## bfcl -- PASS

| item | value |
|---|---|
| new-code event count (drift dirs included) | 3325 |
| new-code sample count (drift dirs stripped) | 36343 |
| stripped drift collection dirs | {'bfcl_gptoss': 32163} |
| v3 old sample count (four piles merged) | 36343 |
| samples compared line by line | 36343 |
| primary keys only on the new side | 0 |
| primary keys only on the old side | 0 |
| duplicate primary keys on the new side (beyond the first) | 0 |
| duplicate primary keys on the old side (beyond the first) | 0 |
| same primary key, different field count | 0 |

Per-field mismatch counts:

| field | text | label | w | depth | n_sents | traj | unit | model | step |
|---|---|---|---|---|---|---|---|---|---|
| mismatches | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## appworld -- PASS

| item | value |
|---|---|
| new-code event count (drift dirs included) | 5552 |
| new-code sample count (drift dirs stripped) | 111767 |
| stripped drift collection dirs | none |
| v3 old sample count (four piles merged) | 111767 |
| samples compared line by line | 111767 |
| primary keys only on the new side | 0 |
| primary keys only on the old side | 0 |
| duplicate primary keys on the new side (beyond the first) | 0 |
| duplicate primary keys on the old side (beyond the first) | 0 |
| same primary key, different field count | 0 |

Per-field mismatch counts:

| field | text | label | w | depth | n_sents | traj | unit | model | step |
|---|---|---|---|---|---|---|---|---|---|
| mismatches | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |


## Overall verdict: PASS (all zero)
