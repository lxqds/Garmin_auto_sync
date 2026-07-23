# 佳明运动数据同步项目

把你的 **Garmin（佳明）Connect 账号** 自动同步到本地，并转成可行动的恢复 / 心率分析：
每日健康指标（睡眠、HRV、静息心率、身体电量、训练准备度、压力）+ 跑步活动（TCX/FIT），
再生成「睡眠 → HRV / 静息心率」趋势图。专为**中国区账号（connect.garmin.cn）**打磨。

> 本工程已同时封装为 WorkBuddy 用户级技能 `garmin-sync`（位于 `~/.workbuddy/skills/garmin-sync`），
> 可在任意会话输入一句话即可复用整套流程。详见文末「作为技能复用」。

---

## 目录结构

```
.
├── README.md                      # 本文件（项目说明）
├── garmin_sync.py                 # 中国区直连：登录 + 拉健康/活动
├── analyze_garmin.py              # TCX/FIT 解析（心率区间/有氧解耦/配速）
├── watch_and_analyze.py           # 监控 inbox/ 自动分析 + 趋势汇总
├── make_trend_chart.py            # 由 health_records.json 生成趋势图 HTML
├── strava_sync.py                 # 合规备选：Garmin→Strava OAuth 拉活动（可选）
├── garmin-data/                   # 数据目录（凭据/令牌/产出，已 .gitignore）
│   ├── .garmin_config.json        # 账号配置（email/password/region）
│   ├── .garmin_tokens_cn/         # 中国区令牌（自动刷新，~1年）
│   ├── inbox/                     # 待分析的活动文件（.tcx/.fit）
│   ├── processed/                 # 已分析归档
│   ├── reports/                   # 单次活动分析报告
│   ├── health_daily.md            # 每日健康面板（人读表格）
│   ├── health_records.json        # 每日健康原始数据
│   └── health_trend.html          # 趋势图（HRV/静息心率 vs 睡眠时长）
├── 跑步心率偏高的原因与研究解读.md
├── 跑步有氧训练降心率方案.md
├── 最大心率数据分析.md
├── AI健康手表对比与推荐.md
├── 佳明直连接入指南.md
├── Strava自动拉取指南.md
└── garmin-sync.zip                # 导出的技能包（可分享/重装）
```

---

## 快速开始

### 1. 依赖

```bash
python -m venv venv && venv/bin/pip install garminconnect
```

### 2. 配置

首次运行 `garmin_sync.py` 会自动生成 `garmin-data/.garmin_config.json`，
填入 `email` / `password`（中国区账号），确认 `region: "cn"`。

### 3. 首次登录（中国区 + MFA）

```bash
python garmin_sync.py auth --mfa <6位验证码>
```

验证码由佳明发到你账号的邮箱/手机。成功后令牌存 `garmin-data/.garmin_tokens_cn/`，
之后约 1 年内免密免码；令牌过期时 `fetch` 会用密码自动重登。

### 4. 拉取数据

```bash
python garmin_sync.py fetch --days 30
```

产出 `health_daily.md` 与 `health_records.json`。新跑步活动下载到 `inbox/` 并自动分析。

### 5. 分析跑步活动

把导出的 `.tcx` / `.fit` 丢进 `garmin-data/inbox/`，再：

```bash
python watch_and_analyze.py --once      # 单次
python watch_and_analyze.py --watch      # 持续监控
```

或直接分析单个文件：`python analyze_garmin.py <file.tcx> --maxhr 200`

### 6. 趋势图

```bash
python make_trend_chart.py
```

生成 `garmin-data/health_trend.html`（自包含 SVG，无需联网）。
横轴睡眠时长、左轴 HRV、右轴静息心率；并打印相关系数（睡眠时长 vs HRV 正相关、
vs 静息心率负相关）。

### 7. 每日自动同步

已建 WorkBuddy 自动化（每天 08:00）：依次跑 `fetch` + `make_trend_chart.py`，
令牌持久故无需交互。可在 WorkBuddy 自动化面板查看/停用。

---

## 中国区关键说明（必读）

- **务必 `is_cn=True`**：`connect.garmin.cn` 与 `connect.garmin.com` 数据完全隔离。
  中国区账号连全球端点会显示为空壳账号（0 设备、全 null），这是「fetch 拉空」的头号原因。
- **令牌按区隔离**：中国区用 `.garmin_tokens_cn/`，勿与全球令牌混用。
- **MFA 必现**：后台/定时任务用 `auth --mfa <码>`，别依赖交互输入。

---

## 隐私与数据安全（重要）

本仓库**刻意不含任何敏感信息**，相关文件已被 `.gitignore` 排除、从未入库：

| 已排除（绝不入库） | 说明 |
|---|---|
| `garmin-data/.garmin_config.json` | 账号 email / password / region 配置 |
| `garmin-data/.garmin_tokens_cn/` | 中国区登录令牌（等同账号读取权限） |
| `garmin-data/.garmin_state.json` | 同步状态 |
| `garmin-data/health_*.md` `.json` `.html` | 个人每日健康面板 / 原始数据 / 趋势图 |
| `garmin-data/inbox/*.fit` `*.tcx` `*.gpx` | 原始运动记录 |
| `.workbuddy/` | 本地工作区记忆 / 个人笔记 |
| `garmin-sync.zip` | 导出的技能包（生成物，非源码） |

> ✅ 推送前已用 `git ls-files` 复核：远端 `main` 仅含 15 个源码 / 文档文件，无任何令牌、配置、健康数据或原始记录。

**注意事项**
- 文档中的训练参数（最大心率 ≈ 200 bpm、作息 1–2 点睡等）为**作者个人情况**，仅供参考，请勿直接套用。
- 本仓库默认设为 **私有（private）** 以保护个人信息；如需公开，请先确认 `garmin-data/` 下无遗漏的敏感文件。
- 若你 fork / 克隆后自行运行，令牌与健康数据将落在你本地的 `garmin-data/`，请自行评估隐私风险。

---

## 排错速查

| 现象 | 原因 | 处理 |
|---|---|---|
| fetch 全空、0 设备 | 连错国际区 | 设 `region:"cn"`，删旧全球令牌 |
| 修好区后仍 0 健康 | 脏 `.garmin_state.json` 标记已处理 | 删 `state`+`health_*.json`/`health_daily.md` 后重跑 |
| HRV/睡眠分/压力全 null | 解析字段错位（见下） | HRV 取 `hrvSummary` 嵌套；睡眠分取训练准备度接口；压力回退 `get_stats.averageStressLevel` |
| 限流报错 | 频率过高 | 脚本已指数退避重试 |

更全的踩坑清单见技能内 `references/troubleshooting.md`，或本目录 `佳明直连接入指南.md`。

---

## 已生成的交付物（当前账号真实数据）

- `garmin-data/health_daily.md` —— 近 30 天每日健康面板
- `garmin-data/health_trend.html` —— 趋势图（HRV/静息心率 vs 睡眠时长，r≈0.62 / −0.51）
- `garmin-data/health_records.json` —— 原始数据，可二次分析

---

## 作为 WorkBuddy 技能复用

整套流程已封装为用户级技能 `garmin-sync`：

- **位置**：`~/.workbuddy/skills/garmin-sync/`（跨所有项目可用）
- **包含**：`SKILL.md` + `scripts/`（5 个脚本）+ `references/troubleshooting.md`
- **导出包**：`garmin-sync.zip`（可分享给他人或重装）
- **触发**：对话中说「同步我的佳明数据 / 拉 HRV / 跑步心率分析」等即自动调用

重新安装技能：`python .../skill-creator/scripts/package_skill.py <技能目录>` 解包即可。
