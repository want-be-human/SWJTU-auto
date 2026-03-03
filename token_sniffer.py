# token_sniffer.py
# -*- coding: utf-8 -*-
"""
mitmproxy 插件：自动捕获微信小程序登录响应中的 token/userId，
写入 auth_store.json 供其他脚本动态读取。

用法：
  pip install mitmproxy
  mitmdump -p 8888 -s token_sniffer.py

然后将手机/小程序的网络代理指向本机 8888 端口，
打开小程序完成一次登录即可。
"""
from mitmproxy import http
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "auth_store.json"

LOGIN_PATH = "/onesports-gateway/business-service/api/weChatController/weChatCreateUserAndLogin"


def response(flow: http.HTTPFlow):
    if flow.request.method != "POST":
        return
    if LOGIN_PATH not in flow.request.pretty_url:
        return

    try:
        data = json.loads(flow.response.get_text())
    except Exception:
        return

    token = data.get("token")
    user_id = data.get("userId")
    if not token or not user_id:
        return

    payload = {
        "token": token,
        "userId": str(user_id),
        "capturedAt": int(time.time() * 1000),
    }

    # 先写临时文件再原子替换，避免读取到半写状态
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)

    print(f"[sniffer] auth_store.json 已更新：token={token[:8]}... userId={user_id}")
