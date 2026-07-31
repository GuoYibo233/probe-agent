# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] bfcl — `get_nearest_airport_by_city.location`
- value: `New York`  区间 [7664,7672)
```
...New York".⏎Done. ⏎Proceeding. ⏎[Output] `[get_nearest_airport_by_city(location="【New York】")]`⏎(Self-Correction/Note during generation)⏎I realize I can just call `get_fli...
```
### [2] bfcl — `book_flight.travel_from`
- value: `CRH`  区间 [604,607)
```
...nt Hollow to New York.⏎I have retrieved the airport codes:⏎- Crescent Hollow -> 【CRH】⏎...
```
### [3] bfcl — `cd.folder`
- value: `research`  区间 [2535,2543)
```
... `ls` to see if `archives` exists.⏎Step 3: `mkdir archives` if not.⏎Step 4: `cp 【research】_notes.txt archives`⏎Step 5: `cd archives`⏎...
```
### [4] bfcl — `purchase_insurance.insurance_type`
- value: `travel`  区间 [4563,4569)
```
...Proceed. ⏎Output: [purchase_insurance(access_token="abc123xyz", insurance_type="【travel】", insurance_cost=150.0, booking_id="3426812", card_id="card_7243")]⏎...
```
### [5] bfcl — `logarithm.value`
- value: `980.0`  区间 [3510,3515)
```
...e of 20."⏎I will use base=20.0.⏎All good. ⏎Output generation. ⏎[logarithm(value=【980.0】, base=20.0, precision=10)]⏎Done. ⏎Wait, the prompt says "base the previous fuel...
```
### [6] bfcl — `set_navigation.destination`
- value: `2107 Channing Way, Berkeley, CA`  区间 [1181,1212)
```
...arams_name=params_value)]`⏎Yes.⏎Proceed. ⏎Output: `[set_navigation(destination="【2107 Channing Way, Berkeley, CA】")]`⏎Done. ⏎...
```
### [7] bfcl — `lockDoors.unlock`
- value: `False`  区间 [1364,1369)
```
...ep, or I can call both. I'll call lockDoors first.⏎Let's call `lockDoors(unlock=【False】, door=["driver", "passenger", "rear_left", "rear_right"])`.⏎Then `startEngine(i...
```
### [8] bfcl — `get_symbol_by_name.name`
- value: `Nvidia`  区间 [1030,1036)
```
...company Nvidia at the going market rate".⏎I will call `get_symbol_by_name(name="【Nvidia】")`.⏎Then I will need to call `get_stock_info` and `place_order` in subsequent t...
```
### [9] bfcl — `register_credit_card.cardholder_name`
- value: `Michael Smith`  区间 [7500,7513)
```
...z', card_number='4012888888881881', expiration_date='12/2028', cardholder_name='【Michael Smith】', card_verification_number=465)]⏎Done. ⏎(Self-Correction/Verification during ge...
```
### [10] bfcl — `logarithm.precision`
- value: `4`  区间 [1137,1138)
```
...s call the logarithm function first.⏎`logarithm(value=36.0, base=6.0, precision=【4】)`⏎⏎...
```
### [11] bfcl — `lockDoors.door`
- value: `["driver", "passenger", "rear_left", "rear_right"]`  区间 [1782,1832)
```
...ock all doors.⏎⏎Let's prepare the function calls.⏎`lockDoors(unlock=False, door=【["driver", "passenger", "rear_left", "rear_right"]】)`⏎`startEngine(ignitionMode="START")`⏎⏎Check parameters for `lockDoors`:⏎`unloc...
```
### [12] bfcl — `lockDoors.unlock`
- value: `False`  区间 [1661,1666)
```
...ld try to start the engine again.⏎⏎So the next steps are:⏎1.  `lockDoors(unlock=【False】, door=["driver", "passenger", "rear_left", "rear_right"])`⏎...
```
### [13] bfcl — `message_login.user_id`
- value: `USR001`  区间 [173,179)
```
...my cousin (user id USR002), updating them my status. If you need, my user id is 【USR001】.⏎[HISTORY]⏎[find_nearest_tire_shop()] -> {"shopLocation": "456 Oakwood Avenue, ...
```
### [14] bfcl — `place_order.price`
- value: `457.23`  区间 [583,589)
```
...is price.⏎Parameters for `place_order`:⏎order_type: "Buy"⏎symbol: "OMEG"⏎price: 【457.23】⏎...
```
### [15] bfcl — `book_flight.access_token`
- value: `abc123xyz`  区间 [4419,4428)
```
...schema. Format is correct. No extra text.⏎Proceeds. ⏎[book_flight(access_token="【abc123xyz】", card_id="card1234", travel_date="2026-12-15", travel_from="RMS", travel_to="G...
```
### [16] bfcl — `place_order.symbol`
- value: `MSFT`  区间 [2258,2262)
```
...ing matches.⏎Ready. ⏎Output generation. ⏎[place_order(order_type="Buy", symbol="【MSFT】", price=310.23, amount=100)]⏎Done. ⏎...
```
### [17] bfcl — `contact_customer_support.booking_id`
- value: `3426812`  区间 [5362,5369)
```
...good. ⏎Proceeds. ⏎[Output Generation] -> `[contact_customer_support(booking_id='【3426812】', message='Urgent booking-related query')]`⏎Done. ⏎(Self-Correction/Note during...
```
### [18] bfcl — `book_flight.access_token`
- value: `secure_access_token_987654321`  区间 [826,855)
```
...Airport)⏎- Date: 2026-12-15⏎- Class: first⏎- Card ID: card_4526⏎- Access Token: 【secure_access_token_987654321】⏎⏎...
```
### [19] bfcl — `fillFuelTank.fuelAmount`
- value: `39.5`  区间 [556,560)
```
...ank can hold up to 50 gallons.⏎To fill it completely, I need to add 50 - 10.5 = 【39.5】 gallons.⏎...
```
### [20] bfcl — `cd.folder`
- value: `projects`  区间 [3585,3593)
```
... was because the file doesn't exist? No, `find` found it.⏎⏎Let's try `cd` into `【projects】/photography` first. Then I can copy the files. But where to? The user wants the...
```
### [21] bfcl — `get_zipcode_based_on_city.city`
- value: `San Francisco`  区间 [2984,2997)
```
....⏎⏎Let's start with getting the zipcodes.⏎⏎*   `get_zipcode_based_on_city(city="【San Francisco】")`⏎*   `get_zipcode_based_on_city(city="Rivermist")`⏎⏎After getting zipcodes, I...
```
### [22] bfcl — `get_booking_history.access_token`
- value: `abc123xyz`  区间 [5812,5821)
```
... `access_token`. I have it.⏎Ready. ⏎Output: `[get_booking_history(access_token="【abc123xyz】")]`⏎...
```
### [23] bfcl — `compute_exchange_rate.value`
- value: `20000.0`  区间 [8171,8178)
```
...compute_exchange_rate⏎Params: base_currency="RMB", target_currency="USD", value=【20000.0】⏎Matches schema.⏎Ready. ⏎Output matches requested format.⏎Proceeds. ⏎(Self-Corre...
```
### [24] bfcl — `add_to_watchlist.stock`
- value: `AAPL`  区间 [3441,3445)
```
...chlist()`.⏎Done. ⏎Proceeding. ⏎Output matches format.⏎`[add_to_watchlist(stock="【AAPL】"), get_watchlist()]`⏎Wait, the prompt says "integrate Apple's stock into my cur...
```
### [25] bfcl — `cd.folder`
- value: `documents`  区间 [183,192)
```
...t line look like?⏎[HISTORY]⏎(start)⏎[THINKING]⏎The user wants to:⏎1. Go to the `【documents】` folder in the current working directory (CWD).⏎...
```
### [26] bfcl — `close_ticket.ticket_id`
- value: `3`  区间 [1642,1643)
```
...icket(ticket_id=3)`⏎Ready. ⏎Output matches. ⏎Proceeds. ⏎[close_ticket(ticket_id=【3】)]⏎Done. ⏎(Self-Correction/Verification during thought)⏎...
```
### [27] bfcl — `place_order.order_type`
- value: `Buy`  区间 [1646,1649)
```
...0.23, amount=100)`⏎Done. ⏎Wait, checking the function signature:⏎`order_type`: "【Buy】/Sell"⏎`symbol`: "MSFT"⏎`price`: 310.23⏎`amount`: 100⏎All good.⏎I will generate ...
```
### [28] bfcl — `book_flight.travel_to`
- value: `LAX`  区间 [678,681)
```
...)] -> {"nearest_airport": "LAX"}⏎[get_flight_cost(travel_from="RMS", travel_to="【LAX】", travel_date="2026-11-10", travel_class="business")] -> {"travel_cost_list": [...
```
### [29] bfcl — `get_stock_info.symbol`
- value: `XYZ`  区间 [729,732)
```
...but didn't provide a specific number. I need to get the current stock info for "【XYZ】" first to find its price.⏎- `amount`: 100⏎...
```
### [30] bfcl — `lockDoors.door`
- value: `["driver", "passenger", "rear_left", "rear_right"]`  区间 [4674,4724)
```
... ⏎Output matches. ⏎Done. ⏎[Output Generation] -> `[lockDoors(unlock=False, door=【["driver", "passenger", "rear_left", "rear_right"]】), startEngine(ignitionMode="START")]`⏎(Note: I'll make sure the formatting matc...
```
### [31] bfcl — `get_available_stocks.sector`
- value: `Technology`  区间 [398,408)
```
...r specified "technology sector".⏎So I should call `get_available_stocks(sector="【Technology】")`.⏎⏎...
```
### [32] bfcl — `get_zipcode_based_on_city.city`
- value: `Rivermist`  区间 [4586,4595)
```
...ll good. ⏎Proceeding. ⏎[Output Generation] -> `[get_zipcode_based_on_city(city="【Rivermist】"), get_zipcode_based_on_city(city="Stonebrook")]`⏎Done. ⏎(Self-Correction/Verif...
```
### [33] bfcl — `lockDoors.door`
- value: `["driver", "passenger", "rear_left", "rear_right"]`  区间 [2950,3000)
```
...t:⏎Wait, `lockDoors` parameter `door` expects an array of strings. The enum is `【["driver", "passenger", "rear_left", "rear_right"]】`.⏎`activateParkingBrake` parameter `mode` expects string. Enum `["engage", "rel...
```
### [34] bfcl — `fillFuelTank.fuelAmount`
- value: `20.0`  区间 [709,713)
```
...llons.⏎The user specified 20 gallons.⏎So I should call `fillFuelTank(fuelAmount=【20.0】)`.⏎Let's verify the parameters:⏎`fillFuelTank` requires `fuelAmount` (float).⏎T...
```
### [35] bfcl — `get_flight_cost.travel_from`
- value: `LAX`  区间 [1656,1659)
```
...all `get_flight_cost` and `get_all_credit_cards`.⏎`get_flight_cost(travel_from="【LAX】", travel_to="JFK", travel_date="2026-10-12", travel_class="business")`⏎`get_all...
```
### [36] bfcl — `book_flight.travel_class`
- value: `economy`  区间 [2853,2860)
```
...1", travel_date="2026-08-10", travel_from="ORD", travel_to="LAX", travel_class="【economy】")⏎Done. ⏎...
```
### [37] bfcl — `get_zipcode_based_on_city.city`
- value: `Silverpine`  区间 [3511,3521)
```
...matches. ⏎Proceeding. ⏎[Output Generation] -> `[get_zipcode_based_on_city(city="【Silverpine】"), get_zipcode_based_on_city(city="Oakendale")]`⏎Wait, should I just call them?...
```
### [38] bfcl — `find.name`
- value: `analysis_report.csv`  区间 [1258,1277)
```
...."⏎The parameters are `name` and `path`. `path` defaults to ".".⏎So `find(name="【analysis_report.csv】")` will search recursively from the current directory.⏎⏎...
```
### [39] bfcl — `sort.file_name`
- value: `Notes2023.txt`  区间 [2584,2597)
```
...alphabetically sorted version of 'Notes2023.txt'."⏎I will call `sort(file_name='【Notes2023.txt】')`.⏎Then I will take the result and count characters. But I don't have a string...
```
### [40] bfcl — `authenticate_twitter.username`
- value: `michael_smith`  区间 [740,753)
```
...Travel' and 'Adventure'.⏎⏎1.  **Authenticate**: `authenticate_twitter(username='【michael_smith】', password='michael1234')`⏎2.  **Post Tweet**: `post_tweet(content='Exploring t...
```
### [41] bfcl — `authenticate_travel.client_secret`
- value: `M@xSecret!`  区间 [243,253)
```
...ls are ready for you: the client ID is 'trav3lMaxID2023', the client secret is '【M@xSecret!】', and the refresh token 'r3freshM3n0w'. If you could handle the authentication,...
```
### [42] bfcl — `authenticate_twitter.password`
- value: `john1234`  区间 [397,405)
```
... my trip to LA'. Be sure to authenticate using my username 'john' and password '【john1234】'.⏎[HISTORY]⏎Flight cost estimate: $400 USD. Converted to EUR: €320. Since this ...
```
### [43] bfcl — `rm.file_name`
- value: `SuperResearch/findings_report`  区间 [666,695)
```
... description says "Remove a directory at current directory."⏎⏎The file path is "【SuperResearch/findings_report】".⏎The `rm` tool takes `file_name`. The description says "The name of the file o...
```
### [44] bfcl — `get_user_id.user`
- value: `Michael`  区间 [4827,4834)
```
...essary.⏎Done. ⏎Output matches. ⏎Proceeds. ⏎[Final Response] `[get_user_id(user="【Michael】")]`⏎...
```
### [45] bfcl — `wc.mode`
- value: `l`  区间 [1465,1466)
```
..._name='DataSet1.csv', mode='l')`⏎`wc(file_name='DataSet1.csv', mode='w')`⏎`wc(fi【l】e_name='DataSet1.csv', mode='c')`⏎...
```
### [46] bfcl — `resolve_ticket.resolution`
- value: `Fixed through manual troubleshooting techniques.`  区间 [640,688)
```
...o resolve the ticket with ID 987654.⏎The user provided the resolution summary: '【Fixed through manual troubleshooting techniques.】'⏎...
```
### [47] bfcl — `displayCarStatus.option`
- value: `fuel`  区间 [1350,1354)
```
...fuel")` now.⏎Let's do that.⏎Actually, I can just call `displayCarStatus(option="【fuel】")`.⏎...
```
### [48] bfcl — `find.name`
- value: `annual_report.txt`  区间 [1754,1771)
```
...the file system." This strongly implies it exists.⏎I will use `find` to locate '【annual_report.txt】'.⏎Then I will use `cd` to navigate to the directory containing it.⏎...
```
### [49] bfcl — `authenticate_twitter.username`
- value: `tech_guru`  区间 [4811,4820)
```
...h.⏎I will output both.⏎Done. ⏎Checking format: `[authenticate_twitter(username="【tech_guru】", password="securePass123"), post_tweet(content="Initial summary of the project...
```
### [50] bfcl — `get_zipcode_based_on_city.city`
- value: `San Francisco`  区间 [1927,1940)
```
... from Rivermist to San Francisco."⏎I will call `get_zipcode_based_on_city(city="【San Francisco】")`.⏎Then I will use the result to call `estimate_distance`.⏎Let's do it. ⏎Wait,...
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] bfcl — `place_order.order_type`
- value: `Buy`
- text 末 120 字符:
```
5-Day Moving  -> 
[THINKING]
The user wants to buy 50 shares of Zeta Corp (symbol: ZETA) at the prevailing market rate.

```
### [NG2] bfcl — `book_flight.travel_to`
- value: `LAX`
- text 末 120 字符:
```
   - From: San Francisco (SF)
   - To: Los Angeles (LA)
   - Date: November 25th 2026 (2026-11-25)
   - Class: business

```
### [NG3] bfcl — `purchase_insurance.insurance_cost`
- value: `769.0`
- text 末 120 字符:
```
hensive
Insurance cost: 769
Card ID: main1234
Access token: abc123xyz

I need to call `purchase_insurance`.
Parameters:

```
### [NG4] bfcl — `get_flight_cost.travel_date`
- value: `2026-12-15`
- text 末 120 字符:
```
m JFK to LAX on December 15, 2026.
2. Book the flight using credit card id 'card_2108' and access token 'abc123xyz'.
3. 
```
### [NG5] bfcl — `send_message.params`
- value: `{"receiver_id": "travel_advisor", "message": "Details regarding problems faced with the flight booking transaction."}`
- text 末 120 字符:
```
f the user to send the message to."},
        "message": {"type": "string", "description": "Message to be sent."}
    }

```
### [NG6] bfcl — `ls.a`
- value: `True`
- text 末 120 字符:
```
key.
[HISTORY]
(start)
[THINKING]
The user wants me to:
1. List files in the initial directory, including hidden files.

```
### [NG7] bfcl — `retrieve_invoice.params`
- value: `{"access_token": "abc123xyz", "booking_id": "latest_reservation"}`
- text 末 120 字符:
```
 ID for insurance. It's safe to assume they want the invoice for that same booking, or I should ask for the booking ID.

```
### [NG8] bfcl — `place_order.price`
- value: `150.0`
- text 末 120 字符:
```
 wants to place a 'Buy' order for 100 shares of AAPL at a price of $150 each.
I need to use the `place_order` function.

```
### [NG9] bfcl — `get_flight_cost.params_name3`
- value: `travel_date`
- text 末 120 字符:
```
(start)
[THINKING]
The user wants to know the cost of a flight from LAX to JFK on November 15, 2026, in business class.

```
### [NG10] bfcl — `cd.folder`
- value: `..`
- text 末 120 字符:
```
rrent_directory_content": ["proposal.docx", "notes.md"]}
[THINKING]
I found "proposal.docx" in the workspace directory. 
```
