# SWJTU-auto

西南交通大学体育场馆（羽毛球）自动预约工具。

---

## 项目结构

```
SWJTU-auto/
├── config.py            # 用户配置（校区、场号、SESSION_IDS、TOKEN 兜底值）
├── auth.py              # 认证模块（动态读取 token，支持缓存与过期等待）
├── refresh_token.py     # Token 刷新工具（预约前运行，确保 token 有效）
├── token_sniffer.py     # mitmproxy 插件（自动抓包捕获登录 token）
├── get_sid.py           # 获取后天目标时段的 Session ID
├── auto-two.py          # 抢场主脚本（定时持续下单）
├── check.py             # 场地信息交互式查询工具
├── auth_store.json      # [自动生成] token 存储文件（已 gitignore）
├── .gitignore
└── README.md
```

---

## 环境准备

### 1. Python 环境

需要 Python 3.8+，安装依赖：

```bash
pip install requests
```

如需使用自动抓包模式刷新 token（可选）：

```bash
pip install mitmproxy
```

### 2. 编辑配置文件

打开 `config.py`，根据你的需求修改：

```python
# 选择校区：'xipu'（犀浦）或 'jiuli'（九里）
SELECTED_CAMPUS = 'xipu'

# 选择场地编号（犀浦 1-9，九里 1-6）
SELECTED_COURT_NUMBER = 8

# Token 和 Member ID（作为兜底值，推荐通过 refresh_token.py 管理）
TOKEN = "你的token"
MEMBER_ID = "你的memberId"
```

---

## 使用流程

每次预约按以下 3 步顺序执行：

### 第 1 步：刷新 Token

```bash
python refresh_token.py
```

脚本会自动检查当前 token 是否有效：
- **有效** → 提示无需刷新，直接进入第 2 步
- **过期** → 提供两种刷新方式供你选择：
  - **方式 1：手动输入**（默认）—— 从抓包工具（Fiddler / Charles 等）复制 token 和 userId 粘贴
  - **方式 2：自动抓包** —— 需提前配置 mitmproxy 和手机代理

常用命令参数：

| 命令 | 说明 |
|------|------|
| `python refresh_token.py` | 默认模式：检查 → 选择刷新方式 |
| `python refresh_token.py --check` | 仅检查当前 token 是否有效 |
| `python refresh_token.py --manual` | 直接进入手动输入模式 |
| `python refresh_token.py --auto` | 直接进入自动抓包模式 |

### 第 2 步：获取 Session ID

```bash
python get_sid.py
```

脚本会查询**后天**的场地信息，输出目标时段的 Session ID，例如：

```
  19:00-20:00: 1984652097234567890
  20:00-21:00: 1984652097990172672
  21:00-22:00: 1984652098409603072
```

将你需要的时段 ID 填入 `config.py` 的 `SESSION_IDS` 列表：

```python
SESSION_IDS = [
    "1984652097990172672",   # 20:00-21:00
    "1984652098409603072"    # 21:00-22:00
]
```

### 第 3 步：运行抢场脚本

```bash
python auto-two.py
```

脚本启动后会：
1. 验证 token 有效性（无效则提醒先运行 `refresh_token.py`）
2. 等待到指定的触发时间（默认 22:30:00）
3. 在触发时间前 0.3 秒开始持续发送预约请求
4. 成功或场次被占用后自动停止

**抢场时间设置**（在 `auto-two.py` 中修改）：

```python
TRIGGER_HOUR = 22
TRIGGER_MINUTE = 30
TRIGGER_SECOND = 0
```

---

## 辅助工具

### 场地信息查询

```bash
python check.py
```

交互式查询任意日期、任意校区、任意场地的状态信息。支持按时间段过滤。

---

## Token 读取优先级

所有脚本通过 `auth.py` 统一获取 token，优先级如下：

1. **环境变量**：`SWJTU_TOKEN` + `SWJTU_USER_ID`
2. **auth_store.json**：由 `refresh_token.py` 或 `token_sniffer.py` 自动写入
3. **config.py**：硬编码的 `TOKEN` / `MEMBER_ID`（兜底）

---

## 自动抓包模式说明（可选）

如果你希望全自动捕获 token（无需手动复制粘贴），可以使用 mitmproxy：

```bash
# 安装
pip install mitmproxy

# 方式一：通过 refresh_token.py 启动（推荐）
python refresh_token.py --auto

# 方式二：手动启动 sniffer
mitmdump -p 8888 -s token_sniffer.py
```

然后将手机/模拟器的网络代理指向 `本机IP:8888`，打开微信小程序触发一次登录，token 会自动保存到 `auth_store.json`。

---

## 注意事项

- `auth_store.json` 包含敏感的 token 信息，已加入 `.gitignore`，**不会被提交到仓库**
- 每次预约前**务必先运行 `refresh_token.py`**，确保 token 未过期
- 即使在抢场过程中 token 意外过期，`auto-two.py` 也会自动暂停并等待你刷新后继续
- Session ID 每天不同，**每次预约都需要重新运行 `get_sid.py` 获取**
