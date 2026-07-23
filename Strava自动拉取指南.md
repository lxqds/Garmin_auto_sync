# Garmin → Strava → 本地 自动拉取运动数据（合规方案）

目标：你不手动导出了，**跑完步 Garmin 自动同步到 Strava，脚本每天自动把数据拉回本地分析**。

链路：
```
Garmin 手表 → Garmin Connect App（官方同步，一次授权，之后全自动）
            → Strava（官方 OAuth API，只读 activity:read）
            → strava_sync.py（本程序）
            → garmin-data/inbox/
            → watch_and_analyze.py（自动分析 + 趋势汇总）
```

为什么合规 & 安全：
- 不碰 Garmin 账号密码，不走任何非官方接口（无封号/泄露风险）。
- 用 Strava 官方 OAuth 2.0，权限仅 `activity:read`（只读运动数据，不含隐私区）。
- token 存在本地 `garmin-data/.strava_tokens.json`，不进代码、不进 git（已加 `.gitignore`）。

---

## 第一步：让 Garmin 自动同步到 Strava（一次性，之后全自动）

1. 打开手机 **Garmin Connect** App → 右下角「更多」→「设置」→「第三方应用同步」（或「Connected Apps / 已连接应用」）。
2. 找到 **Strava** → 授权登录你的 Strava 账号 → 允许同步。
3. 之后每次手表同步到 Garmin Connect，活动会**自动**出现在 Strava（通常几分钟内）。

> 没 Strava 账号就先去 strava.com 注册一个（免费）。

## 第二步：创建一个 Strava API 应用（拿 client_id / secret）

1. 打开 https://www.strava.com/settings/api （登录后）。
2. 填一下应用信息（随便填，比如 App name 写 `My Training Sync`，其余可留空/默认）。
3. 创建后页面会显示 **Client ID** 和 **Client Secret**。
4. 本程序已生成配置模板 `garmin-data/.strava_config.json`，把这两个值填进去：
   ```json
   {
     "client_id": "你的ClientID",
     "client_secret": "你的ClientSecret"
   }
   ```
   > 回调地址（Authorization Callback Domain）填 `localhost` 即可（Strava 白名单，本地用最方便）。

## 第三步：本地授权（拿 token，只需一次）

在本工作目录运行（用 managed Python）：
```bash
C:/Users/user/.workbuddy/binaries/python/envs/default/Scripts/python.exe strava_sync.py auth
```
程序会打印一个授权链接 → 浏览器打开 → 点「Authorize」→ 跳转到 `http://localhost?code=XXXX...`
（localhost 没服务，页面可能显示无法连接，没关系，**只从地址栏复制 `code=` 后面那段**）→ 粘贴回终端。
授权成功后 token 自动存到 `garmin-data/.strava_tokens.json`。

## 第四步：拉取数据（之后每天跑这一句）

```bash
# 拉取"上次之后"的新活动（默认行为，靠 STATE 记录去重）
python strava_sync.py fetch

# 首次/补历史：拉最近 30 天
python strava_sync.py fetch --days 30

# 或拉某天之后的
python strava_sync.py fetch --after 2026-07-01

# 查看 token 状态 / 上次拉取时间
python strava_sync.py status

# 验证配置与 API 连通
python strava_sync.py test
```
`fetch` 会：拉活动 → 下载每条的原始 `.fit/.tcx`（拿不到时自动用 streams 合成 TCX 兜底）→ 落进 `garmin-data/inbox/` → 自动调用 `watch_and_analyze.py` 出报告 + 维护 `garmin-data/summary.md` 趋势。

---

## 让它"全自动"（可选）

数据获取已自动化（Garmin→Strava 自动同步）。剩下"本地拉取+分析"可以用**定时任务**每天跑一次：

- **方案 A（WorkBuddy 自动化）**：我帮你建一个每天定时执行的任务，自动运行 `strava_sync.py fetch`（到你指定的工作目录）。你只需保证电脑当时开机联网。
- **方案 B（系统计划任务）**：Windows 任务计划程序 / macOS launchd 定时调用上面的 `python strava_sync.py fetch` 命令。

> 注意：本程序只做"读取+本地分析"，不会上传/分享你的任何数据。

---

## 常见问题

- **`activity:read` 够吗？** 够覆盖"所有人/关注者可见"的活动。如果你在 Strava 把活动设为"仅自己可见"，需要把脚本里的 `SCOPE` 改成 `activity:read_all` 再重新 `auth`。
- **限流？** 读取类默认 100 次/15 分钟、1000 次/天，每天拉几次完全够；脚本已处理 429 自动退避。
- **token 过期？** access token 6 小时过期，`fetch` 会**自动用 refresh token 刷新**，无需你干预；refresh token 每次轮换，程序会保存最新值。
- **换表/换账号？** 删掉 `garmin-data/.strava_tokens.json` 重新 `auth` 即可。

## 文件清单
| 文件 | 作用 |
|---|---|
| `strava_sync.py` | 本程序：OAuth + 拉取 + 落盘 + 触发分析 |
| `garmin-data/.strava_config.json` | client_id/secret（机密，勿提交） |
| `garmin-data/.strava_tokens.json` | access/refresh token（机密，勿提交） |
| `garmin-data/.strava_state.json` | 上次拉取时间 + 已下载活动 ID（去重用） |
| `analyze_garmin.py` / `watch_and_analyze.py` | 既有分析器（复用） |
| `garmin-data/inbox/` | 拉下来的原始活动文件 |
| `garmin-data/summary.md` | 趋势汇总 |
