#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动定点抢：后天 8号羽毛球场次（每天 22:30:00 精确触发）
支持同时抢多个时间段，使用硬编码的 sessionId，在触发前 1 秒开始持续下单
"""

import requests
import time
import datetime

# --------------------- CONFIG ---------------------
TOKEN = "c1fd08b5-d49a-47b2-afaa-be66b4078274"
MEMBER_ID = "1697570245594587136"  # 替换成你的 memberId
FIELD_ID = "1462412671863504896"  # 犀浦羽毛球馆
PLACE_ID_8 = "1581847774254194688"  # 8号羽毛球 placeId
SPORT_TYPE_ID = "2"  # 羽毛球

# 硬编码的 sessionId（从 get_sid.py 获取）
# 可以设置单个 sessionId 或多个 sessionId 列表
SESSION_IDS = [
    "1959284626974318592",  # 20:00-21:00 时段
    "1959284627087564800",  # 21:00-22:00 时段（取消注释以同时抢两个时段）
]

# 时间点（本机系统时间）
TRIGGER_HOUR = 22
TRIGGER_MINUTE = 30
TRIGGER_SECOND = 0  # 精确到秒：22:30:00

# 下单策略：在触发前 1 秒开始持续下单
RESERVE_START_DELTA_SECONDS = 1    # 在触发时间前多少秒开始下单（1秒）
RESERVE_INTERVAL = 0.08            # 下单间隔（秒）
MAX_RESERVE_ATTEMPTS = 200         # 最大下单尝试次数

# API endpoints
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
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

def reserve_session(session_ids, date_str):
    """下单（支持单个或多个时段）。注意：orderUseDate 为整数毫秒时间戳"""
    # 确保 session_ids 是列表格式
    if isinstance(session_ids, str):
        session_ids = [session_ids]
    
    # 构建 requestsList
    requests_list = [{"sessionsId": sid} for sid in session_ids]
    
    payload = {
        "number": 1,
        "orderUseDate": to_midnight_ts_ms(date_str),   # 整数（毫秒）
        "requestsList": requests_list,
        "fieldId": FIELD_ID,
        "fieldName": "犀浦羽毛球7-9号",
        "siteName": "8号羽毛球",
        "sportTypeId": SPORT_TYPE_ID,
        "sportTypeName": "羽毛球"
    }
    try:
        r = requests.post(RESERVE_URL, json=payload, headers=make_headers(), timeout=6)
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

def main_run_once():
    # 校验必要配置
    if not TOKEN or not MEMBER_ID or not SESSION_IDS:
        print("请在脚本顶部 CONFIG 区域填写 TOKEN、MEMBER_ID 和 SESSION_IDS 后重试。")
        return

    target_date = get_target_date(2)
    print(f"[main] 目标（后天）日期: {target_date}")
    print(f"[main] 使用 sessionIds: {SESSION_IDS}")
    if len(SESSION_IDS) > 1:
        print(f"[main] 将同时抢 {len(SESSION_IDS)} 个时间段")
    
    # 计算开始下单的时间（触发前 1 秒）
    trigger_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(TRIGGER_HOUR, TRIGGER_MINUTE, TRIGGER_SECOND))
    reserve_start_dt = trigger_dt - datetime.timedelta(seconds=RESERVE_START_DELTA_SECONDS)
    reserve_start_time = reserve_start_dt.timestamp()
    
    now = datetime.datetime.now()
    if trigger_dt < now:
        print(f"[main] 警告：触发时间 {trigger_dt} 已过，当前时间 {now}。请在触发前启动脚本。")
    
    print(f"[main] 将在 {reserve_start_dt} 开始持续下单")
    
    # 等待到开始下单时间
    while time.time() < reserve_start_time:
        time.sleep(0.05)
    
    print(f"[main] 开始持续下单，时间：{datetime.datetime.now()}")
    
    # 持续下单直到成功或已被占用
    for attempt in range(1, MAX_RESERVE_ATTEMPTS + 1):
        status, resp = reserve_session(SESSION_IDS, target_date)
        print(f"[reserve attempt {attempt}] status={status} resp={resp}")
        
        # 成功下单
        if isinstance(resp, dict) and resp.get("code") == 200 and resp.get("orderId"):
            print(f"[reserve] 下单成功，orderId={resp.get('orderId')}")
            order_id = resp.get("orderId")
            time.sleep(0.8)
            ord_info = find_order(order_id)
            print(f"[main] 订单详情: {ord_info}")
            return
        
        # 已被占用，停止尝试
        if isinstance(resp, dict) and resp.get("code") == 201:
            print("[reserve] 场次已被占用，停止尝试")
            return
        
        # 重复请求错误，停止尝试
        if status == 400 and isinstance(resp, dict) and "请勿重复请求" in (resp.get("message") or ""):
            print("[reserve] 服务器提示重复请求，停止尝试")
            return
        
        # 继续下一次尝试
        if attempt < MAX_RESERVE_ATTEMPTS:
            time.sleep(RESERVE_INTERVAL)
    
    print("[main] 达到最大尝试次数，下单未成功")

if __name__ == "__main__":
    print("脚本启动：将等待并在指定时间尝试抢后天 8号场次。")
    if len(SESSION_IDS) > 1:
        print(f"同时抢 {len(SESSION_IDS)} 个时间段")
    main_run_once()