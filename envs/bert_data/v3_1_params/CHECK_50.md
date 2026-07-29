# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `like_transaction`  区间 [11349,11365)
```
...w the exact parameter names. Let's see the doc.⏎⏎We need to request the doc for 【like_transaction】. Already did. The environment will output. Then request doc for create_transact...
```
### [2] appworld — `apis.venmo.create_transaction_comment.comment`
- value: `Thank you so much!`  区间 [1334,1352)
```
...mo.create_transaction_comment(access_token=token, transaction_id=8319, comment="【Thank you so much!】")) -> {"message": "Transaction comment created.", "comment_id": 2428}⏎⏎[THINKIN...
```
### [3] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `search_songs`  区间 [10087,10099)
```
..._library, show_liked_songs, show_artist, show_artist_following, search_artists, 【search_songs】, etc. That will give us more info.⏎⏎But before that, we need to get supervisor ...
```
### [4] appworld — `apis.spotify.show_song_library.access_token`
- value: `token`  区间 [2488,2493)
```
...et their release dates, and count how many were released before 2024. Wait, the 【token】 expiration is 1684412098 -> May 18, 2023. So maybe the current year is 2023? Or...
```
### [5] appworld — `apis.venmo.show_transactions.page_limit`
- value: `20`  区间 [1303,1305)
```
...er at Whimsical Bites",⏎  "created_at": "2023-05-17T12:00:57",⏎  "updated_at": "【20】23-05-17T12:00:57",⏎  "private": false,⏎  "like_count": 0,⏎  "payment_card_digit...
```
### [6] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_artist_following`  区间 [3568,3589)
```
...hat's the only one with "following". So maybe the action to follow is done via "【show_artist_following】"? ...
```
### [7] appworld — `apis.venmo.show_transactions.max_created_at`
- value: `2023-05-18`  区间 [1627,1637)
```
...6:20",⏎  "friends_since": null⏎ }⏎]⏎⏎[THINKING]⏎The transactions I found today (【2023-05-18】) don't involve any of the roommates (Anthony Harrison, Anita Burch, Nicholas We...
```
### [8] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `file_system`  区间 [3576,3587)
```
... strings likely include the file name. For each file path, we need to call apis.【file_system】.show_file(file_path=..., access_token=token) to get details including created_a...
```
### [9] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [2909,2914)
```
...e iso. Then compute yesterday and today strings in YYYY-MM-DD format. Then call 【venmo】.show_transactions with min_created_at=yesterday_str, max_created_at=today_str (...
```
### [10] appworld — `apis.venmo.show_transactions.user_email`
- value: `jamie-solomon@gmail.com`  区间 [2052,2075)
```
..."Anita Burch",⏎   "email": "anita.burch@gmail.com"⏎  },⏎  "re ...[cut]... il": "【jamie-solomon@gmail.com】"⏎  }⏎ }⏎]⏎⏎[THINKING]⏎The supervisor said "Everyones' transactions except mine ...
```
### [11] appworld — `apis.simple_note.search_notes.query`
- value: `query`  区间 [12268,12273)
```
...search query "Dinner" will match title and content? The description says search 【query】 for notes, but not content. It says "Search your notes. This will not show cont...
```
### [12] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1229,1236)
```
....show_api_doc(app_name="spotify", api_name="show_playlist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "show_playlist",⏎ "path": "/playlists/{playlist_id}",⏎ "method":...
```
### [13] appworld — `apis.phone.search_text_messages.access_token`
- value: `token`  区间 [1289,1294)
```
...Q.WIoBUqmPNoG2I3zrIsPlXAQaM4dx4GLylGtdOdR14ow⏎⏎[THINKING]⏎Now I have the access 【token】. ...
```
### [14] appworld — `apis.venmo.show_transactions.max_created_at`
- value: `2023-05-17`  区间 [1824,1834)
```
...ion": "Enchanted Eats",⏎  "created_at": "2023-05-17T17:53:07",⏎  "updated_at": "【2023-05-17】T17:53:07",⏎  "private": false,⏎  "like_count": 0,⏎  "payment_card_digits": null...
```
### [15] appworld — `apis.simple_note.login.password`
- value: `^tqDJrM`  区间 [6863,6870)
```
...0t3P@ss" was from a previous list (maybe outdated). So the correct password is "【^tqDJrM】". So we logged in successfully. However the search results now show notes that ...
```
### [16] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `search_users`  区间 [3457,3469)
```
...ers API takes name or email. Let's see its doc.⏎We need to view the API doc for 【search_users】.⏎We need to see the output.⏎We need to see the output. The system is not respon...
```
### [17] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `login`  区间 [3798,3803)
```
...nt passwords to get Spotify password.⏎3. Login to Spotify: token = apis.spotify.【login】(username=..., password=... )["access_token"]⏎4. Use token to call apis.spotify....
```
### [18] tales — `open.arg`
- value: `cabinet`  区间 [5113,5120)
```
...", "dishwasher". Maybe the game only has those containers. The plain door, shoe 【cabinet】, etc. might not be openable. The door might be opened by "move south" if it's u...
```
### [19] tales — `open.arg`
- value: `door`  区间 [5756,5760)
```
...o.⏎I'll try `open door`.⏎Wait, the system said "Unknown action" for `open patio 【door】`. ...
```
### [20] tales — `read.arg`
- value: `cookbook`  区间 [235,243)
```
...G]⏎The user wants me to play a text-based cooking game. I need to:⏎1. Check the 【cookbook】 for the recipe⏎2. Gather all ingredients⏎3. Follow the exact preparation steps⏎...
```
### [21] tales — `move.arg`
- value: `west`  区间 [3962,3966)
```
...sh can closed, dishwasher closed, plain door closed (south), patio door closed (【west】). The corridor has a shoe cabinet (empty), wood door closed (south). The wood d...
```
### [22] tales — `open.arg`
- value: `west door`  区间 [14790,14799)
```
...ed. Let's try "open west door". Or "open west". Already unknown. So maybe "open 【west door】". Let's try that.⏎⏎Thus we need to find the correct syntax for opening doors. T...
```
### [23] tales — `open.arg`
- value: `shoe cabinet`  区间 [2208,2220)
```
...y where the BBQ is).⏎The wood door leads to... somewhere else.⏎⏎Let's check the 【shoe cabinet】 in the corridor. ...
```
### [24] tales — `open.arg`
- value: `patio door`  区间 [1931,1941)
```
...description: "To the South you see a closed patio door." So we need to open the 【patio door】, then move south. Then we can "cook yellow bell pepper in BBQ". Then we need to...
```
### [25] tales — `open.arg`
- value: `screen-door`  区间 [9818,9829)
```
...r". Already tried. Could try "open screen door". Already tried. Could try "open 【screen-door】". Not tried.⏎⏎Alternatively, maybe the parser expects "open south door". But th...
```
### [26] tales — `open.arg`
- value: `frosted glass door`  区间 [5526,5544)
```
... "open frosted-glass door" maybe the hyphen is causing trouble. Let's try "open 【frosted glass door】". Also "open sliding patio door" gave unknown. ...
```
### [27] tales — `open.arg`
- value: `trash can`  区间 [2177,2186)
```
...a yellow apple, and a cookbook on it."⏎"dining table, that has nothing on it."⏎"【trash can】 that is closed."⏎"dishwasher that is closed."⏎⏎Maybe the BBQ is not in the back...
```
### [28] tales — `open.arg`
- value: `umbrella stand`  区间 [2065,2079)
```
... the corridor.⏎"In one part of the room you see a key holder... shoe cabinet... 【umbrella stand】... hat rack... coat hanger."⏎I opened the shoe cabinet (empty).⏎I tried to open...
```
### [29] tales — `open.arg`
- value: `frosted glass door`  区间 [5040,5058)
```
...lits on spaces and hyphens cause issues. Could be that the parser expects "open 【frosted glass door】". Let's try that.⏎⏎Alternatively, maybe the door is not openable because it's a...
```
### [30] tales — `open.arg`
- value: `screen`  区间 [16947,16953)
```
...ed-glass door. Or "open wood" might open the wood door.⏎⏎Thus, we can try "open 【screen】". That might be recognized. Let's try that.⏎⏎If that works, we can then "move s...
```
### [31] tales — `open.arg`
- value: `door`  区间 [1035,1039)
```
...e in another room. The patio door leads north, and there's also a frosted-glass 【door】 to the west. ...
```
### [32] tales — `open.arg`
- value: `patio door`  区间 [6588,6598)
```
...r hasn't moved east yet. Let's try "move east". That may be blocked because the 【patio door】 is closed. But maybe the game will allow moving through a closed door? Usually ...
```
### [33] tales — `open.arg`
- value: `patio door`  区间 [3577,3587)
```
... So we need to open the patio door. The game supports "open X". So we can "open 【patio door】". ...
```
### [34] tales — `open.arg`
- value: `east door`  区间 [3436,3445)
```
..."open X". So we need to open the door by name. The name is "plain door" for the 【east door】, "wood door" for the west door in corridor, "sliding patio door" for north. So ...
```
### [35] bfcl — `diff.file_name2`
- value: `report_final.txt`  区间 [256,272)
```
...ort_final.txt"]}⏎[THINKING]⏎Great! I found both files:⏎- ./report_draft.txt⏎- ./【report_final.txt】⏎...
```
### [36] bfcl — `book_flight.travel_from`
- value: `RMS`  区间 [831,834)
```
...e user wants to book a flight from RMS to GFD. They've provided:⏎- travel_from: 【RMS】⏎- travel_to: GFD⏎- card_id: card1234⏎- travel_date: 2026-12-15 (from previous c...
```
### [37] bfcl — `register_credit_card.card_number`
- value: `2345-6789-1234-5678`  区间 [123,142)
```
...icated, could we proceed with registering my credit card? We'll use card number 【2345-6789-1234-5678】, set to expire in 08/2025, listed under Maxwell Edison with the CVV 567. After ...
```
### [38] bfcl — `book_flight.travel_to`
- value: `RMS`  区间 [357,360)
```
...he business‑class flight on 2026‑07‑15 from Crescent Hollow (CRH) to Rivermist (【RMS】) is priced at **$560.00**. -> ⏎[set_budget_limit(access_token="access_token_abc...
```
### [39] bfcl — `get_nearest_airport_by_city.location`
- value: `Los Angeles`  区间 [5154,5165)
```
...both.⏎Done. ⏎Let's format it correctly.⏎`[get_nearest_airport_by_city(location="【Los Angeles】"), get_nearest_airport_by_city(location="New York")]`⏎Wait, the prompt says "Ch...
```
### [40] bfcl — `logarithm.value`
- value: `980.0`  区间 [5576,5581)
```
...l follow the explicit instruction.⏎Done. ⏎Proceeds. ⏎[Output] `[logarithm(value=【980.0】, base=20.0, precision=10)]`⏎Done. ⏎...
```
### [41] bfcl — `get_symbol_by_name.name`
- value: `Zeta Corp`  区间 [2619,2628)
```
... calls in a list.⏎⏎Thus we can output something like: [get_symbol_by_name(name="【Zeta Corp】")]. Then after we get the response, we can call remove_stock_from_watchlist(sym...
```
### [42] bfcl — `get_flight_cost.travel_date`
- value: `2026-12-15`  区间 [3033,3043)
```
...ness"), book_flight(access_token="abc123xyz", card_id="card_2108", travel_date="【2026-12-15】", travel_from="JFK", travel_to="LAX", travel_class="business")]`⏎Wait, should I...
```
### [43] bfcl — `mkdir.dir_name`
- value: `Reports`  区间 [1572,1579)
```
...lative paths. I'll just call `mv` with `source="summary.doc"` and `destination="【Reports】"`.⏎4. ...
```
### [44] bfcl — `book_flight.travel_to`
- value: `HKG`  区间 [4367,4370)
```
...yz", card_id="primary", travel_date="2026-12-15", travel_from="CRH", travel_to="【HKG】", travel_class="economy")].⏎⏎Check if any other functions needed: maybe we need...
```
### [45] bfcl — `get_symbol_by_name.name`
- value: `Quasar Ltd.`  区间 [534,545)
```
...]⏎(start)⏎[THINKING]⏎The user is asking for information about a company called '【Quasar Ltd.】' - specifically they want to know the current price and trading details. To get...
```
### [46] bfcl — `compute_exchange_rate.target_currency`
- value: `USD`  区间 [1366,1369)
```
...t will give exchanged_value in USD. Then we can call set_budget_limit with that 【USD】 value.⏎⏎But the user also says "Around it to have tenth and hundredth digit. Li...
```
### [47] bfcl — `get_stock_info.symbol`
- value: `ALPH`  区间 [1378,1382)
```
...t the current price, then place the order.⏎⏎Let me first get the stock info for 【ALPH】 to get the current price....
```
### [48] bfcl — `place_order.amount`
- value: `100`  区间 [145,148)
```
...among those stocks, Alphabet with symbol 'ALPH'. Supposing I choose to purchase 【100】 units at the prevailing rate, kindly execute this transaction for me.⏎[HISTORY]...
```
### [49] bfcl — `ticket_login.username`
- value: `mthompson`  区间 [1135,1144)
```
...etailing the reservation specifics 'Request to cancel.'. My ticket username is `【mthompson】` and password is `securePass123`"⏎...
```
### [50] bfcl — `cd.folder`
- value: `ResearchDocs`  区间 [1283,1295)
```
... calls in your response."⏎Ready. ⏎Proceed. ⏎Output matches format.⏎`[cd(folder="【ResearchDocs】"), find(name="report.csv")]`⏎...
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `like_song`
- text 末 120 字符:
```
ngs` has an `artist_id` parameter to filter songs by artist. I need to:
1. Get all followed artists (already have 6)
2. 
```
### [NG2] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_playlist`
- text 末 120 字符:
```
e task is to give a 5-star rating to all songs in the supervisor's Spotify playlists which they have liked. I need to:


```
### [NG3] appworld — `apis.spotify.search_songs.pos0`
- value: `# descending rating (higher rating = more recommended)
        page_index=page_index`
- text 末 120 字符:
```
or each song_id, call add_song_to_playlist with playlist_id, song_id, access_token. Possibly we need to handle errors.


```
### [NG4] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_song_privates`
- text 末 120 字符:
```
unt: 178
- Song 39: "A Pathway to Nowhere" - play_count: 594
- Song 40: "Burning Like a Distant Star" - play_count: 120

```
### [NG5] tales — `open.arg`
- value: `trash can`
- text 末 120 字符:
```
ed: banana.
- I am in the kitchen.
- I have checked the fridge (no banana), dishwasher (empty), cutlery drawer (empty).

```
### [NG6] tales — `open.arg`
- value: `door east`
- text 末 120 字符:
```
 "open east"? unknown. Then "open wooddoor"? unknown. Then "open patio door"? unknown. Then "open east door"? unknown.


```
### [NG7] tales — `open.arg`
- value: `screen door`
- text 末 120 字符:
```
, salt. Directions: chop the parsley, prepare meal. So we need to gather parsley, water, salt. We have water in fridge. 
```
### [NG8] bfcl — `get_nearest_airport_by_city.location`
- value: `New York`
- text 末 120 字符:
```
s, booking_history.

We need to get flight cost first, then book flight.

We need to know IATA codes for NYC and Tokyo. 
```
### [NG9] bfcl — `cancel_booking.booking_id`
- value: `booking_123`
- text 末 120 字符:
```
r, usually in these tasks, if the booking was just made, I might need to assume a booking ID or the system provides it. 
```
### [NG10] bfcl — `pressBrakePedal.pedalPosition`
- value: `1.0`
- text 末 120 字符:
```
ear_left, rear_right". We locked doors. Then we got error: "Brake pedal needs to be pressed when starting the engine."


```
