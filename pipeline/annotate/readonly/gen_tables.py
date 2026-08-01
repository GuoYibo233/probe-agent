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

# ---------- AppWorld：按 apis.app.verb_... 的动词判 ----------
AW_RO_VERBS = {
    "show":      "纯展示，不改任何状态",
    "search":    "纯查询，不改任何状态",
    "list":      "纯列举，不改任何状态",
    "get":       "纯读取，不改任何状态",
    "read":      "纯读取文件内容",
    "file":      "file_exists：只查存在性",
    "directory": "directory_exists：只查存在性",
}
AW_NRO_VERBS = {
    "complete":  "提交任务终答，发出去任务就结束了",
    "create":    "新建对象（转账/文件/歌单/任务…）",
    "add":       "追加对象或款项",
    "update":    "改写已有对象",
    "delete":    "删除对象",
    "remove":    "移除对象",
    "send":      "对外发送（短信/语音/验证码）",
    "approve":   "批准付款请求，动钱",
    "deny":      "拒绝付款请求",
    "like":      "写入点赞状态",
    "unlike":    "写入取消点赞",
    "follow":    "写入关注状态",
    "unfollow":  "写入取关状态",
    "record":    "记账写入",
    "accept":    "接受邀请，写入成员状态",
    "post":      "发表评论",
    "assign":    "改任务分配",
    "play":      "改播放器状态",
    "previous":  "改播放器状态",
    "next":      "改播放器状态",
    "shuffle":   "改播放队列",
    "clear":     "清空播放队列",
    "review":    "写入评价",
    "remind":    "对外发提醒",
    "withdraw":  "取钱，动余额",
    "signup":    "注册新账号",
    "reset":     "重置密码",
    "compress":  "生成压缩包，写文件系统",
    "move":      "移动文件，写文件系统",
    "download":  "写入下载库/落盘文件",
    "pause":     "改播放器状态",
}
AW_BORDERLINE = {
    "login": (False, "登录类：2026-08-01 拍板按严格只读口径判非只读（改会话状态）"),
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
            table[tool] = dict(readonly=False, count=cnt, reason="动词未入规则表，保守判非只读", flag="uncovered")
            uncovered.append(tool)
    return table, uncovered

# ---------- BFCL：无命名空间，显式清单 ----------
BFCL_RO = {
    # shell 读操作
    "ls": "列目录", "cat": "读文件", "pwd": "显示当前目录", "find": "查找文件",
    "grep": "文本搜索", "wc": "统计行数", "tail": "读文件尾部", "du": "查磁盘占用",
    "diff": "比较文件，只读两侧", "sort": "返回排序结果，不写回文件", "display_log": "显示日志",
    # 交易查询
    "get_stock_info": "查股价", "get_symbol_by_name": "查代码", "get_watchlist": "查自选列表",
    "get_account_info": "查账户", "get_available_stocks": "查可交易股票",
    "get_order_details": "查订单详情", "get_order_history": "查订单历史", "get_current_time": "查时间",
    "get_transaction_history": "查交易历史", "retrieve_invoice": "查发票",
    # 差旅查询
    "get_nearest_airport_by_city": "查机场", "get_flight_cost": "查票价",
    "get_zipcode_based_on_city": "查邮编", "list_all_airports": "列机场",
    "get_credit_card_balance": "查卡余额", "get_all_credit_cards": "列信用卡",
    "get_booking_history": "查订票历史", "verify_traveler_information": "核对信息，只比对不写入",
    "compute_exchange_rate": "纯计算汇率",
    # 车辆查询
    "displayCarStatus": "显示车况", "check_tire_pressure": "查胎压",
    "estimate_distance": "纯计算距离", "estimate_drive_feasibility_by_mileage": "纯计算可达性",
    "get_outside_temperature_from_google": "查气温", "find_nearest_tire_shop": "查轮胎店",
    # 消息/推特/工单查询
    "view_messages_sent": "查已发消息", "search_messages": "搜消息",
    "get_user_id": "查用户 id", "list_users": "列用户",
    "message_get_login_status": "查登录态", "posting_get_login_status": "查登录态",
    "ticket_get_login_status": "查登录态", "trading_get_login_status": "查登录态",
    "get_user_tickets": "查工单", "get_ticket": "查工单", "get_user_tweets": "查推文",
    # 纯数学
    "mean": "纯计算", "standard_deviation": "纯计算", "logarithm": "纯计算",
    "round_number": "纯计算", "sum_values": "纯计算", "divide": "纯计算",
    "multiply": "纯计算", "MA": "纯计算移动平均", "liter_to_gallon": "纯换算",
    "gallon_to_liter": "纯换算", "imperial_si_conversion": "纯换算",
}
BFCL_NRO = {
    # shell 写操作与状态
    "cd": "改当前目录，猜错会让后续真实命令跑错地方", "touch": "建文件", "mkdir": "建目录",
    "mv": "移动文件", "cp": "复制文件", "rm": "删文件", "rmdir": "删目录",
    "echo": "带 file_name 参数时会写文件",
    # 车辆控制
    "startEngine": "点火", "func_startEngine": "点火（日志里的变体名）",
    "pressBrakePedal": "踩刹车", "releaseBrakePedal": "松刹车", "lockDoors": "锁门",
    "fillFuelTank": "加油", "setCruiseControl": "设定巡航", "set_navigation": "设定导航",
    # 交易写操作
    "place_order": "下单，动钱", "cancel_order": "撤单", "add_to_watchlist": "写自选列表",
    "remove_stock_from_watchlist": "写自选列表", "fund_account": "入金", "withdraw_funds": "出金",
    "trading_logout": "登出会话，后续真实调用会失效",
    # 差旅写操作
    "book_flight": "订票，动钱", "cancel_booking": "退票", "purchase_insurance": "买保险，动钱",
    "register_credit_card": "绑卡", "set_budget_limit": "设预算上限",
    "contact_customer_support": "给客服发消息",
    # 消息/推特/工单写操作
    "send_message": "发消息，收不回", "delete_message": "删消息", "add_contact": "写通讯录",
    "post_tweet": "发推文，收不回", "retweet": "转推", "comment": "发评论", "mention": "发@提及",
    "create_ticket": "开工单", "resolve_ticket": "改工单状态", "close_ticket": "关工单",
    "edit_ticket": "改工单内容",
    # 日志里的垃圾/未知名
    "deploy": "身份不明，保守判非只读", "line": "身份不明，保守判非只读",
    "func_call": "幻觉产物，保守判非只读", "func_name1": "幻觉产物，保守判非只读",
}
_LOGIN_REASON = "登录类：2026-08-01 拍板按严格只读口径判非只读（改会话状态）"
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
            table[tool] = dict(readonly=False, count=cnt, reason="未入清单，保守判非只读", flag="uncovered")
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
    print(f"== {env}: 工具 {len(table)} 个，其中只读 {n_ro} 个；"
          f"事件 {e_all} 个，只读事件 {e_ro} 个（{e_ro/e_all:.1%}），"
          f"其中登录类 borderline 占 {e_bl} 个（{e_bl/e_all:.1%}）")
    if uncovered:
        print(f"   规则没覆盖、保守判非只读的：{uncovered}")
