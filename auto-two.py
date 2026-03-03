#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
狙击手版：精准单次请求抢票脚本
策略：
1. 自动校准时间：NTP 校准本地与标准时间差。
2. 保持连接 (Keep-Alive)：使用 requests.Session() 复用 TCP 连接，降低握手延迟。
3. 动态发射：根据网络延迟 (RTT) 动态计算发射时间。
4. 单发必中：只发送一次请求，避免触发“请勿重复请求”的限制。
"""

import requests
import time
import datetime
import socket
import struct
from email.utils import parsedate_to_datetime
from config import (get_selected_ids, SELECTED_CAMPUS, SELECTED_COURT_NUMBER,
                    SESSION_IDS, TOKEN, MEMBER_ID)

# 从配置文件获取场地ID
try:
    FIELD_ID, PLACE_ID = get_selected_ids()
except ValueError as e:
    print(f"[错误] {e}")
    exit()

SPORT_TYPE_ID = "2"  # 羽毛球

# 目标时间设置
TRIGGER_HOUR = 22
TRIGGER_MINUTE = 30
TRIGGER_SECOND = 0
TARGET_ARRIVAL_OFFSET = 0.05  # 目标到达时间偏移量（秒），即希望请求在 22:30:00.050 到达

# 手动时间修正 (秒) - 作为 NTP 失败时的备选
MANUAL_OFFSET = 0.7 

# API endpoints
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
RESERVE_URL = BASE_PREFIX + "/business-service/orders/weChatSessionsReserve"
# 使用 sessionsList 接口来获取服务器时间，因为它响应快且无副作用
TIME_CHECK_URL = BASE_PREFIX + "/wechat-c/api/wechat/memberBookController/weChatSessionsList"

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

def parse_http_date(date_str):
    """把 HTTP Date (RFC-1123) 转为毫秒时间戳"""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return None

def get_ntp_offset(server="ntp.aliyun.com"):
    """
    通过 NTP 协议获取本地时间与标准时间的偏差 (秒)
    返回: delta (标准时间 - 本地时间)
    """
    TIME1970 = 2208988800
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(3)
    data = b'\x1b' + 47 * b'\0'
    
    try:
        # 记录发送时间 t1
        t1 = time.time()
        client.sendto(data, (server, 123))
        data, address = client.recvfrom(1024)
        # 记录接收时间 t4
        t4 = time.time()
        
        if data:
            unpacked = struct.unpack('!12I', data)
            # t2: 服务器接收时间
            t2 = unpacked[8] - TIME1970 + float(unpacked[9]) / 2**32
            # t3: 服务器发送时间
            t3 = unpacked[10] - TIME1970 + float(unpacked[11]) / 2**32
            
            # NTP 偏移量公式: offset = ((t2 - t1) + (t3 - t4)) / 2
            offset = ((t2 - t1) + (t3 - t4)) / 2
            return offset
    except Exception as e:
        print(f"[NTP] 校准失败: {e}")
        return None
    finally:
        client.close()

def sync_time(session):
    """
    计算本地时间与服务器时间的差值 (delta) 和网络延迟 (latency)
    delta = 服务器时间 - 本地时间
    """
    print("[sync] 正在校准时间...")
    deltas = []
    latencies = []
    
    # 1. 先通过 NTP 获取精确的时间偏差 (替代 time.is)
    print("[sync] 正在连接 NTP 服务器 (ntp.aliyun.com) 自动计算时间偏差...")
    ntp_offset = get_ntp_offset()
    
    if ntp_offset is not None:
        avg_delta = ntp_offset
        print(f"[sync] NTP 校准成功。本地比标准时间 {'慢' if avg_delta > 0 else '快'} {abs(avg_delta):.3f}s")
    else:
        avg_delta = MANUAL_OFFSET
        print(f"[sync] NTP 校准失败，回退使用手动偏移量: {avg_delta}s")

    # 2. 测量与学校服务器的网络延迟
    print("[sync] 正在测量与学校服务器的网络延迟...")
    # 构造一个轻量级的 payload 用于时间查询
    payload = {
        "fieldId": FIELD_ID,
        "searchDate": datetime.date.today().strftime("%Y-%m-%d"), # 查询今天的即可
        "sportTypeId": SPORT_TYPE_ID,
        "memberId": MEMBER_ID
    }

    for i in range(5): # 采样5次
        try:
            t_start = time.time()
            resp = session.post(TIME_CHECK_URL, json=payload, headers=make_headers(), timeout=5)
            t_end = time.time()
            
            latency = (t_end - t_start) / 2.0 # 单向延迟估算
            latencies.append(latency)
            print(f"  [sample {i+1}] Latency: {latency*1000:.1f}ms")
                
            time.sleep(0.2)
        except Exception as e:
            print(f"  [sample {i+1}] 异常: {e}")

    # 剔除最大最小值，取平均
    if len(latencies) > 2:
        latencies.sort()
        avg_latency = sum(latencies[1:-1]) / (len(latencies) - 2)
    elif latencies:
        avg_latency = sum(latencies) / len(latencies)
    else:
        avg_latency = 0.05 # 默认延迟 50ms

    print(f"[sync] 平均单向延迟 (Latency): {avg_latency*1000:.1f}ms")
    
    return avg_delta, avg_latency

def main_sniper():
    # 校验必要配置
    if not TOKEN:
        print("请在配置文件 config.py 的 TOKEN 变量中填写有效的 token 后重试。")
        return
    if not SESSION_IDS:
        print("请先运行 get_sid.py 获取目标时段的 sessionId，并将其填入脚本的 SESSION_IDS 列表后重试。")
        return

    target_date_str = get_target_date(2)
    print(f"[main] 目标（后天）日期: {target_date_str}")
    print(f"[main] 使用 sessionIds: {SESSION_IDS}")
    print(f"[main] 目标校区: {SELECTED_CAMPUS}, 场地: {SELECTED_COURT_NUMBER}号")

    # 初始化 Session
    session = requests.Session()
    # 预热连接
    print("[main] 正在预热连接...")
    session.get("https://zhcg.swjtu.edu.cn", headers=make_headers(), timeout=5)

    # 时间校准
    time_delta, avg_latency = sync_time(session)
    
    # 计算目标触发时间
    # 目标是：请求到达服务器的时间 = 22:30:00 + 0.05s
    # 发射时间 = 目标到达时间 - 单向延迟 - 本地与服务器的时间差
    
    now = datetime.datetime.now()
    target_time = datetime.datetime.combine(now.date(), datetime.time(TRIGGER_HOUR, TRIGGER_MINUTE, TRIGGER_SECOND))
    target_ts = target_time.timestamp()
    
    # 修正后的发射时间戳
    # 本地时间 + delta = 服务器时间
    # => 本地时间 = 服务器时间 - delta
    # 我们希望 服务器时间 = target_ts + TARGET_ARRIVAL_OFFSET
    # 所以 本地发射时间 = (target_ts + TARGET_ARRIVAL_OFFSET) - delta - avg_latency
    
    fire_ts = target_ts + TARGET_ARRIVAL_OFFSET - time_delta - avg_latency
    fire_dt = datetime.datetime.fromtimestamp(fire_ts)
    
    print(f"[main] 目标服务器时间: {target_time} + {TARGET_ARRIVAL_OFFSET}s")
    print(f"[main] 预计发射时间 (本地): {fire_dt.strftime('%H:%M:%S.%f')}")
    
    if fire_ts < time.time():
        print("[ERROR] 目标时间已过！请检查系统时间或脚本启动时间。")
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
        "sportTypeId": SPORT_TYPE_ID,
        "sportTypeName": "羽毛球"
    }

    # 倒计时等待
    print("[main] 进入倒计时...")
    while True:
        t = time.time()
        if t >= fire_ts:
            break
        # 剩余时间大于 1秒时 sleep，小于 1秒时忙等待以提高精度
        remaining = fire_ts - t
        if remaining > 1:
            time.sleep(0.5)
        else:
            pass # 忙等待

    # --- FIRE ---
    print(f"[FIRE] 发射! {datetime.datetime.now().strftime('%H:%M:%S.%f')}")
    try:
        r = session.post(RESERVE_URL, json=payload, headers=make_headers(), timeout=5)
        print(f"[RESULT] 状态码: {r.status_code}")
        print(f"[RESULT] 响应: {r.text}")
        
        try:
            resp_json = r.json()
            if resp_json.get("code") == 200 and resp_json.get("orderId"):
                print(f"\n>>> 抢票成功! 订单号: {resp_json.get('orderId')} <<<")
            elif "请勿重复请求" in str(resp_json):
                print("\n[失败] 触发了重复请求限制 (可能之前有请求已到达)")
            else:
                print(f"\n[失败] {resp_json.get('message', '未知错误')}")
        except:
            pass
            
    except Exception as e:
        print(f"[ERROR] 请求异常: {e}")

if __name__ == "__main__":
    print("狙击手模式启动...")
    main_sniper()
