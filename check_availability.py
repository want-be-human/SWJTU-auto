#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 TOKEN 是否有效的轻量脚本。

行为调整：
- 优先使用文件顶部的全局 `TOKEN` 常量（编辑此文件以把 token 写入脚本）。
- 如果全局 `TOKEN` 为空，仍可通过 --token 参数或环境变量传入。
- 不再需要 memberId；payload 中不会发送 memberId 字段。

用法示例（PowerShell）：
& .\.venv\Scripts\python.exe .\check_availability.py
或覆盖 token：
& .\.venv\Scripts\python.exe .\check_availability.py --token YOUR_TOKEN
"""
from dataclasses import field
import requests
import datetime
import argparse
import os
import sys
from typing import Tuple, Any
from typing import List, Dict

# Avoid importing TOKEN and FIELD_ID because they are defined as constants later in this script,
# importing them would be shadowed by the subsequent assignments below.

TOKEN = "ad6561ef-71ac-4102-bafe-4fbecaeecbc5"
# 默认要检查的 placeId 与 sessions（可根据需要修改）
FIELD_ID = "1462412671863504896" 
SESSION_IDS_TO_CHECK: List[str] = [
    "1972692986104913920",  # 20:00-21:00
    "1972692986201382912"   # 21:00-22:00
]
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
SESSIONS_LIST_URL = BASE_PREFIX + "/wechat-c/api/wechat/memberBookController/weChatSessionsList"

HEADERS_TEMPLATE = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}

def make_headers(token: str) -> dict:
    h = dict(HEADERS_TEMPLATE)
    if token:
        h["token"] = token
        h["X-UserToken"] = token
    return h

def get_target_date(days_ahead: int = 2) -> str:
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    return d.strftime("%Y-%m-%d")

def check_token(token: str, field_id: str = "") -> Tuple[bool, Any]:
    """返回 (is_valid, details)。details 为响应 JSON 或错误信息。

    注意：不再发送 memberId（接口通常允许不传 memberId 来获取 sessions 列表）。
    """
    payload = {
        "fieldId": field_id,
        "isIndoor": "",
        "placeTypeId": "",
        "searchDate": get_target_date(2),
        "sportTypeId": "2",
    }
    try:
        r = requests.post(SESSIONS_LIST_URL, json=payload, headers=make_headers(token), timeout=6)
    except Exception as e:
        return False, f"请求异常: {e}"

    # 尝试解析 JSON
    try:
        j = r.json()
    except Exception:
        return False, {"status_code": r.status_code, "text": r.text}

    # 常见无权限/未登录的提示判断
    msg = ""
    if isinstance(j, dict):
        msg = j.get("message") or j.get("msg") or ""
    # 判定逻辑：
    # - 200 且 返回非空（列表或包含 sessions） -> 很可能有效
    # - 400/401/403 或 message 提示登录 -> 无效
    if r.status_code == 200:
        # 若返回是列表或 dict 且非空，则视为有效
        if (isinstance(j, list) and len(j) > 0) or (isinstance(j, dict) and j):
            return True, j
        # 200 但返回空，仍可能有效（权限正常但无数据），视为有效但需人工检查
        return True, j

    if r.status_code in (401, 403) or ("登录" in str(msg)) or ("需要用户登录" in str(msg)) or ("token" in str(msg).lower()):
        return False, {"status_code": r.status_code, "message": msg or j}

    # 其它情况返回原始响应以便人工判断
    return False, {"status_code": r.status_code, "response": j}


def fetch_sessions_for_date(token: str, date_str: str) -> Any:
    """调用 weChatSessionsList 获取指定日期的 sessions 列表并返回解析后的 JSON。"""
    payload = {
        "fieldId": "",
        "isIndoor": "",
        "placeTypeId": "",
        "searchDate": date_str,
        "sportTypeId": "2",
    }
    r = requests.post(SESSIONS_LIST_URL, json=payload, headers=make_headers(token), timeout=8)
    r.raise_for_status()
    return r.json()


def flatten_sessions(resp_json: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not resp_json:
        return items
    for group in resp_json:
        if isinstance(group, list):
            for s in group:
                if isinstance(s, dict):
                    items.append(s)
        elif isinstance(group, dict):
            items.append(group)
    return items


def _as_int(val: Any) -> Tuple[bool, int]:
    try:
        return True, int(val)
    except Exception:
        return False, 0


def evaluate_availability(s: Dict[str, Any]) -> Dict[str, Any]:
    keys_of_interest = [
        "status",
        "reserveStatus",
        "isReserve",
        "isBooked",
        "surplus",
        "surplusNumber",
        "remainNumber",
        "orderNumber",
        "numberSurplus",
        "enableStatus",
    ]
    raw = {k: s.get(k) for k in keys_of_interest if k in s}
    available = None
    for key in ["surplus", "surplusNumber", "remainNumber", "numberSurplus"]:
        if key in s and s.get(key) is not None:
            ok, num = _as_int(s.get(key))
            if ok:
                available = num > 0
                break
    return {
        "id": s.get("id"),
        "placeId": s.get("placeId"),
        "openDate": s.get("openDate"),
        "start": s.get("openStartTime"),
        "end": s.get("openEndTime"),
        "raw": raw,
        "available": available,
    }

def main():
    p = argparse.ArgumentParser(description="验证 wechat token 是否有效（优先使用文件顶部全局 TOKEN）")
    p.add_argument("--token", "-t", help="可选：覆盖脚本顶部的 TOKEN")
    p.add_argument("--field", "-f", help="可选 fieldId", default=os.environ.get("FIELD_ID", ""))
    args = p.parse_args()

    # 优先使用脚本顶部全局 TOKEN，若为空则使用命令行/环境变量
    token = TOKEN or args.token or os.environ.get("TOKEN", "")
    if not token:
        print("请在脚本顶部设置 TOKEN，或通过 --token/环境变量提供 token。")
        sys.exit(2)

    ok, details = check_token(token, args.field)
    if ok:
        print("✅ TOKEN 看起来有效（接口返回 200）。")
        # 若 details 是 JSON，简要显示关键信息
        if isinstance(details, dict) or isinstance(details, list):
            print("返回示例（已截断）：")
            try:
                import json
                print(json.dumps(details if isinstance(details, dict) else {"len": len(details)}, ensure_ascii=False)[:1000])
            except Exception:
                print(str(details)[:1000])
        sys.exit(0)
    else:
        print("❌ TOKEN 可能无效或未登录。详情：")
        print(details)
        sys.exit(1)

if __name__ == "__main__":
    main()