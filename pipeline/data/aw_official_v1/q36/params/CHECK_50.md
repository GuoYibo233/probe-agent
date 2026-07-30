# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] appworld — `apis.splitwise.record_expense.group_id`
- value: `274`  区间 [1342,1345)
```
...urton@gmail.com", "angriddle@gmail.com", "ashlee_martinez@gmail.com"], group_id=【274】)) -> {"message": "Expense recorded.", "expense_id": 5041}⏎⏎[THINKING]⏎Now I nee...
```
### [2] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `venmo`  区间 [1252,1257)
```
...vY"⏎ },⏎ {⏎  "account_name": "gmail",⏎  "password": "Fnzta&X"⏎ } ...[cut]... : "【venmo】",⏎  "password": "OzVS[j5"⏎ }⏎]⏎⏎[THINKING]⏎Now I need to:⏎1. Login to Venmo⏎2. ...
```
### [3] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [1403,1408)
```
...pi_doc(app_name="venmo", api_name="delete_payment_request")) -> {⏎ "app_name": "【venmo】",⏎ "api_name": "delete_payment_request",⏎ "path": "/payment_requests/{payment_r...
```
### [4] appworld — `apis.venmo.show_transactions.min_created_at`
- value: `2023-05-18`  区间 [1357,1367)
```
...ion": "Auto Insurance",⏎  "created_at": "2023-05-18T11:24:40",⏎  "updated_at": "【2023-05-18】T11:24:40",⏎  "private": false,⏎  "like_count": 4,⏎  "payment_card_digits": null...
```
### [5] appworld — `apis.spotify.show_song_library.access_token`
- value: `token`  区间 [4707,4712)
```
...ach song ID to get release_date.⏎Count.⏎⏎Wait, `show_song` doesn't take `access_【token】`? ...
```
### [6] appworld — `apis.venmo.show_transactions.page_limit`
- value: `20`  区间 [1265,1267)
```
... States\n65644",⏎  "work_address": "716 White Drive S ...[cut]... created_at": "【20】22-12-25T13:28:45"⏎ }⏎]⏎⏎[THINKING]⏎I have the list of roommates:⏎1. Chris Mccoy...
```
### [7] appworld — `apis.spotify.create_playlist.access_token`
- value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcG90aWZ5K2tpYV9iYWlsZXlAZ21haWwuY29tIiwiZXhwIjoxNjg0NDEyNzQxfQ._KQZDUntXqJGf1w9EyO3DgJHXkGTX_Agj90fIvutxFE`  区间 [849,1004)
```
...in(username="kia_bailey@gmail.com", password="+v3-_9e")) -> {⏎ "access_token": "【eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcG90aWZ5K2tpYV9iYWlsZXlAZ21haWwuY29tIiwiZXhwIjoxNjg0NDEyNzQxfQ._KQZDUntXqJGf1w9EyO3DgJHXkGTX_Agj90fIvutxFE】",⏎ "token_type": "Bearer"⏎}⏎⏎print(apis.api_docs.show_api_descriptions(app_name...
```
### [8] appworld — `apis.venmo.show_received_payment_requests.access_token`
- value: `token`  区间 [838,843)
```
....login(username="joseharr@gmail.com", password="uNK8[nt")["access_token"]⏎print(【token】) -> eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ2ZW5tbytqb3NlaGFyckBnbWFpbC...
```
### [9] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1265,1272)
```
...": "string",⏎   "required": true,⏎   "description": "Access token obtained from 【spotify】 app login.",⏎   "default ...[cut]... ure": {⏎   "message": "string"⏎  }⏎ }⏎}⏎⏎[...
```
### [10] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1107,1114)
```
...docs.show_api_doc(app_name="spotify", api_name="show_song")) -> {⏎ "app_name": "【spotify】",⏎ "api_name": "show_song",⏎ "path": "/songs/{song_id}",⏎ "method": "GET",⏎ "de...
```
### [11] appworld — `apis.venmo.create_transaction.description`
- value: `For Food`  区间 [12042,12050)
```
...ry payment requests with a note 'For Taxi', and a payment to Nancy with a note '【For Food】', on venmo."⏎⏎OK so:⏎- Troy paid $60 for taxi. Shared among 4 people = $15 each...
```
### [12] appworld — `apis.phone.get_current_date_and_time.access_token`
- value: `phone_token`  区间 [1563,1574)
```
...phone_token)⏎son_contact = apis.phone.search_contacts(query="son", access_token=【phone_token】)⏎print(son_contact)⏎venmo_token = apis.venmo.login(username="sab-brown@gmail.co...
```
### [13] appworld — `apis.phone.send_text_message.message`
- value: `message`  区间 [1775,1782)
```
...les from the content and send them as a comma-separated list to Leslie via text 【message】.⏎⏎The movies listed are:⏎1. The Lord of the Rings: The Two Towers⏎2. No Country...
```
### [14] appworld — `apis.spotify.search_songs.page_index`
- value: `1`  区间 [1671,1672)
```
...all songs, or check if there are more pages.⏎⏎Actually, I used min_play_count=99【1】 which should catch all songs with play_count > 990. The result only showed one ...
```
### [15] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `venmo`  区间 [3137,3142)
```
... `update_transaction` doc. Or maybe `create_transaction`? No.⏎Let's look at the 【venmo】 API descriptions again. I only saw up to `show_received_payment_requests`. Let'...
```
### [16] appworld — `apis.supervisor.complete_task.answer`
- value: `144`  区间 [3919,3922)
```
...erify the sum one more time.⏎32 + 25 = 57⏎57 + 31 = 88⏎88 + 27 = 115⏎115 + 29 = 【144】.⏎Correct.⏎I will execute the completion.⏎All good. ⏎Let's produce the response....
```
### [17] appworld — `apis.venmo.deny_payment_request.access_token`
- value: `token["access_token"]`  区间 [5232,5253)
```
...ansaction(receiver_email="lindseysimpson@gmail.com", amount=525.0, access_token=【token["access_token"]】, description="You forgot about the 5% increase!"))⏎```⏎Done. ⏎Wait, let's verif...
```
### [18] appworld — `apis.venmo.show_transactions.page_limit`
- value: `20`  区间 [3387,3389)
```
...token, query="phone", direction="sent", min_created_at="2023-01-01", page_limit=【20】)`⏎...
```
### [19] appworld — `apis.spotify.show_song.song_id`
- value: `song_id`  区间 [1073,1080)
```
...scription": "Get details of a specific song.",⏎ "parameters": [⏎  {⏎   "name": "【song_id】",⏎   "type": "integer",⏎   "required": true,⏎   "description": "The song id to ...
```
### [20] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `search_contacts`  区间 [1822,1837)
```
... search_contacts API might have pagination. Let me also look at the API doc for 【search_contacts】.⏎⏎From the messages, I have these Splitwise invitations:⏎1. Edwin Wilson - 8506...
```
### [21] appworld — `apis.spotify.search_songs.page_limit`
- value: `20`  区间 [379,381)
```
...ts": [⏎   {⏎    "id": 32,⏎    "name": "Lucas Grey"⏎   }⏎  ],⏎  "release_date": "【20】22-05-21T21:55:36",⏎  "genre": "R&B",⏎  "play_count": 905,⏎  "rating": 0.0,⏎  "l...
```
### [22] appworld — `apis.venmo.create_transaction.amount`
- value: `33`  区间 [31620,31622)
```
...h `receiver_email` set to Stephen's email (stmcco@gmail.com) and the amount is $【33】. If this creates a request, great. If it sends money, then I need to find anoth...
```
### [23] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [1197,1202)
```
...pp_name="venmo", api_name="show_received_payment_requests")) -> {⏎ "app_name": "【venmo】",⏎ "api_name": "show_received_payment_requests",⏎ "path": "/received_payment_re...
```
### [24] appworld — `apis.spotify.show_song.song_id`
- value: `sid`  区间 [1536,1539)
```
...ss_token=token, playlist_id=pid, song_id=sid)⏎    print(f"Playlist {pid}, Song {【sid】}: {result}") -> Playlist 8, Song 99: {'message': 'Song removed from playlist.'}...
```
### [25] appworld — `apis.file_system.show_directory.directory_path`
- value: `/home/susan/photographs/vacations/`  区间 [1926,1960)
```
...eoul/img_092123d.jpg"⏎}⏎{⏎ "message": "File moved.",⏎ "destination_file_path": "【/home/susan/photographs/vacations/】Seoul/img_1286641.jp ...[cut]... phs/vacations/Seoul/img_f803be1.jpeg"⏎}⏎⏎[THINK...
```
### [26] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_directory`  区间 [900,914)
```
...g8gYsS1PGhw78OvKLvhvLwBummg",⏎ "token_type": "Bearer"⏎}⏎⏎print(apis.file_system.【show_directory】(path="~/pictures/", access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...
```
### [27] appworld — `apis.splitwise.record_expense.access_token`
- value: `splitwise_token["access_token"]`  区间 [617,648)
```
...8bMc",⏎ "token_type": "Bearer"⏎}⏎⏎print(apis.splitwise.show_groups(access_token=【splitwise_token["access_token"]】)) -> [⏎ {⏎  "group_id": 281,⏎  "name": "Road Trip",⏎  "description": null,⏎  "c...
```
### [28] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [1308,1313)
```
...t": "2023-05-18T04:48:33"⏎ }⏎]⏎⏎print(apis.venmo.show_transactions(access_token=【venmo】_token)) -> [⏎ {⏎  "transaction_id": 1565,⏎  "amount": 8.0,⏎  "description": "\u...
```
### [29] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `spotify`  区间 [1444,1451)
```
...tatus code is 422:⏎{"message":"No APIs with name show_now_playing found for the 【spotify】 app. Check the api and app name again."}⏎[THINKING]⏎The API `show_now_playing` ...
```
### [30] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `update_transaction`  区间 [5528,5546)
```
...o see if there's a way to change a transaction to a request.⏎⏎Let me check the `【update_transaction】` API.⏎⏎Actually, let me just try creating a transaction with the supervisor as ...
```
### [31] appworld — `apis.gmail.show_inbox_threads.access_token`
- value: `gmail_token`  区间 [1174,1185)
```
...{⏎print(apis.gmail.show_archived_threads(query="electricity bill", access_token=【gmail_token】)) -> [⏎ {⏎  "email_thread_id": 1385,⏎  "email_ids": [⏎   431,⏎   432⏎  ],⏎  "dr...
```
### [32] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [812,819)
```
...()]) -> []⏎⏎print([api for api in apis.api_docs.show_api_descriptions(app_name="【spotify】") if "review" in api["name"].lower() or "update" in api["name"].lower()]) -> [⏎...
```
### [33] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `create_transaction`  区间 [13485,13503)
```
...sn't seem to support requests.⏎⏎Let me try one more thing: maybe I can use the `【create_transaction】` API with Ronald as the receiver, and the API will interpret it as a request be...
```
### [34] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `venmo`  区间 [1109,1114)
```
...essage": "string"⏎  }⏎ }⏎}⏎⏎print(apis.api_docs.show_api_descriptions(app_name="【venmo】")) -> [⏎ {⏎  "name": "show_account",⏎  "description": "Show your account inform...
```
### [35] appworld — `apis.venmo.show_transactions.sort_by`
- value: `-created_at`  区间 [1163,1174)
```
...apis.venmo.show_transactions(access_token=access_token, page_limit=20, sort_by="【-created_at】")⏎print(transactions) -> [⏎ {⏎  "transaction_id": 7054,⏎  "amount": 20.0,⏎  "de...
```
### [36] appworld — `apis.spotify.search_songs.access_token`
- value: `spotify_token["access_token"]`  区间 [1329,1358)
```
...pis.spotify.search_songs(query="Stardust Serenade Violet Cascade", access_token=【spotify_token["access_token"]】)) -> [⏎ {⏎  "song_id": 175,⏎  "title": "Stardust Serenade",⏎  "album_id": null,...
```
### [37] appworld — `apis.spotify.update_song_review.rating`
- value: `4`  区间 [2454,2455)
```
...pdates first, then the creates.⏎⏎Songs to update (existing review with rating < 【4】):⏎- Song 1: review_id=291⏎- Song 25: review_id=293⏎...
```
### [38] appworld — `apis.venmo.login.password`
- value: `zp$44pd`  区间 [1206,1213)
```
..."⏎ },⏎ {⏎  "account_name": "splitwise",⏎  ...[cut]... : "venmo",⏎  "password": "【zp$44pd】"⏎ }⏎]⏎⏎[THINKING]⏎Now I need to login to Venmo and then:⏎1. Get all transaction...
```
### [39] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `create_file`  区间 [1650,1661)
```
...]⏎The directory already exists. Now I need to create the file. Let me check the 【create_file】 API....
```
### [40] appworld — `apis.splitwise.record_expense.group_id`
- value: `275`  区间 [3228,3231)
```
...match. Let me reconsider.⏎⏎Actually, looking more carefully:⏎- The Paris group (【275】) has: Jamie, Sabrina, Brian, Aaron⏎- The Zurich trip involves: Timothy, Brian, ...
```
### [41] appworld — `apis.file_system.show_directory.directory_path`
- value: `~/my_downloads/`  区间 [1619,1634)
```
...e": "Directory already exists."}⏎⏎[THINKING]⏎Now I need to:⏎1. For each file in 【~/my_downloads/】, get its creation date⏎2. Add the prefix "YYYY_MM_DD_" to the filename⏎3. Move ...
```
### [42] appworld — `apis.spotify.unfollow_artist.access_token`
- value: `token`  区间 [1198,1203)
```
...3:41:48'}]⏎⏎followed_artists = apis.spotify.show_following_artists(access_token=【token】, page_limit=20)⏎print(followed_artists) -> [⏎ {⏎  "artist_id": 5,⏎  "name": "Av...
```
### [43] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_tasks`  区间 [991,1001)
```
...null,⏎  ...[cut]... invites": [],⏎  "is_shared": false⏎ }⏎]⏎⏎print(apis.todoist.【show_tasks】(access_token=todoist_token["access_token"], project_id=280)) -> {⏎ "project_id"...
```
### [44] appworld — `apis.venmo.show_received_payment_requests.status`
- value: `pending`  区间 [6131,6138)
```
...ayment_requests(access_token=token, status="pending", page_limit=20)⏎for req in 【pending】:⏎    if req["sender"]["email"] in roommate_emails:⏎        print(apis.venmo.app...
```
### [45] appworld — `apis.venmo.add_friend.user_email`
- value: `brandon-webe@gmail.com`  区间 [1777,1799)
```
...e analyze the situation:⏎⏎1. Coworkers from phone contacts:⏎   - Brandon Weber (【brandon-webe@gmail.com】)⏎   - Claudia Miller (clmiller@gmail.com)⏎   - James Solomon (ja-solomon@gmail....
```
### [46] appworld — `apis.venmo.show_transactions.page_index`
- value: `1`  区间 [1004,1005)
```
...ass",⏎  "created_at": "2023-04-04T20:02:31",⏎  "updated_at": "2023-04-04T20:02:3【1】",⏎  "private": true,⏎  "like_count": 0,⏎  "payment_card_digits": null,⏎  "comme...
```
### [47] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `venmo`  区间 [1241,1246)
```
...ow_api_doc(app_name="venmo", api_name="create_transaction")) -> {⏎ "app_name": "【venmo】",⏎ "api_name": "create_transaction",⏎ "path": "/transactions",⏎ "method": "POST...
```
### [48] appworld — `apis.spotify.add_song_to_playlist.song_id`
- value: `137`  区间 [2033,2036)
```
...marize:⏎⏎Songs to ADD:⏎1. "A Symphony of Fading Hopes" by Zoey James - song_id: 【137】⏎2. "Secrets of the Heart" by Carter Knight - song_id: 265⏎3. "The Sweet Pain of...
```
### [49] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_transaction`  区间 [1102,1118)
```
...3-05-15T0 ...[cut]... ends_since": "2023-03-17T19:07:33"⏎ }⏎]⏎⏎print(apis.venmo.【show_transaction】s(access_token=token["access_token"], query="Cory", page_limit=20)) -> [⏎ {⏎  "t...
```
### [50] appworld — `apis.venmo.show_transactions.page_index`
- value: `4`  区间 [1756,1757)
```
... "cod.smith@gmail.com"⏎  },⏎  "rece ...[cut]... "updated_at": "2023-05-16T17:36:【4】3",⏎  "⏎[THINKING]⏎I need to find transactions where the coworkers from the note...
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `delete_payment_request`
- text 末 120 字符:
```
sor says "I made venmo payment requests to my roommates yesterday evening". 

Let me think about who the roommates are. 
```
### [NG2] appworld — `apis.supervisor.complete_task.answer`
- value: `The total cost of cable bills for this year is $310.`
- text 末 120 字符:
```
otal}") -> Total cable bill cost for 2023: $310

[THINKING]
The total cost of cable bills for this year (2023) is $310. 
```
### [NG3] appworld — `apis.splitwise.record_expense.debtor_emails`
- value: `["sab-brown@gmail.com", "br_ritt@gmail.com"]`
- text 末 120 字符:
```
 names and trip names:
- Honolulu trip → Honolulu group (276) ✓
- London trip → London group (279) ✓
- Zurich trip → ? 

```
### [NG4] appworld — `apis.venmo.create_payment_request.access_token`
- value: `venmo_token["access_token"]`
- text 末 120 字符:
```
ate_payment_request` API. Now I need to:
1. First, undo the money I accidentally sent to Stephen (transaction_id 8221). 
```
### [NG5] appworld — `apis.spotify.login.password`
- value: `!+EcqW8`
- text 末 120 字符:
```
bums in the user's album library."
 },
 
[THINKING]
Now I understand the Spotify API. I need to:
1. Login to Spotify
2. 
```
### [NG6] appworld — `apis.venmo.show_transactions.access_token`
- value: `venmo_token`
- text 末 120 字符:
```
Nicholas Weber) in 2023, and like them.

The roommates' emails are:
1. an-harrison@gmail.com
2. mel.bailey@gmail.com
3. 
```
### [NG7] appworld — `apis.file_system.show_file.path`
- value: `/home/chelsea/bills/internet/2023-01.txt`
- text 末 120 字符:
```
sts.

Let me look at the internet bills for 2023:
- 2023-01.txt
- 2023-02.txt
- 2023-03.txt
- 2023-04.txt
- 2023-05.pdf

```
### [NG8] appworld — `apis.spotify.show_album_privates.album_id`
- value: `aid`
- text 末 120 字符:
```
e ✗
- Song 302: liked=False, downloaded=False ✗

Now for albums: I need to check which albums are liked AND downloaded. 
```
### [NG9] appworld — `apis.spotify.search_playlists.query`
- value: `best`
- text 末 120 字符:
```
lists I've checked so far only have about 30-42 minutes of music. The longest workout is 130 minutes (Saturday hiking). 
```
### [NG10] appworld — `apis.todoist.delete_task.access_token`
- value: `td_token`
- text 末 120 字符:
```
35: 55 minutes
- 6342: 60 minutes
- 6338: 65 minutes
- 6336: 85 minutes
- 6339: 90 minutes

Available time: 245 minutes

```
