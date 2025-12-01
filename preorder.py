#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提前抢票脚本 (Pre-Order Mode)
策略：
1. 强制使用 HTTP Date 头来计算服务器时间偏差。
2. 忽略 NTP 和本地标准时间，完全跟随服务器的“错误”时间。
3. 适用于服务器时间比标准时间快/慢很多的情况。
"""

import requests
import time
import datetime
import json
from email.utils import parsedate_to_datetime
from config import get_selected_ids, SELECTED_CAMPUS, SELECTED_COURT_NUMBER, TOKEN, MEMBER_ID

# --------------------- CONFIG ---------------------
# TOKEN 和 MEMBER_ID 已移至 config.py

# 务必填入从 get_sid.py 获取的ID
SESSION_IDS = [
    "1985014184704745472", 
    "1985014184809603072"
] 

# 目标时间设置
TRIGGER_HOUR = 22
TRIGGER_MINUTE = 30
TRIGGER_SECOND = 0
TARGET_ARRIVAL_OFFSET = 0.05  # 目标到达时间偏移量（秒）

# API endpoints
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
RESERVE_URL = BASE_PREFIX + "/business-service/orders/weChatSessionsReserve"
TIME_CHECK_URL = BASE_PREFIX + "/wechat-c/api/wechat/memberBookController/weChatSessionsList"

HEADERS_TEMPLATE = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "zhcg.swjtu.edu.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows",
    "token": TOKEN,
    "X-UserToken": TOKEN
}

def make_headers():
    h = dict(HEADERS_TEMPLATE)
    if TOKEN:
        h["token"] = TOKEN
        h["X-UserToken"] = TOKEN
    return h

def get_target_date(days_ahead=2):
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    return d.strftime("%Y-%m-%d")

def to_midnight_ts_ms(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    ts = int(time.mktime(dt.timetuple()) * 1000)
    return ts

def parse_http_date(date_str):
    """把 HTTP Date (RFC-1123) 转为毫秒时间戳"""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return None

def sync_time_with_http_date(session):
    """
    强制使用 HTTP Date 头计算时间偏差
    """
    print("[sync] 正在通过 HTTP Date 校准服务器时间...")
    deltas = []
    latencies = []
    
    payload = {
        "fieldId": "0", # 这里的ID不重要，只要能触发请求即可
        "searchDate": datetime.date.today().strftime("%Y-%m-%d"),
        "sportTypeId": "2",
        "memberId": MEMBER_ID
    }

    for i in range(5):
        try:
            t_start = time.time()
            resp = session.post(TIME_CHECK_URL, json=payload, headers=make_headers(), timeout=5)
            t_end = time.time()
            
            latency = (t_end - t_start) / 2.0
            latencies.append(latency)
            
            server_date_str = resp.headers.get('Date')
            if server_date_str:
                server_ts = parse_http_date(server_date_str)
                if server_ts:
                    # 粗略计算：假设服务器时间在 t_end - latency 时刻是 server_ts
                    # 由于 HTTP Date 只有秒级精度，我们加 0.5s 平均误差
                    estimated_server_time = server_ts + 0.5
                    delta = estimated_server_time - (t_end - latency)
                    deltas.append(delta)
                    print(f"  [sample {i+1}] Server Date: {server_date_str} -> Delta: {delta:.2f}s")
            
            time.sleep(0.5)
        except Exception as e:
            print(f"  [sample {i+1}] 异常: {e}")

    if not deltas:
        print("[ERROR] 无法获取服务器时间！")
        return 0, 0.05

    # 剔除最大最小值
    if len(deltas) > 2:
        deltas.sort()
        avg_delta = sum(deltas[1:-1]) / (len(deltas) - 2)
        latencies.sort()
        avg_latency = sum(latencies[1:-1]) / (len(latencies) - 2)
    else:
        avg_delta = sum(deltas) / len(deltas)
        avg_latency = sum(latencies) / len(latencies)

    print(f"[sync] 校准完成。服务器比本地 {'快' if avg_delta > 0 else '慢'} {abs(avg_delta):.2f}s")
    print(f"[sync] 这意味着当本地时间为 22:30 - {abs(avg_delta):.2f}s 时，服务器已经是 22:30 了！")
    
    return avg_delta, avg_latency

def main():
    # 校验必要配置
    try:
        FIELD_ID, PLACE_ID = get_selected_ids()
    except ValueError as e:
        print(f"[错误] {e}")
        return

    if not TOKEN or not SESSION_IDS:
        print("请在脚本顶部 CONFIG 区域填写 TOKEN 和 SESSION_IDS 后重试。")
        return

    target_date_str = get_target_date(2)
    print(f"[main] 目标（后天）日期: {target_date_str}")
    print(f"[main] 使用 sessionIds: {SESSION_IDS}")
    print(f"[main] 目标校区: {SELECTED_CAMPUS}, 场地: {SELECTED_COURT_NUMBER}号")

    session = requests.Session()
    print("[main] 正在预热连接...")
    session.get("https://zhcg.swjtu.edu.cn", headers=make_headers(), timeout=5)

    # 关键：使用 HTTP Date 校准
    time_delta, avg_latency = sync_time_with_http_date(session)
    
    # 计算发射时间
    now = datetime.datetime.now()
    target_time = datetime.datetime.combine(now.date(), datetime.time(TRIGGER_HOUR, TRIGGER_MINUTE, TRIGGER_SECOND))
    target_ts = target_time.timestamp()
    
    # 公式：发射时间 = 目标时间 + 缓冲 - 偏差 - 延迟
    # 如果服务器快 223s (delta = 223)，那么发射时间 = 22:30 - 223s ...
    fire_ts = target_ts + TARGET_ARRIVAL_OFFSET - time_delta - avg_latency
    fire_dt = datetime.datetime.fromtimestamp(fire_ts)
    
    print(f"[main] 目标服务器时间: {target_time} + {TARGET_ARRIVAL_OFFSET}s")
    print(f"[main] 预计发射时间 (本地): {fire_dt.strftime('%H:%M:%S.%f')}")
    
    if fire_ts < time.time():
        print("[ERROR] 计算出的发射时间已过！(可能服务器快太多了，或者已经过了抢票点)")
        return

    # 构造 Payload
    requests_list = [{"sessionsId": sid} for sid in SESSION_IDS]
    payload = {
        "number": len(requests_list),
        "orderUseDate": to_midnight_ts_ms(target_date_str),
        "requestsList": requests_list,
        "fieldId": FIELD_ID,
        "fieldName": "犀浦室内羽毛球馆" if SELECTED_CAMPUS == 'xipu' else "九里室内羽毛球馆",
        "siteName": f"{SELECTED_COURT_NUMBER}号羽毛球",
        "sportTypeId": "2",
        "sportTypeName": "羽毛球"
    }

    print("[main] 进入倒计时...")
    while True:
        t = time.time()
        if t >= fire_ts:
            break
        remaining = fire_ts - t
        if remaining > 1:
            time.sleep(0.5)
            print(f"\r倒计时: {remaining:.1f}s", end="")
        else:
            pass

    print(f"\n[FIRE] 发射! {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
    try:
        r = session.post(RESERVE_URL, json=payload, headers=make_headers(), timeout=5)
        print(f"[RESULT] 状态码: {r.status_code}")
        print(f"[RESULT] 响应: {r.text}")
    except Exception as e:
        print(f"[ERROR] 请求异常: {e}")

if __name__ == "__main__":
    print("提前抢票模式启动 (Pre-Order Mode)...")
    main()
