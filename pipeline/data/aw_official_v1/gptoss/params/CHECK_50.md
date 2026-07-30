# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] appworld — `apis.venmo.login.password`
- value: `venmo_password`  区间 [4032,4046)
```
...⏎⏎Thus code:⏎⏎login_resp = apis.venmo.login(username=profile['email'], password=【venmo_password】)⏎token = login_resp.get("access_token")⏎print("Access token:", token)⏎⏎Now next...
```
### [2] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `file_system`  区间 [2332,2343)
```
...ybe", "can't make it", etc.) and update the CSV.⏎⏎We need to login to phone and 【file_system】 apps using supervisor credentials.⏎⏎...
```
### [3] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `phone`  区间 [2482,2487)
```
...=...). The docs for phone login? Let's view phone login API doc.⏎We need to see 【phone】 login doc.⏎We need to see Venmo login doc.⏎We need to see Venmo show_venmo_bala...
```
### [4] appworld — `apis.simple_note.login.username`
- value: `paul_mill@gmail.com`  区间 [6459,6478)
```
...ly was:⏎⏎```python⏎print("Simple Note token:", apis.simple_note.login(username="【paul_mill@gmail.com】", password="S]AqplV")["access_token"])⏎```⏎⏎Thus we have not stored the token i...
```
### [5] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `download_transaction_receipt`  区间 [18378,18406)
```
...⏎- For each transaction, we need to download receipt: receipt_path = apis.venmo.【download_transaction_receipt】(access_token=venmo_token, transaction_id=transaction_id). ...
```
### [6] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `spotify`  区间 [1458,1465)
```
...nse status code is 422:⏎{"message":"No APIs with name clear_queue found for the 【spotify】 app. Check the api and app name again."}⏎[THINKING]⏎We need to accomplish the t...
```
### [7] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `splitwise`  区间 [4502,4511)
```
...onment may have many APIs. We need to explore splitwise. Let's try to call apis.【splitwise】.show_account to see what it returns.⏎We need to see the output.⏎We need to see ...
```
### [8] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1329,1336)
```
...vious output was truncated)⏎print(apis.api_docs.show_api_descriptions(app_name="【spotify】")) -> [⏎ {⏎  "name": "show_account",⏎  "description": "Show your account inform...
```
### [9] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `create_playlist`  区间 [3276,3291)
```
...with only the allowed songs. But we need to preserve the title and privacy. The 【create_playlist】 API likely allows specifying title, is_public, maybe songs? ...
```
### [10] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_received_payment_requests`  区间 [1391,1421)
```
...") to see parameters.⏎We need to see the output.⏎We need to see the API doc for 【show_received_payment_requests】.⏎We need to see the output.⏎We need to see the API doc.⏎We need to see the outp...
```
### [11] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `phone`  区间 [3896,3901)
```
...ber may need to be in string format. Let's try that.⏎⏎We need to try login with 【phone】 number as username. Also maybe the password is correct. Let's try:⏎⏎...
```
### [12] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_file`  区间 [4966,4975)
```
...md" (case-insensitive):⏎       - Get file content: file_info = apis.file_system.【show_file】(access_token=token_fs, file_path=file_path)⏎       - content = file_info["conte...
```
### [13] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [5666,5673)
```
...```⏎We need to see output.⏎```python⏎print(apis.api_docs.show_api_doc(app_name="【spotify】", api_name="skip_to_previous"))⏎```⏎We need to see output.⏎...
```
### [14] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `play`  区间 [3022,3026)
```
...aylist is insufficient, we need to find a suitable playlist (maybe search for a 【play】list with enough songs) or create a new one.⏎⏎We need to explore the Simple Note...
```
### [15] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `phone`  区间 [3119,3124)
```
...essages may accept a query string like "Kristin". Let's explore the API doc for 【phone】's search_text_messages.⏎We need to see the API doc.⏎We need to call the API doc...
```
### [16] appworld — `apis.splitwise.login.username`
- value: `email`  区间 [7451,7456)
```
...il,               # supervisor is the payer⏎            receiver_email=creditor_【email】,   # creditor receives the payment⏎            amount=debt_amount,⏎            ...
```
### [17] appworld — `apis.venmo.login.password`
- value: `O*3`  区间 [7151,7154)
```
...⏎venmo_login = apis.venmo.login(username="morgan-harrison@gmail.com", password="【O*3】)aho")⏎print(venmo_login)⏎```⏎⏎We need to capture the token.⏎⏎If login fails, ma...
```
### [18] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_genres`  区间 [2479,2490)
```
...it. We can request each doc separately and maybe get full output. Let's request 【show_genres】 doc.⏎We need to get create_playlist doc.⏎We also need to get the full documenta...
```
### [19] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_note`  区间 [2961,2970)
```
... doc: we haven't seen it yet. Let's view it.⏎We need to request the API doc for 【show_note】.⏎We need to see the output.⏎We need to see the output.⏎We need to see the outpu...
```
### [20] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [4311,4316)
```
...use the Venmo password.⏎⏎After we get that, we can login to Venmo: token = apis.【venmo】.login(username=..., password=...)["access_token"]⏎⏎Then we need to get transact...
```
### [21] appworld — `apis.simple_note.update_note.content`
- value: `new_content`  区间 [5988,5999)
```
...s.simple_note.update_note(note_id=3084, access_token=simple_note_token, content=【new_content】)⏎print(update_result)⏎```⏎⏎We should also verify the note after update.⏎⏎Thus, ...
```
### [22] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `create_payment_request`  区间 [6438,6460)
```
...oc is not available due to a typo. Let's double-check the name. The list shows "【create_payment_request】". So it's correct. Let's try to call with correct case. It's all lower case. ...
```
### [23] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `file_system`  区间 [2805,2816)
```
..._path? Let's view its doc.⏎We need to call apis.api_docs.show_api_doc(app_name="【file_system】", api_name="compress_directory").⏎We need to see the output.⏎We need to see the...
```
### [24] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `venmo`  区间 [8921,8926)
```
... Let's try again.⏎```python⏎print(apis.api_docs.show_api_descriptions(app_name="【venmo】"))⏎```⏎We need to see the output. If we still get no output, we need to conside...
```
### [25] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `simple_note`  区间 [5033,5044)
```
...ta in candidate_notes:⏎        nid = note_meta["id"]⏎        note_detail = apis.【simple_note】.show_note(note_id=nid, access_token=access_token)⏎        title = note_detail.g...
```
### [26] appworld — `apis.phone.search_text_messages.only_latest_per_contact`
- value: `False`  区间 [1955,1960)
```
...    access_token=phone_token,⏎    query="playlist",⏎    only_latest_per_contact=【False】,⏎    page_index=0,⏎    page_limit=50⏎)⏎⏎# Combine and deduplicate messages⏎comb...
```
### [27] appworld — `apis.phone.search_text_messages.only_latest_per_contact`
- value: `False`  区间 [7255,7260)
```
...ook for any message containing the word "Splitwise"⏎    only_latest_per_contact=【False】,⏎    page_index=0,⏎    page_limit=20                    # max allowed by the AP...
```
### [28] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `login`  区间 [2480,2485)
```
...., password=...)["access_token"]; similarly for venmo: token_venmo = apis.venmo.【login】(username=..., password=...)["access_token"].⏎⏎Then search contacts: apis.phone....
```
### [29] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [4836,4843)
```
...ybe the environment is waiting. Let's try again with a simpler call: print(apis.【spotify】.login(...)). But we need credentials. So we need to get them first.⏎⏎Thus next ...
```
### [30] appworld — `apis.file_system.show_directory.path`
- value: `~/documents/work/meetings_files`  区间 [2106,2137)
```
...al home path. The path "~" may be accepted. Let's try show_directory with path="【~/documents/work/meetings_files】". Use recursive? Not needed.⏎⏎We need to parse each file name. The pattern: "<d...
```
### [31] appworld — `apis.phone.login.username`
- value: `8683971586`  区间 [12279,12289)
```
.... The phone login doc says username is "Your account phone_number." So we pass "【8683971586】". Good.⏎⏎Now we need to consider that the phone token may be needed for search_...
```
### [32] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `phone`  区间 [4530,4535)
```
...: maybe email? But description says username is phone_number. Could be that the 【phone】 number is stored with a leading country code like "+1" for US. The number "6639...
```
### [33] appworld — `apis.api_docs.show_api_descriptions.app_name`
- value: `spotify`  区间 [1029,1036)
```
...t we need to explore all relevant APIs. Let's request the list of API names for 【spotify】.⏎We need to see the output.⏎We need to see the doc for get_liked_albums. But we...
```
### [34] appworld — `apis.venmo.login.username`
- value: `ashlee_martinez@gmail.com`  区间 [7601,7626)
```
...:⏎supervisor_share = 38.0⏎if not any(⏎    tx.get("sender", {}).get("email") == "【ashlee_martinez@gmail.com】"⏎    and tx.get("receiver", {}).get("email") == manager_email⏎    and abs(float...
```
### [35] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [6791,6796)
```
... number "3808719492". We have passwords for each app: phone password "5!Dkf5d", 【venmo】 password "*mR5XTY". The Venmo account currently has insufficient balance, and t...
```
### [36] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `add_song_to_playlist`  区间 [1702,1722)
```
.... We need to see its doc. Let's request its API doc.⏎We need to see the doc for 【add_song_to_playlist】.⏎We need to see the output.⏎We need to see the output.⏎We need to see the outpu...
```
### [37] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [5826,5831)
```
...ke all the venmo transactions from yesterday involving any of my siblings on my 【venmo】 social feed."⏎⏎We have supervisor profile and passwords. We have Venmo password...
```
### [38] appworld — `apis.file_system.login.password`
- value: `Q8R#cPQ`  区间 [2719,2726)
```
... = apis.file_system.login(⏎    username="st-maldonado@gmail.com",⏎    password="【Q8R#cPQ】"⏎)⏎print("File system login response:", fs_login)⏎fs_token = fs_login.get("acce...
```
### [39] appworld — `apis.venmo.add_payment_card.owner_name`
- value: `Brandon Weber`  区间 [10008,10021)
```
...r number: 6011111111111117 (common test). Use card_name "Discover". Owner name "【Brandon Weber】". expiry_year 2028, expiry_month 12, cvv 123. Let's try that. If that fails, tr...
```
### [40] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1887,1894)
```
...visor.show_account_passwords() returns passwords for apps, including Spotify.⏎- 【spotify】.login(username, password) returns access_token.⏎...
```
### [41] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_account`  区间 [2700,2712)
```
...from apis.supervisor.show_account_passwords().⏎⏎We need to call apis.supervisor.【show_account】_passwords() to get passwords for each app. Then find the password for Spotify. ...
```
### [42] appworld — `apis.venmo.login.username`
- value: `siwhit@gmail.com`  区间 [14860,14876)
```
...---------------------------------------⏎login_resp = apis.venmo.login(username="【siwhit@gmail.com】", password="7=Z{ZMj")⏎print("Login response:", login_resp)⏎⏎access_token = logi...
```
### [43] appworld — `apis.file_system.login.password`
- value: `YUmI+0Z`  区间 [9152,9159)
```
...ogin_response = apis.file_system.login(username="dav.mart@gmail.com", password="【YUmI+0Z】")⏎print("Login response:", login_response)⏎token = login_response.get("access_t...
```
### [44] appworld — `apis.spotify.show_playlist_library.access_token`
- value: `token`  区间 [4383,4388)
```
...d in song_ids:⏎    song_info = apis.spotify.show_song(song_id=sid, access_token=【token】)⏎    # print song info for debugging maybe⏎    # parse year⏎    release_date = ...
```
### [45] appworld — `apis.venmo.login.username`
- value: `mar_blac@gmail.com`  区间 [1243,1261)
```
...asswords()) -> {⏎ "first_name": "Martin",⏎ "last_name": "Blackburn",⏎ "email": "【mar_blac@gmail.com】",⏎ "phone_number": "3539110281",⏎ "birthday": "1985-01-08",⏎ "sex": "male"⏎}⏎[⏎...
```
### [46] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `venmo`  区间 [6693,6698)
```
...) and password. The supervisor's email is 'jer.calhoun@gmail.com', password for 【venmo】 is '7vte5ic'.⏎⏎Then we need to send money to Robert's Venmo email. If we have R...
```
### [47] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_transactions`  区间 [3542,3559)
```
...o show_received_payment_requests (already seen). But we need to see the doc for 【show_transactions】 to get transaction details.⏎⏎We also need to see the doc for venmo show_transac...
```
### [48] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [7194,7201)
```
...put.⏎We need to see the output. Let's assume the output shows:⏎⏎{⏎ "app_name": "【spotify】",⏎ "api_name": "create_playlist",⏎ "path": "/playlists",⏎ "method": "POST",⏎ "d...
```
### [49] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `spotify`  区间 [1051,1058)
```
...e api and app name again."}⏎print(apis.api_docs.show_api_descriptions(app_name="【spotify】")) -> [⏎ {⏎  "name": "show_account",⏎  "description": "Show your account inform...
```
### [50] appworld — `apis.file_system.login.password`
- value: `0rE1V#a`  区间 [6634,6641)
```
...ogin⏎fs_login = apis.file_system.login(username="kat_simp@gmail.com", password="【0rE1V#a】")⏎fs_token = fs_login.get("access_token")⏎phone_login = apis.phone.login(userna...
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `add_song_to_playlist`
- text 末 120 字符:
```
ist of songs with song_id, title, etc. The response schema shows a list of objects with song_id, title, album_id, etc.


```
### [NG2] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `search_users`
- text 末 120 字符:
```
ion note, 'Have a great day!'. Then leave him a phone text message, 'Happy Birthday son! Hope you have a great day!'."


```
### [NG3] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_tasks`
- text 末 120 字符:
```
d "Inbox" or default). Then move tasks from Inbox to "Today's Goal" up to the maximum number that can fit in schedule.


```
### [NG4] appworld — `apis.api_docs.show_api_doc.api_name`
- value: `show_inbox_threads`
- text 末 120 字符:
```
ve from earlier. The earlier token was "abcdef1234567890abcdef1234567890". It gave a listing. So maybe we can reuse it. 
```
### [NG5] appworld — `apis.todoist.login.password`
- value: `get_password("todoist")`
- text 末 120 字符:
```
 content. For each line after the first line, if line starts with "add =>", we extract the track string after "add =>". 
```
### [NG6] appworld — `apis.phone.login.username`
- value: `jo-harr@gmail.com`
- text 末 120 字符:
```
 the $40) and also pay Nancy for her share of the dinner (i.e., the supervisor owes Nancy for her portion of the $166). 
```
### [NG7] appworld — `apis.api_docs.show_api_doc.app_name`
- value: `simple_note`
- text 末 120 字符:
```
...[cut]... pp. Check the api and app name again."}

[THINKING]
We have discovered the endpoint "add_song_to_playlist". 
```
### [NG8] appworld — `apis.spotify.search_artists.page_limit`
- value: `ARTIST_PAGE_LIMIT`
- text 末 120 字符:
```
y and sort_by follower_count descending. That might give us top artists. Then we can check which of those are followed. 
```
### [NG9] appworld — `apis.venmo.login.username`
- value: `phone_number`
- text 末 120 字符:
```
s transaction_id. Or maybe we need to use create_transaction_comment on the transaction ID associated with the request. 
```
### [NG10] appworld — `apis.spotify.login.password`
- value: `-m^8gsb`
- text 末 120 字符:
```
roach: Use page_limit=20 to reduce number of calls. Use page_index starting at 0, increment until empty list returned.


```
