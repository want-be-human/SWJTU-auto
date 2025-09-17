import requests
import datetime
import time

# 固定参数
BASE_URL = "https://zhcg.swjtu.edu.cn/onesports-gateway"
FIELD_ID = "1462312540799516672"     # 九里羽毛球馆
PLACE_ID = "1519942071047168000"     # 1号羽毛球
SPORT_TYPE_ID = "2"                  # 羽毛球
TOKEN = "c1fd08b5-d49a-47b2-afaa-be66b4078274"

HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "zhcg.swjtu.edu.cn",
    "Referer": "https://servicewechat.com/wx34c9f462afa158b3/27/page-frame.html",
    "User-Agent": "Mozilla/5.0 ... MiniProgramEnv/Windows",
    "token": TOKEN,
    "X-UserToken": TOKEN,
}

def get_order_date_millis(date_str):
    """把 yyyy-MM-dd 转换成毫秒时间戳"""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return int(time.mktime(dt.timetuple()) * 1000)

def reserve_session(session_id, date_str):
    """提交预约"""
    url = f"{BASE_URL}/business-service/orders/weChatSessionsReserve"
    payload = {
        "number": 1,   # 场次数量
        "orderUseDate": get_order_date_millis(date_str),
        "requestsList": [{"sessionsId": session_id}],
        "fieldId": FIELD_ID,
        "fieldName": "九里羽毛球1-6号",
        "siteName": "1号羽毛球",
        "sportTypeId": SPORT_TYPE_ID,
        "sportTypeName": "羽毛球"
    }
    resp = requests.post(url, json=payload, headers=HEADERS).json()
    return resp

if __name__ == "__main__":
    # 目标日期和场次
    target_date = "2025-09-17"
    target_session_id = "1957110241580556288"  # 14:00–15:00 的 sessionId

    result = reserve_session(target_session_id, target_date)
    print("下单结果:", result)
