#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用于查询指定日期的场地信息的脚本
"""

import requests
import datetime
import json
import re
from config import XIPU_FIELDID, JIULI_FIELDID, XIPU_PLACEID, JIULI_PLACEID
from refresh_token import get_auth

# --------------------- CONFIG ---------------------
SPORT_TYPE_ID = "2"  # 羽毛球

# API endpoint
SESSIONS_LIST_URL = "https://zhcg.swjtu.edu.cn/onesports-gateway/wechat-c/api/wechat/memberBookController/weChatSessionsList"

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

def get_default_date(days_ahead=2):
    """返回默认查询日期（后天） YYYY-MM-DD"""
    return (datetime.date.today() + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def fetch_venue_info(date_str, field_id, place_id=None, start_time_filters=None):
    """获取指定日期的场地信息"""
    auth = get_auth()
    payload = {
        "fieldId": field_id,
        "isIndoor": "",
        "placeTypeId": "",
        "searchDate": date_str,
        "sportTypeId": SPORT_TYPE_ID,
        "memberId": auth.user_id
    }
    
    print(f"\n[INFO] 正在查询日期: {date_str}")
    print(f"[INFO] 请求 URL: {SESSIONS_LIST_URL}")
    
    try:
        r = requests.post(SESSIONS_LIST_URL, json=payload, headers=make_headers(), timeout=10)
        
        # print(f"[INFO] HTTP 状态码: {r.status_code}")
        
        if r.status_code == 200:
            try:
                response_data = r.json()
                print("[SUCCESS] 成功获取场地信息 (仅显示匹配项的详细信息):")
                filter_and_print_results(response_data, place_id, start_time_filters)
                return response_data
            except json.JSONDecodeError:
                print("[ERROR] 无法解析返回的 JSON 数据。")
                print("原始返回内容:", r.text)
                return None
        else:
            print(f"[ERROR] 请求失败。")
            print("返回内容:", r.text)
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"[FATAL] 请求发生异常: {e}")
        return None

def filter_and_print_results(data, place_id, start_time_filters):
    """根据场地ID和时间过滤并打印结果"""
    if not data:
        print("  -> 无数据可供分析。")
        return

    found_any = False
    for group in data:
        if not isinstance(group, list):
            group = [group]
        for session in group:
            match_place = (not place_id) or (session.get("placeId") == place_id)
            match_time = (not start_time_filters) or (session.get("openStartTime") in start_time_filters)

            if match_place and match_time:
                found_any = True
                print("-" * 30)
                filtered_session = {
                    # "id": session.get("id"),
                    "openDate": session.get("openDate"),
                    # "sessionPrice": session.get("sessionPrice"),
                    "placeName": session.get("placeName"),
                    "openStartTime": session.get("openStartTime"),                 
                    "sessionsStatus": session.get("sessionsStatus")
                }
                print(json.dumps(filtered_session, indent=4, ensure_ascii=False))
    
    if not found_any:
        print("  -> 未找到符合条件的场地信息。")


def main():
    """主函数"""
    print("--- 场地信息查询工具 ---")
    
    # 获取日期
    default_date = get_default_date(2)
    user_date = input(f"请输入要查询的日期 (格式 YYYY-MM-DD, 默认: {default_date}): ").strip()
    search_date = user_date if user_date else default_date
    try:
        datetime.datetime.strptime(search_date, "%Y-%m-%d")
    except ValueError:
        print("[ERROR] 日期格式不正确，请输入 YYYY-MM-DD 格式的日期。")
        return

    # 获取校区
    user_campus = input("请输入校区 (xipu/jiuli, 默认: xipu): ").strip().lower()
    campus = user_campus if user_campus in ['xipu', 'jiuli'] else 'xipu'
    
    field_id = XIPU_FIELDID if campus == 'xipu' else JIULI_FIELDID
    place_ids_map = XIPU_PLACEID if campus == 'xipu' else JIULI_PLACEID

    # 获取场地号
    user_court_num_str = input(f"请输入场地号 (例如: 6, 留空则查询所有场地): ").strip()
    place_id_filter = None
    if user_court_num_str:
        try:
            court_num = int(user_court_num_str)
            place_id_filter = place_ids_map.get(court_num)
            if not place_id_filter:
                print(f"[ERROR] 在 {campus} 校区未找到编号为 {court_num} 的场地。")
                return
        except ValueError:
            print("[ERROR] 场地号必须是数字。")
            return

    # 获取时间
    user_time_hour_str = input("请输入开始时间的小时 (例如: 19,20, 留空则查询所有时间): ").strip()
    start_time_filters = []
    if user_time_hour_str:
        # 支持逗号、中文逗号、空格分隔
        parts = re.split(r'[,\s，]+', user_time_hour_str)
        for part in parts:
            if not part:
                continue
            try:
                hour = int(part)
                if 0 <= hour <= 23:
                    start_time_filters.append(f"{hour:02d}:00:00")
                else:
                    print(f"[WARN] 小时 {hour} 不在 0-23 之间，已忽略。")
            except ValueError:
                print(f"[WARN] '{part}' 不是有效的数字，已忽略。")
        
    fetch_venue_info(search_date, field_id, place_id_filter, start_time_filters)

if __name__ == "__main__":
    main()
