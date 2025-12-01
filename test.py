#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准服务器时间 —— 使用下单接口的 timestamp
"""

import requests
import time
import datetime
import re
from email.utils import parsedate_to_datetime

# ------------------ CONFIG ------------------
TOKEN = "f7d9e4c8-176e-4609-9628-5f245571cc93"
BASE_PREFIX = "https://zhcg.swjtu.edu.cn/onesports-gateway"
RESERVE_URL = BASE_PREFIX + "/business-service/orders/weChatSessionsReserve"

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "token": TOKEN,
    "X-UserToken": TOKEN,
    "User-Agent": "Mozilla/5.0",
}
# --------------------------------------------
def parse_ts_ms(val):
    """将可能为 ms/秒的数字或 ISO-8601 字符串转换为毫秒时间戳"""
    # 数字或数字字符串
    if isinstance(val, (int, float)):
        v = float(val)
        return int(v if v >= 1e12 else v * 1000)
    if isinstance(val, str):
        s = val.strip()
        if s.isdigit():
            v = int(s)
            return v if v >= 1e12 else int(v * 1000)
        # 处理 ISO-8601：Z -> +00:00；修正无冒号的时区偏移（如 +000 -> +00:00）
        s = s.replace("Z", "+00:00")
        m = re.search(r'([+-]\d{2})(\d{2})$', s)
        if m:
            s = s[:m.start()] + f"{m.group(1)}:{m.group(2)}"
        try:
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            pass
    return None

def parse_http_date(date_str):
    """把 HTTP Date (RFC-1123) 转为毫秒时间戳"""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

def get_server_time():
    """发送一个无效下单请求，借助返回里的 timestamp 或响应头 Date 拿服务器时间"""
    dummy_payload = {
        "fieldId": "0",  # 故意写错
        "number": 1,
        "orderUseDate": int(time.time() * 1000),
        "requestsList": [],
        "siteName": "test",
        "sportTypeId": "2",
        "sportTypeName": "羽毛球"
    }

    t_send = time.time() * 1000
    try:
        r = requests.post(RESERVE_URL, json=dummy_payload, headers=HEADERS, timeout=5)
    except Exception as e:
        print("[debug] 请求异常：", e)
        return None
    t_recv = time.time() * 1000

    # 尝试解析 JSON 里的 timestamp（若有）
    server_ts = None
    try:
        data = r.json()
    except Exception:
        data = None

    if isinstance(data, dict):
        server_ts_raw = data.get("timestamp")
        if server_ts_raw is not None:
            server_ts = parse_ts_ms(server_ts_raw)
            if server_ts is None:
                print("[debug] 无法解析 JSON 中的 timestamp：", server_ts_raw)
            else:
                source = "json"

    # 如果 JSON 没有可用 timestamp，尝试使用响应头 Date
    if server_ts is None:
        hdr_date = r.headers.get("Date") or r.headers.get("date")
        if hdr_date:
            server_ts = parse_http_date(hdr_date)
            if server_ts:
                source = "date"
                hdr_used = hdr_date
                print(f"[debug] 使用响应头 Date 作为服务器时间: {hdr_date}")

    if server_ts is None:
        print("⚠️ 响应中没有 timestamp，且响应头也无法提供有效时间。返回内容：", data or r.text)
        return None

    # NTP 校正：请求往返延迟（ms）
    latency = (t_recv - t_send) / 2.0
    corrected = server_ts + latency
    # 返回额外的信息：source 表示时间来自 "json" 还是 "date"；hdr_used 在 source=="date" 时包含原始 Date 字符串
    return server_ts, latency, corrected, locals().get("source", "unknown"), locals().get("hdr_used", None)

def main():
    print("[test] 多次采样服务器时间（默认 7 次），并计算稳健的时间差中位数...")
    samples = []
    sources = []
    for i in range(7):
        result = get_server_time()
        if not result:
            print(f"[sample {i+1}] 无法获取服务器时间")
            continue
        server_ts, latency, corrected, source, hdr = result
        local_now = time.time() * 1000
        delta = corrected - local_now
        samples.append(delta)
        sources.append(source)
        src_info = f"(source={source})"
        if source == "date" and hdr:
            src_info += f" hdr={hdr}"
        print(f"[sample {i+1}] 服务器_ts={server_ts} 本地_ts={int(local_now)} latency={latency:.1f}ms 校正后={int(corrected)} delta={delta:.1f}ms {src_info}")
        time.sleep(0.12)

    if not samples:
        print("未取得有效样本，无法计算时间差")
        return

    # 计算中位数并剔除明显离群值（>5s）
    import statistics
    median_all = statistics.median(samples)
    filtered = [d for d in samples if abs(d - median_all) <= 5000]
    median_filtered = statistics.median(filtered) if filtered else median_all

    print('\n样本(delta ms):', [round(x,1) for x in samples])
    print('样本来源:', sources)
    print(f'所有样本中位数: {median_all:.1f} ms')
    if filtered != samples:
        print(f'剔除离群后的中位数: {median_filtered:.1f} ms (剔除阈值 5000 ms)')
    else:
        print('未发现离群样本')

    print("[提示] 使用剔除离群后的中位数作为建议的 delta。若中位数很大(>5000ms)，请先同步本机系统时间或检查网络/代理。")

if __name__ == "__main__":
    main()
