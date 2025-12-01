#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
狙击手版：精准单次请求抢票脚本
策略：
1. 自动校准时间：通过 Response Header 的 Date 字段计算本地与服务器的时间差。
2. 保持连接 (Keep-Alive)：使用 requests.Session() 复用 TCP 连接，降低握手延迟。
3. 动态发射：根据网络延迟 (RTT) 动态计算发射时间，确保请求在 22:30:00.050 左右到达服务器。
4. 单发必中：只发送一次请求，避免触发“请勿重复请求”的限制。
"""

import requests
import time
import datetime
import json
from email.utils import parsedate_to_datetime
from config import get_selected_ids, SELECTED_CAMPUS, SELECTED_COURT_NUMBER

# --------------------- CONFIG ---------------------
TOKEN = "f7d9e4c8-176e-4609-9628-5f245571cc93"
MEMBER_ID = "1697570245594587136"  # 你的 memberId（脚本里不发送到下单接口）

# 从配置文件获取场地ID
try:
    FIELD_ID, PLACE_ID = get_selected_ids()
except ValueError as e:
    print(f"[错误] {e}")
    exit()

SPORT_TYPE_ID = "2"  # 羽毛球

# -----------------从 get_sid.py 获取-----------------
# 运行 get_sid.py 脚本后，将打印出的 session ID 粘贴到这里
SESSION_IDS = [
     "1985014184704745472", 
    "1985014184809603072"
] 
# ---------------------------------------------------

# 目标时间设置
TRIGGER_HOUR = 20
TRIGGER_MINUTE = 54
TRIGGER_SECOND = 0
TARGET_ARRIVAL_OFFSET = 0.05  # 目标到达时间偏移量（秒），即希望请求在 22:30:00.050 到达

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

def sync_time(session):
    """
    计算本地时间与服务器时间的差值 (delta) 和网络延迟 (latency)
    delta = 服务器时间 - 本地时间
    """
    print("[sync] 正在校准时间...")
    deltas = []
    latencies = []
    
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
            
            server_date_str = resp.headers.get('Date')
            if server_date_str:
                server_ts = parse_http_date(server_date_str)
                # 服务器时间是收到请求并处理完的时间，近似等于 t_end - latency
                # 但 HTTP Date 只精确到秒，所以这种计算有误差，我们主要用它来对齐秒级
                # 更精确的做法是假设服务器时间在 t_start + latency 时刻是 server_ts
                # 但由于 server_ts 是整秒，我们取中间值优化
                
                # 这里我们采用一种简化的策略：
                # 假设 HTTP Date 变化的那一瞬间，就是该秒的开始。
                # 但由于我们无法捕捉那一瞬间，我们只能粗略计算。
                
                # 更好的策略：直接计算差值
                # 假设服务器返回的 Date 是 T_server (秒)
                # 本地当前时间是 T_local (秒)
                # 差值 = T_server - T_local
                # 但 T_server 是截断的整秒，这会导致最大 1秒的误差。
                
                # 鉴于 HTTP Date 精度低，我们主要用它来判断本地时间是否快/慢了整秒数
                # 毫秒级的对齐依赖于假设本地时钟走速准确，只差一个固定的 offset
                
                # 修正策略：
                # 我们信任本地时间的毫秒部分，只用服务器时间修正“秒”级的偏差。
                # 除非偏差巨大，否则我们认为本地时间的相对流逝是准的。
                
                # 实际上，对于抢票，最重要的是“相对服务器的 22:30:00”。
                # 如果本地时间是 22:29:59.500，服务器认为是 22:30:00.500，那我们就晚了 1秒。
                
                # 计算 delta:
                # 估算服务器响应时的精确时间 = server_ts (但这只是整秒)
                # 实际上，如果服务器返回 12:40:37，那么真实时间在 12:40:37.000 到 12:40:37.999 之间。
                # 平均取 12:40:37.500
                
                if server_ts is not None:
                    estimated_server_time = server_ts + 0.5 
                    delta = estimated_server_time - (t_end - latency) # 粗略偏差
                    
                    deltas.append(delta)
                    latencies.append(latency)
                    print(f"  [sample {i+1}] Latency: {latency*1000:.1f}ms, Server Date: {server_date_str}")
                else:
                    print(f"  [sample {i+1}] 无法解析服务器时间")
            else:
                print(f"  [sample {i+1}] 响应头中没有 Date 字段")
                
            time.sleep(0.5)
        except Exception as e:
            print(f"  [sample {i+1}] 异常: {e}")

    if not deltas:
        print("[sync] 无法获取服务器时间，将使用本地时间。")
        return 0, 0.05 # 默认延迟 50ms

    # 剔除最大最小值，取平均
    if len(deltas) > 2:
        deltas.sort()
        avg_delta = sum(deltas[1:-1]) / (len(deltas) - 2)
        latencies.sort()
        avg_latency = sum(latencies[1:-1]) / (len(latencies) - 2)
    else:
        avg_delta = sum(deltas) / len(deltas)
        avg_latency = sum(latencies) / len(latencies)

    print(f"[sync] 时间校准完成。本地比服务器 {'慢' if avg_delta > 0 else '快'} {abs(avg_delta):.3f}s")
    print(f"[sync] 平均单向延迟 (Latency): {avg_latency*1000:.1f}ms")
    
    return avg_delta, avg_latency

def main_sniper():
    # 校验必要配置
    if not TOKEN or not SESSION_IDS:
        print("请在脚本顶部 CONFIG 区域填写 TOKEN 和 SESSION_IDS 后重试。")
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
