import requests
import time
from email.utils import parsedate_to_datetime

r = requests.get("https://zhcg.swjtu.edu.cn/onesports-gateway/wechat-c/api/wechat/memberBookController/weChatSessionsList")
server_time = parsedate_to_datetime(r.headers['Date']).timestamp()
local_time = time.time()
print(f"服务器时间: {r.headers['Date']}")
print(f"本地时间戳: {local_time}")
print(f"差值 (服务器 - 本地): {server_time - local_time:.2f} 秒")