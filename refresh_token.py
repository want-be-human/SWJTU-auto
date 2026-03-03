#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token 刷新 & 认证模块 —— 在运行预约脚本前执行，确保 token 是最新的。
也作为公共库被 auto-two.py / get_sid.py / check.py 导入。

用法：
  python refresh_token.py              # 默认：先检查再选择刷新方式
  python refresh_token.py --manual     # 手动输入 token
  python refresh_token.py --check      # 仅检查当前 token 是否有效

推荐工作流：
  1. python refresh_token.py    ← 确保 token 新鲜
  2. python get_sid.py           ← 获取 session ID
  3. python auto-two.py          ← 抢场
"""
from __future__ import annotations

import argparse
import json
import time
import requests
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "auth_store.json"

# ---------- 验证用的 API（需要鉴权） ----------
VALIDATE_URL = (
    "https://zhcg.swjtu.edu.cn/onesports-gateway"
    "/business-service/orders/weChatSessionsReserve"
)

HEADERS_TEMPLATE = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "zhcg.swjtu.edu.cn",
    "Referer": "https://servicewechat.com/wx34c9f462afa158b3/27/page-frame.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 "
        "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows"
    ),
}


# ──────────────── Auth 数据结构 & 读取 ────────────────

@dataclass(frozen=True)
class Auth:
    token: str
    user_id: str  # 对应登录响应里的 userId / 脚本原来的 MEMBER_ID


def get_auth() -> Auth:
    """
    获取当前认证信息。优先级：auth_store.json > config.py 兜底。
    """
    token, uid = load_current_auth()
    if token and uid:
        return Auth(token=str(token).strip(), user_id=str(uid).strip())
    raise RuntimeError("未找到有效的 token / userId，请先运行 refresh_token.py")


def need_login(status, resp) -> bool:
    """
    判断 HTTP 响应是否表示 token 已过期 / 需要重新登录。
    已知特征：HTTP 400，body.message 包含 '{403}当前请求需要用户登录'
    """
    if status in (401, 403):
        return True
    if status == 400 and isinstance(resp, dict):
        msg = resp.get("message") or ""
        return ("需要用户登录" in msg) or ("{403}" in msg)
    return False


# ──────────────── 工具函数 ────────────────

def _make_headers(token: str) -> dict:
    h = dict(HEADERS_TEMPLATE)
    h["token"] = token
    h["X-UserToken"] = token
    h["x-usertoken"] = token
    return h


def validate_token(token: str, user_id: str) -> bool:
    """
    发一个轻量请求验证 token 是否仍然有效。
    使用预约接口（空 payload），该接口强制鉴权：
      - 无效 token → 400 + '{403}当前请求需要用户登录'
      - 有效 token → 200 + code:201 '请选择要预定的场次'（正常业务错误）
    """
    payload = {
        "number": 0,
        "orderUseDate": 0,
        "requestsList": [],
        "fieldId": "0",
        "fieldName": "validate",
        "siteName": "validate",
        "sportTypeId": "2",
        "sportTypeName": "validate",
    }
    try:
        r = requests.post(VALIDATE_URL, json=payload, headers=_make_headers(token), timeout=6)
        if r.status_code == 200:
            return True
        # 非 200：检查是否为已知的"需要登录"响应
        try:
            body = r.json()
            msg = body.get("message") or ""
            if "需要用户登录" in msg or "{403}" in msg:
                return False
        except Exception:
            pass
        # 其他非 200 错误（如 500 / 网络问题），打印详情
        print(f"  [WARN] 验证返回 HTTP {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"  [WARN] 验证请求异常: {e}")
        return False


def save_auth(token: str, user_id: str):
    """保存认证信息到 auth_store.json（原子写）。"""
    payload = {
        "token": token.strip(),
        "userId": str(user_id).strip(),
        "capturedAt": int(time.time() * 1000),
    }
    tmp = STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


def load_current_auth():
    """从 auth_store.json → config.py 依次尝试读取。"""
    if STORE_PATH.exists():
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            token = data.get("token")
            uid = data.get("userId") or data.get("memberId")
            if token and uid:
                return token, uid
        except Exception:
            pass

    try:
        from config import TOKEN, MEMBER_ID
        if TOKEN and MEMBER_ID:
            return TOKEN, MEMBER_ID
    except Exception:
        pass

    return None, None


# ──────────────── 检查当前 token ────────────────

def check_current_token() -> bool:
    """检查当前 token 是否有效，返回 True/False。"""
    token, user_id = load_current_auth()
    if not token or not user_id:
        print("[INFO] 未找到已保存的 token。")
        return False

    print(f"[INFO] 正在验证当前 token: {token[:8]}...  userId: {user_id}")
    if validate_token(token, user_id):
        print("[OK] 当前 token 仍然有效！")
        return True
    else:
        print("[EXPIRED] 当前 token 已过期，需要刷新。")
        return False


# ──────────────── 手动输入模式 ────────────────

def manual_mode() -> bool:
    """手动粘贴 token 和 userId。"""
    print("\n--- 手动输入模式 ---")
    print("请使用抓包工具（Fiddler / Charles / 浏览器开发者工具）获取登录响应。")
    print("在微信小程序中完成一次登录/刷新操作，找到以下接口的响应：")
    print("  POST .../weChatCreateUserAndLogin")
    print("从响应 JSON 中复制 token 和 userId 字段。\n")

    token = input("请输入 token: ").strip()
    if not token:
        print("[ERROR] token 不能为空。")
        return False

    user_id = input("请输入 userId (memberId): ").strip()
    if not user_id:
        print("[ERROR] userId 不能为空。")
        return False

    print("[INFO] 正在验证新 token…")
    valid = validate_token(token, user_id)

    if valid:
        save_auth(token, user_id)
        print(f"[OK] token 验证通过并已保存到 auth_store.json！")
        return True

    # 验证不通过——让用户决定
    print("[WARN] token 验证未通过（可能已过期或网络问题）。")
    choice = input("是否仍然保存？(y/n, 默认 y): ").strip().lower()
    if choice != "n":
        save_auth(token, user_id)
        print("[OK] 已保存。")
        return True
    return False


# ──────────────── 入口 ────────────────

def main():
    parser = argparse.ArgumentParser(description="SWJTU 场馆预约 - Token 刷新工具")
    parser.add_argument("--manual", action="store_true", help="手动输入 token")
    parser.add_argument("--check", action="store_true", help="仅检查当前 token 是否有效")
    args = parser.parse_args()

    print("=== SWJTU 场馆预约 - Token 刷新工具 ===\n")

    # 仅检查模式
    if args.check:
        check_current_token()
        return

    # 先看当前 token 是否还能用
    if check_current_token():
        choice = input("\n当前 token 有效，是否仍要刷新？(y/n, 默认 n): ").strip().lower()
        if choice != "y":
            print("跳过刷新，可以直接运行预约脚本。")
            return

    # 直接进入手动输入
    manual_mode()


if __name__ == "__main__":
    main()
