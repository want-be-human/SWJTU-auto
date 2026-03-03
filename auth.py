# auth.py
# -*- coding: utf-8 -*-
"""
运行时动态读取最新 token / userId（memberId）。
优先级：环境变量 > auth_store.json > config.py 兜底。
token 失效时可调用 wait_for_token_change() 自动等待文件更新。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "auth_store.json"


@dataclass(frozen=True)
class Auth:
    token: str
    user_id: str  # 对应登录响应里的 userId / 脚本原来的 MEMBER_ID


# ---------- 内部缓存，避免每次都读磁盘 ----------
_cache_auth: Optional[Auth] = None
_cache_mtime: float = -1.0


def _load_from_file() -> Auth:
    """从 auth_store.json 读取 token 和 userId"""
    data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    token = data.get("token")
    user_id = data.get("userId") or data.get("memberId") or data.get("user_id")
    if not token or not user_id:
        raise RuntimeError("auth_store.json 缺少 token/userId 字段")
    return Auth(token=str(token).strip(), user_id=str(user_id).strip())


def _load_from_config() -> Auth:
    """兜底：从 config.py 硬编码读取（向后兼容）"""
    from config import TOKEN, MEMBER_ID
    if TOKEN and MEMBER_ID:
        return Auth(token=str(TOKEN).strip(), user_id=str(MEMBER_ID).strip())
    raise RuntimeError("config.py 中也未配置 TOKEN/MEMBER_ID，且 auth_store.json 不存在")


def get_auth() -> Auth:
    """
    获取当前有效的认证信息，优先级：
      1. 环境变量 SWJTU_TOKEN + SWJTU_USER_ID
      2. auth_store.json（自动缓存，文件变化时刷新）
      3. config.py 中的 TOKEN / MEMBER_ID（兜底）
    """
    # ---- 环境变量（方便 CI / 临时覆盖）----
    tok = os.getenv("SWJTU_TOKEN")
    uid = os.getenv("SWJTU_USER_ID") or os.getenv("SWJTU_MEMBER_ID")
    if tok and uid:
        return Auth(token=tok.strip(), user_id=uid.strip())

    # ---- auth_store.json ----
    global _cache_auth, _cache_mtime
    if STORE_PATH.exists():
        st = STORE_PATH.stat()
        if _cache_auth is not None and st.st_mtime == _cache_mtime:
            return _cache_auth
        try:
            auth = _load_from_file()
            _cache_auth = auth
            _cache_mtime = st.st_mtime
            return auth
        except Exception as e:
            print(f"[auth] 读取 auth_store.json 失败: {e}，尝试 config.py 兜底")

    # ---- config.py 兜底 ----
    return _load_from_config()


def invalidate_cache():
    """强制下次 get_auth() 重新读取文件"""
    global _cache_auth, _cache_mtime
    _cache_auth = None
    _cache_mtime = -1.0


def wait_for_token_change(old_token: str, timeout: float = 0) -> Auth:
    """
    阻塞等待 auth_store.json 更新到一个不同的 token。
    你去小程序重新登录后，token_sniffer 会自动更新该文件。
    timeout: 最长等待秒数，0 表示无限等待。
    """
    start = time.time()
    while True:
        invalidate_cache()
        try:
            auth = get_auth()
            if auth.token != old_token:
                print(f"[auth] 检测到新 token: {auth.token[:8]}...")
                return auth
        except Exception:
            pass

        if timeout > 0 and (time.time() - start) > timeout:
            raise TimeoutError(f"等待新 token 超时（{timeout}s），请确认已重新登录")

        time.sleep(0.3)


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
