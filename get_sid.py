#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专用于获取 sessionId 的脚本
用于获取后天 8号羽毛球 20:00-21:00 时段的 sessionId
"""

import requests
import datetime
from config import get_selected_ids, SELECTED_CAMPUS, SELECTED_COURT_NUMBER

# --------------------- CONFIG ---------------------
TOKEN = "f7d9e4c8-176e-4609-9628-5f245571cc93"
MEMBER_ID = "1697570245594587136"  # 替换成你的 memberId

# 从配置文件获取场地ID
try:
    FIELD_ID, PLACE_ID = get_selected_ids()
except ValueError as e:
    print(f"[错误] {e}")
    exit()

SPORT_TYPE_ID = "2"  # 羽毛球
TIME1 = "19:00:00"
TIME2 = "20:00:00"
TIME3 = "21:00:00"

# API endpoints
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
SESSIONS_LIST_URL = BASE_PREFIX + "/wechat-c/api/wechat/memberBookController/weChatSessionsList"

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
            print(f"[fetch_sessions] HTTP {r.status_code} {r.text}")
            return None
    except Exception as e:
        print(f"[fetch_sessions] 异常: {e}")
        return None

def extract_target_session_ids(resp_json, date_str):
    """
    从 weChatSessionsList 返回中提取指定场地的目标时段的 sessionsId
    返回字典格式：{"19:00-20:00": id, "20:00-21:00": id, "21:00-22:00": id}，未找到的为 None
    """
    result = {"19:00-20:00": None, "20:00-21:00": None, "21:00-22:00": None}
    
    if not resp_json:
        return result
    
    # 返回通常是二维数组（按 opening period）
    for group in resp_json:
        if not isinstance(group, list):
            group = [group]
        for s in group:
            try:
                if (s.get("placeId") == PLACE_ID and s.get("openDate") == date_str):
                    start_time = s.get("openStartTime")
                    if start_time == TIME1:
                        result["19:00-20:00"] = s.get("id")
                    elif start_time == TIME2:
                        result["20:00-21:00"] = s.get("id")
                    elif start_time == TIME3:
                        result["21:00-22:00"] = s.get("id")
            except Exception:
                continue
    
    return result

def main():
    # 校验必要配置
    if not TOKEN or not MEMBER_ID:
        print("请在脚本顶部 CONFIG 区域填写 TOKEN 和 MEMBER_ID 后重试。")
        return

    target_date = get_target_date(2)
    print(f"[get_sid] 目标（后天）日期: {target_date}")
    print(f"[get_sid] 正在为校区 '{SELECTED_CAMPUS}' 的 {SELECTED_COURT_NUMBER} 号场地获取Session ID")
    print(f"[get_sid] 使用 Token: {TOKEN[:20]}...")  # 只显示前20个字符保护隐私
    
    # 获取 sessions 列表
    print("[get_sid] 正在获取 sessions 列表...")
    resp = fetch_sessions_for_date(target_date)
    
    if not resp:
        print("[get_sid] 无法获取 sessions 数据")
        print("[get_sid] 可能原因：Token 已过期、网络问题或服务器错误")
        return
    
    # 提取目标 sessionId
    session_ids = extract_target_session_ids(resp, target_date)
    
    print("[get_sid] 获取结果：")
    for time_slot, sid in session_ids.items():
        if sid:
            print(f"  {time_slot}: {sid}")
        else:
            print(f"  {time_slot}: 未找到")
    
    # 检查是否至少找到一个
    found_any = any(sid for sid in session_ids.values())
    
    if found_any:
        print("[get_sid] 请将需要的 sessionId 复制到主文件 auto-two.py 中的 SESSION_ID 常量")
        print("[get_sid] 如果要抢 19:00-20:00，使用第一个 sessionId")
        print("[get_sid] 如果要抢 20:00-21:00，使用第二个 sessionId")
        print("[get_sid] 如果要抢 21:00-22:00，使用第三个 sessionId")
    else:
        print("[get_sid] 未找到任何目标时段的 sessionId")
        print("[get_sid] 可能原因：")
        print("  - 目标日期尚未开放预订")
        print(f"  - {SELECTED_CAMPUS} 校区 {SELECTED_COURT_NUMBER} 号场地目标时段不可用")
        print("  - 网络或权限问题")

if __name__ == "__main__":
    print("获取 sessionId 脚本启动...")
    main()