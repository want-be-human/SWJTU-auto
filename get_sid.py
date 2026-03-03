#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专用于获取 sessionId 的脚本
用于获取后天指定场地的目标时段 sessionId
"""

import requests
import datetime
from config import get_selected_ids, SELECTED_CAMPUS, SELECTED_COURT_NUMBER
from refresh_token import get_auth, need_login, validate_token

# --------------------- CONFIG ---------------------
# TOKEN / MEMBER_ID 已改为运行时动态获取（auth.py）

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
    a = get_auth()
    h = dict(HEADERS_TEMPLATE)
    h["token"] = a.token
    h["X-UserToken"] = a.token
    h["x-usertoken"] = a.token
    return h

def get_target_date(days_ahead=2):
    """返回后天 YYYY-MM-DD，基于本机系统日期"""
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    return d.strftime("%Y-%m-%d")

def fetch_sessions_for_date(date_str, max_retries=3):
    auth = get_auth()
    payload = {
        "fieldId": FIELD_ID,
        "isIndoor": "",
        "placeTypeId": "",
        "searchDate": date_str,
        "sportTypeId": SPORT_TYPE_ID,
        "memberId": auth.user_id
    }
    for retry in range(max_retries):
        try:
            r = requests.post(SESSIONS_LIST_URL, json=payload, headers=make_headers(), timeout=5)
            if r.status_code == 200:
                return r.json()

            # token 过期检测
            try:
                resp_json = r.json()
            except Exception:
                resp_json = r.text
            if need_login(r.status_code, resp_json if isinstance(resp_json, dict) else {}):
                print("[ERROR] token 已失效！请先运行 refresh_token.py 刷新后再重新启动本脚本。")
                print("  python refresh_token.py")
                return None

            print(f"[fetch_sessions] HTTP {r.status_code} {r.text}")
            return None
        except Exception as e:
            print(f"[fetch_sessions] 异常: {e}")
            return None
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
    # 验证 token 可用
    auth = get_auth()
    print(f"[get_sid] 当前 token: {auth.token[:8]}...  userId: {auth.user_id}")
    print("[get_sid] 正在验证 token 是否有效…")
    if not validate_token(auth.token, auth.user_id):
        print("[ERROR] token 已过期！请先运行 refresh_token.py 刷新 token 后再启动本脚本。")
        print("  python refresh_token.py")
        return
    print("[OK] token 验证通过。")

    target_date = get_target_date(2)
    print(f"[get_sid] 目标（后天）日期: {target_date}")
    print(f"[get_sid] 正在为校区 '{SELECTED_CAMPUS}' 的 {SELECTED_COURT_NUMBER} 号场地获取Session ID")
    
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
        print("[get_sid] 请将需要的 sessionId 复制到 config.py 中的 SESSION_IDS 列表")
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