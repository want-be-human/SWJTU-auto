#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动定点抢：后天 8号羽毛球 20:00-21:00（每天 22:30:00 精确触发）
特性：
- 精确到秒等待 22:30:00
- 在 22:29:59 到 22:30:00 之间进行短时高频 "burst" 拉取（可开/关）
- 到点后切换到正常轮询并在拿到 sessionId 后立即下单（支持多次尝试）
- 终端输出全部运行日志

使用前：
- 编辑下方 CONFIG 区域，填写 TOKEN 和 MEMBER_ID
- 将脚本放到你要运行的机器上（注意系统时间需为北京时间或与你期望一致）
- 手动运行脚本（脚本会阻塞等待到 22:30:00）
"""

import requests
import time
import datetime
import random
import sys

# --------------------- CONFIG ---------------------
TOKEN = "c1fd08b5-d49a-47b2-afaa-be66b4078274"
MEMBER_ID = "1697570245594587136"  # 替换成你的 memberId
FIELD_ID = "1462412671863504896"  # 犀浦羽毛球馆
PLACE_ID_8 = "1581847774254194688"  # 8号羽毛球 placeId
SPORT_TYPE_ID = "2"  # 羽毛球

# 时间点（本机系统时间）
TRIGGER_HOUR = 22
TRIGGER_MINUTE = 30
TRIGGER_SECOND = 0  # 精确到秒：22:30:00

# 提前突发（burst）策略（在触发前 1 秒短时间高频拉取）
BURST_ENABLED = True
BURST_START_DELTA_SECONDS = 1      # 在触发时间前多少秒开始 burst（1秒）
BURST_DURATION_SECONDS = 1.0       # burst 持续长度（秒）
BURST_INTERVAL_MIN = 0.08          # burst 最小间隔（秒）
BURST_INTERVAL_MAX = 0.12          # burst 最大间隔（秒）

# 正常轮询参数（触发后）
FETCH_INTERVAL_MIN = 0.25          # 正常轮询最小间隔（秒）
FETCH_INTERVAL_MAX = 0.6           # 正常轮询最大间隔（秒）
MAX_FETCH_ATTEMPTS_AFTER_TRIGGER = 300  # 触发后最多尝试次数（防止无限循环）

# 下单重试参数
MAX_RESERVE_ATTEMPTS = 5
RESERVE_DELAY_MIN = 0.3
RESERVE_DELAY_MAX = 1.0

# API endpoints
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
SESSIONS_LIST_URL = BASE_PREFIX + "/wechat-c/api/wechat/memberBookController/weChatSessionsList"
RESERVE_URL = BASE_PREFIX + "/business-service/orders/weChatSessionsReserve"
FIND_ORDER_URL = BASE_PREFIX + "/business-service/orders/weChatFindOrderById"

HEADERS_TEMPLATE = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "zhcg.swjtu.edu.cn",
    "Referer": "https://servicewechat.com/wx34c9f462afa158b3/27/page-frame.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 "
                  "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows",
}
# ---------------------------------------------------

def make_headers():
    h = dict(HEADERS_TEMPLATE)
    if TOKEN:
        h["token"] = TOKEN
        h["X-UserToken"] = TOKEN
    return h

def get_target_date(days_ahead=2):
    """返回后天 YYYY-MM-DD，基于本机系统日期"""
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    return d.strftime("%Y-%m-%d")

def to_midnight_ts_ms(date_str):
    """把 YYYY-MM-DD 转为本地时区当日 00:00:00 毫秒时间戳（用于 orderUseDate）"""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    ts = int(time.mktime(dt.timetuple()) * 1000)
    return ts

def fetch_sessions_for_date(date_str):
    payload = {
        "fieldId": FIELD_ID,
        "isIndoor": "",
        "placeTypeId": "",
        "searchDate": date_str,
        "sportTypeId": SPORT_TYPE_ID,
        "memberId": MEMBER_ID
    }
    try:
        r = requests.post(SESSIONS_LIST_URL, json=payload, headers=make_headers(), timeout=5)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[fetch_sessions] HTTP {r.status_code}")
            return None
    except Exception as e:
        print(f"[fetch_sessions] 异常: {e}")
        return None

def extract_20_21_session_id(resp_json, date_str):
    """
    从 weChatSessionsList 返回中提取 8号场 placeId 对应的 20:00-21:00 时段的 sessionsId
    返回单个 id 或 None
    """
    if not resp_json:
        return None
    # 返回通常是二维数组（按 opening period）
    for group in resp_json:
        if not isinstance(group, list):
            group = [group]
        for s in group:
            try:
                if (s.get("placeId") == PLACE_ID_8 and
                    s.get("openDate") == date_str and
                    s.get("openStartTime") == "20:00:00"):
                    return s.get("id")
            except Exception:
                continue
    return None

def reserve_session(session_id, date_str):
    """下单（单时段）"""
    payload = {
        "number": 1,
        "orderUseDate": str(to_midnight_ts_ms(date_str)),
        "requestsList": [{"sessionsId": session_id}],
        "fieldId": FIELD_ID,
        "fieldName": "犀浦羽毛球馆",
        "siteName": "8号羽毛球",
        "sportTypeId": SPORT_TYPE_ID,
        "sportTypeName": "羽毛球"
    }
    try:
        r = requests.post(RESERVE_URL, json=payload, headers=make_headers(), timeout=6)
        # 尽量打印详细返回
        try:
            j = r.json()
        except Exception:
            j = r.text
        return r.status_code, j
    except Exception as e:
        return None, f"exception: {e}"

def find_order(order_id):
    try:
        r = requests.get(FIND_ORDER_URL, params={"orderId": order_id}, headers=make_headers(), timeout=6)
        if r.status_code == 200:
            return r.json()
        else:
            return {"error_http": r.status_code, "text": r.text}
    except Exception as e:
        return {"exception": str(e)}

def wait_until_target(h, m, s=0):
    """阻塞等待到指定时分秒（本机系统时间），检查频率 0.2s"""
    print(f"[wait] 等待到 {h:02d}:{m:02d}:{s:02d} 开始（当前时间 {datetime.datetime.now()}）")
    while True:
        now = datetime.datetime.now()
        if now.hour == h and now.minute == m and now.second == s:
            break
        # 在接近触发点时提高检测频率（例如最后 2 秒）
        if (now.hour == h and now.minute == m and now.second >= s - 2) or \
           (now.hour == h and now.minute == m - 1 and s == 0 and now.second >= 58):
            time.sleep(0.05)
        else:
            time.sleep(0.2)
    print(f"[wait] 到点，时间：{datetime.datetime.now()}")

def burst_fetch_until_trigger(burst_start_time, burst_end_time, date_str):
    """
    在 burst 窗口内高频请求 sessions 列表以尽早拿到 sessionId。
    返回找到的 sessionId 或 None。
    """
    print(f"[burst] 启动 burst 拉取窗口 {burst_start_time} -> {burst_end_time}")
    t_end = burst_end_time
    while time.time() < t_end:
        resp = fetch_sessions_for_date(date_str)
        sid = extract_20_21_session_id(resp, date_str)
        if sid:
            print(f"[burst] 立即获取到 sessionId = {sid}（在 burst 窗口）")
            return sid
        sleep_for = random.uniform(BURST_INTERVAL_MIN, BURST_INTERVAL_MAX)
        time.sleep(sleep_for)
    return None

def normal_polling_fetch(date_str, max_attempts):
    """触发后采用正常轮询策略获取 sessionId"""
    for attempt in range(1, max_attempts + 1):
        resp = fetch_sessions_for_date(date_str)
        sid = extract_20_21_session_id(resp, date_str)
        if sid:
            print(f"[poll] 获取到 sessionId = {sid}（触发后第 {attempt} 次）")
            return sid
        sleep_for = random.uniform(FETCH_INTERVAL_MIN, FETCH_INTERVAL_MAX)
        if attempt % 10 == 0:
            print(f"[poll] 尚未获取到 (attempt {attempt})，继续等待...")
        time.sleep(sleep_for)
    return None

def try_reserve_with_retries(session_id, date_str):
    """对单个 sessionId 多次尝试下单"""
    for attempt in range(1, MAX_RESERVE_ATTEMPTS + 1):
        delay = random.uniform(RESERVE_DELAY_MIN, RESERVE_DELAY_MAX)
        time.sleep(delay)
        status, resp = reserve_session(session_id, date_str)
        print(f"[reserve attempt {attempt}] status={status} resp={resp}")
        if isinstance(resp, dict) and resp.get("code") == 200 and resp.get("orderId"):
            print(f"[reserve] 下单成功，orderId={resp.get('orderId')}")
            return resp
        # 若返回指示“已被占用/满员”等，可继续尝试（取决于后端返回）
    print("[reserve] 多次尝试未成功")
    return None

def main_run_once():
    # 校验必要配置
    if not TOKEN or not MEMBER_ID:
        print("请在脚本顶部 CONFIG 区域填写 TOKEN 和 MEMBER_ID 后重试。")
        return

    target_date = get_target_date(2)
    print(f"[main] 目标（后天）日期: {target_date}")
    # 计算 burst 窗口（基于系统 time.time()）
    trigger_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(TRIGGER_HOUR, TRIGGER_MINUTE, TRIGGER_SECOND))
    now = datetime.datetime.now()
    # 如果触发时间已过（当天已过 22:30），用于测试或次日场景需小心
    if trigger_dt < now:
        # 若本地日期与触发日的关系复杂，按当天的触发时间为准（不自动跨天）
        print(f"[main] 警告：触发时间 {trigger_dt} 已过，当前时间 {now}。请在触发前启动脚本。")
    # 等待到触发前的 burst start（若启用）
    if BURST_ENABLED:
        burst_start_time = (trigger_dt - datetime.timedelta(seconds=BURST_START_DELTA_SECONDS)).timestamp()
        # wait until burst start
        while time.time() < burst_start_time:
            time.sleep(0.05)
        # 在 burst 窗口内高频拉取直到触发或拿到 sid
        sid = burst_fetch_until_trigger(burst_start_time, burst_start_time + BURST_DURATION_SECONDS, target_date)
        # 如果在 burst 期间拿到了，就直接尝试下单
        if sid:
            reserve_resp = try_reserve_with_retries(sid, target_date)
            if reserve_resp:
                order_id = reserve_resp.get("orderId")
                if order_id:
                    time.sleep(0.8)
                    ord_info = find_order(order_id)
                    print(f"[main] 订单详情: {ord_info}")
                return
    # 如果 burst 未启用或 burst 未获得 sid，等待精确触发秒并开始常规轮询
    wait_until_target(TRIGGER_HOUR, TRIGGER_MINUTE, TRIGGER_SECOND)
    # 在触发后进行正常轮询获取 sessionId
    sid = normal_polling_fetch(target_date, MAX_FETCH_ATTEMPTS_AFTER_TRIGGER)
    if not sid:
        print("[main] 未能获取到目标 sessionId，结束本次运行。")
        return
    # 获取到 sessionId 后尝试下单（多次）
    reserve_resp = try_reserve_with_retries(sid, target_date)
    if reserve_resp and isinstance(reserve_resp, dict) and reserve_resp.get("orderId"):
        order_id = reserve_resp.get("orderId")
        time.sleep(0.8)
        ord_info = find_order(order_id)
        print(f"[main] 订单详情: {ord_info}")
    else:
        print("[main] 下单未成功，请手动检查或重试。")

if __name__ == "__main__":
    print("脚本启动：将等待并在指定时间尝试抢后天 8号 20:00-21:00 场次。")
    main_run_once()
