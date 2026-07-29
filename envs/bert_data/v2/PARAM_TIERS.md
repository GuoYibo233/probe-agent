# 参数头三档档位表(由 param_tiers.py 从 router_stats.md 生成)

档位规则:无参=从不带参;选择=逐字命中率≥0.9;自由=<0.9。
命中率是候选集封闭性的代理指标,终裁待抽取头实测。

## tales(共 2039 事件)

| 档位 | 工具数 | 事件数 | 事件占比 |
|---|---|---|---|
| 无参 | 1 | 26 | 1.3% |
| 选择 | 9 | 1663 | 81.6% |
| 自由 | 3 | 350 | 17.2% |

自由档明细:move(命中率0.88,333事件)、cook(命中率0.44,16事件)、<command>".(命中率0.00,1事件)

## appworld(共 2772 事件)

| 档位 | 工具数 | 事件数 | 事件占比 |
|---|---|---|---|
| 无参 | 8 | 523 | 18.9% |
| 选择 | 58 | 2010 | 72.5% |
| 自由 | 13 | 239 | 8.6% |

自由档明细:apis.supervisor.complete_task(命中率0.62,106事件)、apis.venmo.search_users(命中率0.84,30事件)、apis.phone.show_contact_relationships(命中率0.71,22事件)、apis.file_system.create_directory(命中率0.87,17事件)、apis.file_system.show_file(命中率0.79,14事件)、apis.venmo.like_transaction(命中率0.88,13事件)、apis.simple_note.show_note(命中率0.88,12事件)、apis.file_system.create_file(命中率0.62,7事件)、apis.spotify.like_song(命中率0.83,6事件)、apis.spotify.create_playlist(命中率0.80,6事件)、apis.file_system.move_file(命中率0.71,4事件)、apis.venmo.add_payment_card(命中率0.43,1事件)、apis.spotify.show_user_recently_played(命中率0.00,1事件)

## bfcl(共 2265 事件)

| 档位 | 工具数 | 事件数 | 事件占比 |
|---|---|---|---|
| 无参 | 16 | 219 | 9.7% |
| 选择 | 71 | 1699 | 75.0% |
| 自由 | 14 | 347 | 15.3% |

自由档明细:pressBrakePedal(命中率0.72,79事件)、lockDoors(命中率0.77,62事件)、fillFuelTank(命中率0.88,60事件)、ls(命中率0.82,56事件)、estimate_drive_feasibility_by_mileage(命中率0.83,24事件)、contact_customer_support(命中率0.73,22事件)、mean(命中率0.67,15事件)、list_all_airports(命中率0.00,12事件)、fund_account(命中率0.86,7事件)、edit_ticket(命中率0.83,3事件)、mention(命中率0.67,3事件)、setCruiseControl(命中率0.67,2事件)、display_log(命中率0.00,1事件)、func_name1(命中率0.00,1事件)

## 三环境合计(共 7076 事件)

| 档位 | 工具数 | 事件数 | 事件占比 |
|---|---|---|---|
| 无参 | 25 | 768 | 10.9% |
| 选择 | 138 | 5372 | 75.9% |
| 自由 | 30 | 936 | 13.2% |
