# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] appworld — `apis.spotify.like_song.access_token`
- value: `token`  区间 [1315,1320)
```
...(access_token=token)⏎liked_albums = apis.spotify.show_liked_albums(access_token=【token】)⏎print(f"Album library: {album_library}")⏎print(f"Liked albums: {liked_albums}"...
```
### [2] appworld — `apis.todoist.assign_or_unassign_task.access_token`
- value: `token`  区间 [619,624)
```
...dex=1)) -> []⏎⏎print(apis.todoist.show_task_comments(task_id=2886, access_token=【token】, page_limit=20)) -> [⏎ {⏎  "task_id": 2886,⏎  "content": "Hello Kathryn and Den...
```
### [3] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1148,1155)
```
...how_api_doc(app_name="spotify", api_name="create_playlist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "create_playlist",⏎ "path": "/playlists",⏎ "method": "POST",⏎ "d...
```
### [4] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `move_file`  区间 [5344,5353)
```
...mg_db11da2.jpeg: 2022-04-20⏎- img_ee070f4.jpeg: 2022-04-20⏎⏎I need to check the 【move_file】 API documentation to understand how to relocate these files....
```
### [5] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1162,1169)
```
...how_api_doc(app_name="spotify", api_name="create_playlist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "create_playlist",⏎ "path": "/playlists",⏎ "method": "POST",⏎ "d...
```
### [6] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_playlist`  区间 [2251,2264)
```
...e more APIs by looking at the full list again, or perhaps I need to look at the 【show_playlist】 API to see if there's more information.⏎⏎Actually, looking at the task again - ...
```
### [7] appworld — `apis.venmo.show_transaction.access_token`
- value: `token`  区间 [720,725)
```
...ess_token",⏎   "type": "string",⏎   "required": true,⏎   "description": "Access 【token】 obtained  ...[cut]... ure": {⏎   "message": "string"⏎  }⏎ }⏎}⏎⏎print(apis.api_d...
```
### [8] appworld — `apis.phone.search_contacts.page_index`
- value: `page`  区间 [1356,1360)
```
...ds, then determine what needs to be added or removed.⏎⏎From the phone contacts (【page】s 0 and 1):⏎1. Adam Blackburn - ad.blackburn@gmail.com⏎2. Alexander Riddle - ale...
```
### [9] appworld — `apis.venmo.show_transaction.access_token`
- value: `token`  区间 [1363,1368)
```
...ikELGWqWRm9YAe52AmdnqAxNnVFbjVc"⏎print(apis.venmo.show_transaction(access_token=【token】, transaction_id=1538)) -> {⏎ "transaction_id": 1538,⏎ "amount": 24.0,⏎ "descrip...
```
### [10] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [848,855)
```
...  "description" ...[cut]... bums in the user's album library."⏎ },⏎ ⏎print(apis.【spotify】.show_account(access_token=token)) -> {⏎ "first_name": "Patricia",⏎ "last_name":...
```
### [11] appworld — `apis.venmo.show_transactions.direction`
- value: `sent`  区间 [3146,3150)
```
...sent payment requests. Maybe I need to look at the transactions with direction='【sent】' and see if they have similar fields.⏎⏎Actually, let me re-read the task: "Send...
```
### [12] appworld — `apis.todoist.show_tasks.access_token`
- value: `todoist_token["access_token"]`  区间 [3368,3397)
```
...tasks_dict[task_id]⏎    result = apis.todoist.create_task(⏎        access_token=【todoist_token["access_token"]】,⏎        project_id=280,⏎        title=task['title'],⏎        description=task....
```
### [13] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1163,1170)
```
...how_api_doc(app_name="spotify", api_name="create_playlist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "create_playlist",⏎ "path": "/playlists",⏎ "method": "POST",⏎ "d...
```
### [14] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1068,1075)
```
...⏎   183⏎  ]⏎ }, ...[cut]...    239,⏎   262,⏎   263,⏎   317⏎  ]⏎ }⏎]⏎⏎print(apis.【spotify】.search_playlists(query="my", access_token=token)) -> [⏎ {⏎  "playlist_id": 1,⏎ ...
```
### [15] appworld — `apis.phone.search_contacts.page_index`
- value: `page`  区间 [1356,1360)
```
...ds, then determine what needs to be added or removed.⏎⏎From the phone contacts (【page】s 0 and 1):⏎1. Adam Blackburn - ad.blackburn@gmail.com⏎2. Alexander Riddle - ale...
```
### [16] appworld — `apis.venmo.show_transactions.access_token`
- value: `token`  区间 [1311,1316)
```
...cSQ8RZVwb4UMGdhU-xNOmPqVqqSiB4"⏎print(apis.venmo.show_transactions(access_token=【token】, min_created_at="2023-05-01", max_created_at="2023-05-31", page_limit=20, page_...
```
### [17] appworld — `apis.venmo.search_users.email`
- value: `nan_ritt@gmail.com`  区间 [2500,2518)
```
...ail address on Venmo.⏎⏎From the phone contacts, I found:⏎- Nancy Ritter, email: 【nan_ritt@gmail.com】, phone: 2307354647, relationship: roommate⏎⏎There are 3 roommates total:⏎1. Kat...
```
### [18] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_song`  区间 [2124,2133)
```
...e genre information for each song in each playlist. Let me first check what the 【show_song】 API returns to see if it includes genre information.⏎⏎I have 5 playlists:⏎- Pla...
```
### [19] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1299,1306)
```
....show_api_doc(app_name="spotify", api_name="show_playlist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "show_album",⏎ "path": "/albums/{album_id}",⏎ "method": "GET",⏎ ...
```
### [20] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `phone`  区间 [762,767)
```
...up invitations in phone text messages⏎2. Check if the sender's number is in the 【phone】 contact book⏎3. ...
```
### [21] appworld — `apis.venmo.create_transaction_comment.transaction_id`
- value: `8319`  区间 [537,541)
```
...5-24", max_created_at="2023-06-02", page_limit=20)) -> [⏎ {⏎  "transaction_id": 【8319】,⏎  "amount": 30.0,⏎  "description": "\ud83c\udfb3Bowling Squad",⏎  "created_at"...
```
### [22] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [831,838)
```
...cs.show_api_doc(app_name="spotify", api_name="show_artist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "show_artist",⏎ "path": "/artists/{artist_id}",⏎ "method": "GET"...
```
### [23] appworld — `apis.venmo.show_transactions.page_index`
- value: `page`  区间 [751,755)
```
..._token=token, min_created_at="2023-02-01", direction="received", page_limit=20, 【page】_index=0)⏎print(f"Page 0: {len(received_2023)} transactions")⏎print(received_202...
```
### [24] appworld — `apis.venmo.show_transactions.access_token`
- value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ2ZW5tbythc2hsZWVfbWFydGluZXpAZ21haWwuY29tIiwiZXhwIjoxNjg0NDEyMDk4fQ.vOfvj4EsZ-A03xl5X46110t_BIpk_VvFOxteJOKKrQU`  区间 [1702,1861)
```
...@gmail.com"⏎  }⏎ },⏎ {⏎  "tran⏎print(apis.venmo.show_transactions(access_token="【eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ2ZW5tbythc2hsZWVfbWFydGluZXpAZ21haWwuY29tIiwiZXhwIjoxNjg0NDEyMDk4fQ.vOfvj4EsZ-A03xl5X46110t_BIpk_VvFOxteJOKKrQU】", user_email="spencer.powell@gmail.com", private=False, page_limit=20)) -> [⏎ {...
```
### [25] appworld — `apis.phone.update_alarm.alarm_id`
- value: `121`  区间 [2388,2391)
```
...0 to 08:30. Now I need to disable the rest of the alarms. Let me disable alarms 【121】, 124, 123, and 125.⏎⏎...
```
### [26] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `deny_payment_request`  区间 [2356,2376)
```
...s.⏎⏎Looking at the API list, I don't see explicit "approve_payment_request" or "【deny_payment_request】" APIs. However, the payment request has fields like `approved_at` and `denied_a...
```
### [27] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1183,1190)
```
....show_api_doc(app_name="spotify", api_name="show_playlist")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "show_playlist",⏎ "path": "/playlists/{playlist_id}",⏎ "method":...
```
### [28] appworld — `apis.phone.login.password`
- value: `4_%505T`  区间 [1040,1047)
```
...mail",⏎  "password": "u%TW7ah"⏎ },⏎ {⏎  "account_name": "phone",⏎  "password": "【4_%505T】"⏎ },⏎ {⏎  "account_name": "simple_note",⏎  "password": "Q=srh$w"⏎ },⏎ {⏎  "acco...
```
### [29] appworld — `apis.venmo.show_transactions.max_created_at`
- value: `2023-05-31`  区间 [1199,1209)
```
...w_transactions(access_token=token, min_created_at="2023-05-01", max_created_at="【2023-05-31】", page_limit=20, page_index=1)) -> [⏎ {⏎  "transaction_id": 7294,⏎  "amount": 1...
```
### [30] appworld — `apis.simple_note.show_note.access_token`
- value: `token`  区间 [1270,1275)
```
...)["access_token"]⏎print(token)⏎print(apis.simple_note.search_notes(access_token=【token】)) -> eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaW1wbGVfbm90ZSttYV9zbWl0a...
```
### [31] appworld — `apis.venmo.create_transaction.receiver_email`
- value: `brandon-webe@gmail.com`  区间 [981,1003)
```
...l,⏎  "comment_count": 0,⏎  "sender": {⏎   "name": "Brandon Weber",⏎   "email": "【brandon-webe@gmail.com】"⏎  }, ...[cut]... "email": "pa_ritter@gmail.com"⏎  }⏎ }⏎]⏎⏎print(apis.api_docs....
```
### [32] appworld — `apis.venmo.create_transaction.amount`
- value: `29.75`  区间 [1088,1093)
```
...ion(access_token=venmo_token, receiver_email="lindseysimpson@gmail.com", amount=【29.75】, description="For electricity bill.")) -> {"message": "Sent money.", "transacti...
```
### [33] appworld — `apis.venmo.show_transactions.page_limit`
- value: `20`  区间 [2579,2581)
```
...Everyone venmoed the manager except the supervisor. The supervisor's share was $【20】.⏎⏎...
```
### [34] appworld — `apis.venmo.login.password`
- value: `7=Z{ZMj`  区间 [954,961)
```
...e": "gmail",⏎  "password": "f0IV=DW"⏎ },⏎ ...[cut]... : "venmo",⏎  "password": "【7=Z{ZMj】"⏎ }⏎]⏎⏎print(apis.api_docs.show_api_descriptions(app_name="venmo")) -> [⏎ {⏎  "...
```
### [35] appworld — `apis.venmo.search_users.query`
- value: `Jeremy`  区间 [2042,2048)
```
...⏎- Katherine Smith: ka_ball@gmail.com (I owe $171)⏎- Jeremy: need to search for 【Jeremy】⏎⏎...
```
### [36] appworld — `apis.venmo.create_transaction.access_token`
- value: `venmo_token`  区间 [2694,2705)
```
...or Tracy Weber specifically⏎tracy_result = apis.venmo.search_users(access_token=【venmo_token】, query="tra_weber@gmail.com")⏎print(f"Searching for Tracy Weber (tra_weber@gmai...
```
### [37] appworld — `apis.venmo.login.password`
- value: `b8E]-&R`  区间 [1579,1586)
```
...32 each⏎venmo_token = apis.venmo.login(username="jepowell@gmail.com", password="【b8E]-&R】")["access_token"]⏎print(venmo_token) -> eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...
```
### [38] appworld — `apis.simple_note.login.username`
- value: `as_moore@gmail.com`  区间 [1075,1093)
```
...nt_passwords()) -> {⏎ "first_name": "Ashley",⏎ "last_name": "Moore",⏎ "email": "【as_moore@gmail.com】",⏎ "phone_number": "7336094411",⏎ "birthday": "1959-09-03",⏎ "sex": "female"⏎}⏎...
```
### [39] appworld — `apis.venmo.show_transaction.access_token`
- value: `token`  区间 [720,725)
```
...ess_token",⏎   "type": "string",⏎   "required": true,⏎   "description": "Access 【token】 obtained  ...[cut]... ure": {⏎   "message": "string"⏎  }⏎ }⏎}⏎⏎print(apis.api_d...
```
### [40] appworld — `apis.file_system.show_directory.access_token`
- value: `token`  区间 [1690,1695)
```
...efix based on creation date⏎4. Move files not from this year (2024 based on the 【token】 expiry) to ~/archive/⏎⏎...
```
### [41] appworld — `apis.splitwise.record_expense.access_token`
- value: `splitwise_token`  区间 [1717,1732)
```
...litwise_token, query="Spencer"))⏎print(apis.splitwise.search_users(access_token=【splitwise_token】, query="Jeffrey")) -> [⏎ {⏎  "name": "Ashlee Martinez",⏎  "email": "ashlee_mart...
```
### [42] appworld — `apis.venmo.add_payment_card.card_name`
- value: `Wells Fargo`  区间 [1834,1845)
```
... use it to send the $250 to Catherine.⏎⏎Wells Fargo card details:⏎- card_name: "【Wells Fargo】"⏎- owner_name: "Brandon Weber"⏎- card_number: 2597882524365103⏎- expiry_year: 2...
```
### [43] appworld — `apis.spotify.search_songs.access_token`
- value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcG90aWZ5K2NlLW1hbGRvbmFkb0BnbWFpbC5jb20iLCJleHAiOjE2ODQ0MTI3NDF9.S3JR7eWf9xlTjhew1-KGZU7Adf-GXlvQDSdOTpj6_p8`  区间 [1587,1744)
```
...ps://spotify.com/songs/153"⏎ }⏎]⏎⏎print(apis.spotify.search_songs(access_token="【eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcG90aWZ5K2NlLW1hbGRvbmFkb0BnbWFpbC5jb20iLCJleHAiOjE2ODQ0MTI3NDF9.S3JR7eWf9xlTjhew1-KGZU7Adf-GXlvQDSdOTpj6_p8】", query="Astral Serenity Orion Steele")) -> [⏎ {⏎  "song_id": 121,⏎  "title": "...
```
### [44] appworld — `apis.venmo.create_transaction.access_token`
- value: `venmo_token`  区间 [2469,2480)
```
...nce(access_token=venmo_token))⏎print(apis.venmo.show_payment_cards(access_token=【venmo_token】)) -> {"venmo_balance": 0.0}⏎[⏎ {⏎  "payment_card_id": 385,⏎  "card_name": "Mast...
```
### [45] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [963,970)
```
...nt(apis.spotify.show_song_privates(song_id=197, access_token=token))⏎print(apis.【spotify】.show_song_privates(song_id=192, access_token=token)) -> {"liked": false, "revie...
```
### [46] appworld — `apis.venmo.show_transactions.page_limit`
- value: `20`  区间 [2125,2127)
```
...lectricity transactions:⏎1. Transaction 8217: $32.00 - "Bill for Electricity" - 【20】23-05-01⏎...
```
### [47] appworld — `apis.venmo.show_transactions.page_limit`
- value: `20`  区间 [2435,2437)
```
... PUBLIC transactions where someone sent money TO Jamie Solomon (the manager) on 【20】23-05-17 (yesterday). ...
```
### [48] appworld — `apis.phone.search_contacts.access_token`
- value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwaG9uZSsyMjU0MjEzNzM0IiwiZXhwIjoxNjg0NDEyNzQxfQ.QeM73y_jEuP2hURwQ2HUU9G4Fs5iYPjtn7T9x4y2dcQ`  区间 [384,523)
```
...te "Dinner", on venmo.⏎[HISTORY]⏎print(apis.phone.search_contacts(access_token="【eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwaG9uZSsyMjU0MjEzNzM0IiwiZXhwIjoxNjg0NDEyNzQxfQ.QeM73y_jEuP2hURwQ2HUU9G4Fs5iYPjtn7T9x4y2dcQ】", name="nancy")) -> [⏎ {⏎  "contact_id": 264,⏎  "first_name": "Adam",⏎  "last_n...
```
### [49] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [854,859)
```
...seharr@gmail.com"⏎  }⏎ }⏎]⏎⏎print(apis.api_docs.show_api_descriptions(app_name="【venmo】")) -> [⏎ {⏎  "name": "show_account",⏎  "description": "Show your account inform...
```
### [50] appworld — `apis.venmo.add_to_venmo_balance.payment_card_id`
- value: `66`  区间 [1752,1754)
```
... to have enough.⏎⏎I have two payment cards available:⏎- Chase (payment_card_id: 【66】)⏎- American Express (payment_card_id: 70)⏎⏎Let me first add $40 to the Venmo ba...
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] appworld — `apis.phone.search_contacts.contact_id`
- value: `204`
- text 末 120 字符:
```
14T08:39:56"
 }
]

[THINKING]
The search_users API seems to return a fixed list of users regardless of the search term. 
```
### [NG2] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_playlist`
- text 末 120 字符:
```

 },
 
[THINKING]
I need to find a way to add songs to a playlist. Let me look at the API documentation more carefully. 
```
### [NG3] appworld — `apis.venmo.create_transaction.receiver_email`
- value: `thomas.solomon@gmail.com`
- text 末 120 字符:
```
Jack Maldonado - Smoothie Time ✓ (this month)
3. 6142 - 2023-05-16 - $14.0 - Thomas Solomon - Plant Baby ✓ (this month)

```
### [NG4] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `search_artists`
- text 末 120 字符:
```
le it
3. Play it

I need to find APIs related to:
- Queue management
- Getting recommended songs
- Shuffling
- Playing


```
### [NG5] appworld — `apis.spotify.add_song_to_playlist.playlist_id`
- value: `654`
- text 末 120 字符:
```
. "Torn Apart" by Evelyn Rose - song_id: 272
5. "Lost in the Wilderness of Love" by Lily Moon, Zoey James - song_id: 68

```
### [NG6] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `simplenote`
- text 末 120 字符:
```
cket list
4. Count the activities that are left to do

Let me start by exploring the SimpleNote app's API documentation.
```
### [NG7] appworld — `apis.spotify.show_artist.access_token`
- value: `token`
- text 末 120 字符:
```
x Rivers - R&B
3. Jasper Skye - EDM
4. Marigold Muse - R&B
5. Ava Morgan - EDM (user has liked a song from this artist)

```
### [NG8] appworld — `apis.venmo.create_transaction.receiver_email`
- value: `as_moore@gmail.com`
- text 末 120 字符:
```
, or "denied". The payment requests I received have `payment_request_id` but I need to figure out how to approve them.


```
### [NG9] appworld — `apis.phone.search_text_messages.access_token`
- value: `phone_token`
- text 末 120 字符:
```
 roommates

I need to figure out:
1. How many roommates there are (including Troy)
2. Nancy's email to send payment to


```
### [NG10] appworld — `apis.spotify.unlike_song.access_token`
- value: `token`
- text 末 120 字符:
```
tart the player. I've found the liked songs:
- song_id: 19
- song_id: 103
- song_id: 109
- song_id: 133
- song_id: 135


```
