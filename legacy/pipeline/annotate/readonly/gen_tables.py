import json, pathlib

BASE = pathlib.Path("/home/y-guo/reproduce/new1/pipeline/data")
OUT  = pathlib.Path("/home/y-guo/reproduce/new1/pipeline/annotate/readonly")

def load_union(base):
    union = {}
    for m in ["q35", "q36", "gptoss"]:
        v = json.loads((base / m / "tool_vocab.json").read_text())
        for k, c in v.items():
            union[k] = union.get(k, 0) + c
    return union

# ---------- AppWorld: judged by the verb in apis.app.verb_... ----------
AW_RO_VERBS = {
    "show":      "pure display, changes no state",
    "search":    "pure query, changes no state",
    "list":      "pure listing, changes no state",
    "get":       "pure read, changes no state",
    "read":      "pure read of file contents",
    "file":      "file_exists: checks existence only",
    "directory": "directory_exists: checks existence only",
}
AW_NRO_VERBS = {
    "complete":  "submits the task's final answer; once sent, the task is over",
    "create":    "creates a new object (transfer/file/playlist/task, ...)",
    "add":       "appends an object or a sum of money",
    "update":    "rewrites an existing object",
    "delete":    "deletes an object",
    "remove":    "removes an object",
    "send":      "sends outward (SMS/voice/verification code)",
    "approve":   "approves a payment request; moves money",
    "deny":      "rejects a payment request",
    "like":      "writes like state",
    "unlike":    "writes unlike",
    "follow":    "writes follow state",
    "unfollow":  "writes unfollow state",
    "record":    "bookkeeping write",
    "accept":    "accepts an invite; writes member state",
    "post":      "posts a comment",
    "assign":    "changes task assignment",
    "play":      "changes player state",
    "previous":  "changes player state",
    "next":      "changes player state",
    "shuffle":   "changes the playback queue",
    "clear":     "clears the playback queue",
    "review":    "writes a review",
    "remind":    "sends a reminder outward",
    "withdraw":  "withdraws money; changes balance",
    "signup":    "registers a new account",
    "reset":     "resets password",
    "compress":  "generates an archive; writes to the file system",
    "move":      "moves a file; writes to the file system",
    "download":  "writes to the download library / saves a file to disk",
    "pause":     "changes player state",
}
AW_BORDERLINE = {
    "login": (False, "login-type: ruled on 2026-08-01, under the strict read-only basis this counts as not read-only (changes session state)"),
}

def classify_appworld(union):
    table, uncovered = {}, []
    for tool, cnt in union.items():
        verb = tool.split(".")[-1].split("_")[0]
        if verb in AW_BORDERLINE:
            ro, reason = AW_BORDERLINE[verb]
            table[tool] = dict(readonly=ro, count=cnt, reason=reason, flag="borderline")
        elif verb in AW_RO_VERBS:
            table[tool] = dict(readonly=True, count=cnt, reason=AW_RO_VERBS[verb], flag=None)
        elif verb in AW_NRO_VERBS:
            table[tool] = dict(readonly=False, count=cnt, reason=AW_NRO_VERBS[verb], flag=None)
        else:
            table[tool] = dict(readonly=False, count=cnt, reason="verb not in the rule table; conservatively judged not read-only", flag="uncovered")
            uncovered.append(tool)
    return table, uncovered

# ---------- BFCL: no namespace, explicit list ----------
BFCL_RO = {
    # shell read operations
    "ls": "lists a directory", "cat": "reads a file", "pwd": "shows the current directory", "find": "finds files",
    "grep": "text search", "wc": "counts lines", "tail": "reads the tail of a file", "du": "checks disk usage",
    "diff": "compares files; reads both sides only", "sort": "returns sorted results; does not write back to the file", "display_log": "shows logs",
    # transaction queries
    "get_stock_info": "looks up stock price", "get_symbol_by_name": "looks up ticker symbol", "get_watchlist": "looks up the watchlist",
    "get_account_info": "looks up the account", "get_available_stocks": "looks up tradeable stocks",
    "get_order_details": "looks up order details", "get_order_history": "looks up order history", "get_current_time": "looks up the time",
    "get_transaction_history": "looks up trade history", "retrieve_invoice": "looks up invoice",
    # travel queries
    "get_nearest_airport_by_city": "looks up airport", "get_flight_cost": "looks up fare",
    "get_zipcode_based_on_city": "looks up zip code", "list_all_airports": "lists airports",
    "get_credit_card_balance": "looks up card balance", "get_all_credit_cards": "lists credit cards",
    "get_booking_history": "looks up booking history", "verify_traveler_information": "verifies information; compares only, does not write",
    "compute_exchange_rate": "pure exchange-rate calculation",
    # vehicle queries
    "displayCarStatus": "shows vehicle condition", "check_tire_pressure": "looks up tire pressure",
    "estimate_distance": "pure distance calculation", "estimate_drive_feasibility_by_mileage": "pure reachability calculation",
    "get_outside_temperature_from_google": "looks up temperature", "find_nearest_tire_shop": "looks up tire shops",
    # message/twitter/ticket queries
    "view_messages_sent": "looks up sent messages", "search_messages": "searches messages",
    "get_user_id": "looks up user id", "list_users": "lists users",
    "message_get_login_status": "checks login state", "posting_get_login_status": "checks login state",
    "ticket_get_login_status": "checks login state", "trading_get_login_status": "checks login state",
    "get_user_tickets": "looks up ticket", "get_ticket": "looks up ticket", "get_user_tweets": "looks up tweet",
    # pure math
    "mean": "pure calculation", "standard_deviation": "pure calculation", "logarithm": "pure calculation",
    "round_number": "pure calculation", "sum_values": "pure calculation", "divide": "pure calculation",
    "multiply": "pure calculation", "MA": "pure moving-average calculation", "liter_to_gallon": "pure unit conversion",
    "gallon_to_liter": "pure unit conversion", "imperial_si_conversion": "pure unit conversion",
}
BFCL_NRO = {
    # shell write operations and status
    "cd": "changes the current directory; a wrong guess will make subsequent real commands run in the wrong place", "touch": "creates a file", "mkdir": "creates a directory",
    "mv": "moves a file", "cp": "copies a file", "rm": "deletes a file", "rmdir": "deletes a directory",
    "echo": "writes a file when the file_name argument is given",
    # vehicle control
    "startEngine": "ignition", "func_startEngine": "ignition (variant name seen in logs)",
    "pressBrakePedal": "brakes", "releaseBrakePedal": "releases the brake", "lockDoors": "locks the doors",
    "fillFuelTank": "refuels", "setCruiseControl": "sets cruise control", "set_navigation": "sets navigation",
    # transaction write operations
    "place_order": "places an order; moves money", "cancel_order": "cancels an order", "add_to_watchlist": "writes the watchlist",
    "remove_stock_from_watchlist": "writes the watchlist", "fund_account": "deposits funds", "withdraw_funds": "withdraws funds",
    "trading_logout": "logs out the session; subsequent real calls will fail",
    # travel write operations
    "book_flight": "books a ticket; moves money", "cancel_booking": "cancels a ticket", "purchase_insurance": "buys insurance; moves money",
    "register_credit_card": "links a card", "set_budget_limit": "sets a budget cap",
    "contact_customer_support": "sends a message to customer service",
    # message/twitter/ticket write operations
    "send_message": "sends a message; cannot be recalled", "delete_message": "deletes a message", "add_contact": "writes the contact list",
    "post_tweet": "posts a tweet; cannot be recalled", "retweet": "retweets", "comment": "posts a comment", "mention": "posts an @mention",
    "create_ticket": "opens a ticket", "resolve_ticket": "changes ticket status", "close_ticket": "closes a ticket",
    "edit_ticket": "changes ticket content",
    # junk/unknown names in the logs
    "deploy": "unidentified; conservatively judged not read-only", "line": "unidentified; conservatively judged not read-only",
    "func_call": "a hallucinated artifact; conservatively judged not read-only", "func_name1": "a hallucinated artifact; conservatively judged not read-only",
}
_LOGIN_REASON = "login-type: ruled on 2026-08-01, under the strict read-only basis this counts as not read-only (changes session state)"
BFCL_BORDERLINE = {
    "authenticate_twitter": (False, _LOGIN_REASON),
    "authenticate_travel":  (False, _LOGIN_REASON),
    "ticket_login":         (False, _LOGIN_REASON),
    "message_login":        (False, _LOGIN_REASON),
    "trading_login":        (False, _LOGIN_REASON),
}

def classify_bfcl(union):
    table, uncovered = {}, []
    for tool, cnt in union.items():
        if tool in BFCL_BORDERLINE:
            ro, reason = BFCL_BORDERLINE[tool]
            table[tool] = dict(readonly=ro, count=cnt, reason=reason, flag="borderline")
        elif tool in BFCL_RO:
            table[tool] = dict(readonly=True, count=cnt, reason=BFCL_RO[tool], flag=None)
        elif tool in BFCL_NRO:
            table[tool] = dict(readonly=False, count=cnt, reason=BFCL_NRO[tool], flag=None)
        else:
            table[tool] = dict(readonly=False, count=cnt, reason="not on the list; conservatively judged not read-only", flag="uncovered")
            uncovered.append(tool)
    return table, uncovered

for env, base, fn in [("appworld", BASE/"aw_official_v1", classify_appworld),
                      ("bfcl",     BASE/"bfcl_mtb_v1",    fn2 := classify_bfcl)]:
    union = load_union(base)
    table, uncovered = fn(union)
    (OUT / f"{env}.json").write_text(json.dumps(table, ensure_ascii=False, indent=1))
    n_ro   = sum(1 for v in table.values() if v["readonly"])
    e_all  = sum(v["count"] for v in table.values())
    e_ro   = sum(v["count"] for v in table.values() if v["readonly"])
    e_bl   = sum(v["count"] for v in table.values() if v["flag"] == "borderline")
    print(f"== {env}: {len(table)} tools, of which {n_ro} are read-only;"
          f"{e_all} events, {e_ro} read-only events ({e_ro/e_all:.1%}),"
          f"of which login-type borderline cases account for {e_bl} ({e_bl/e_all:.1%})")
    if uncovered:
        print(f"   not covered by the rules, conservatively judged not read-only: {uncovered}")
