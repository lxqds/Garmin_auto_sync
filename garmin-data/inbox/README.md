# 把佳明 265 数据传给我分析的方法

## 当前方案（推荐）：文件导出 + 本地解析

WorkBuddy 没有内置佳明连接器，但 Garmin Connect 可以导出原始运动文件（`.tcx` 或 `.fit`），
把文件丢进 `garmin-data/inbox/` 目录，我就能用 `analyze_garmin.py` 解析并逐日分析。

### 怎么从佳明导出文件
- **手机 App（Garmin Connect）**：打开一次运动 → 右上角 ⋮ → 分享 / 导出 →
  选「Export Original」（得到 `.fit`）或「Export」（得到 `.tcx`）。
- **网页版（connect.garmin.com）**：登录 → 训练 → 活动 → 点开某次 → 右侧齿轮图标 →
  「Export Original」或「Export to TCX」。

### 怎么让我分析
把导出的文件放进本目录 `garmin-data/inbox/`，然后告诉我"分析一下 inbox"，我会运行：
```
python analyze_garmin.py garmin-data/inbox --maxhr 你的实测最大心率
```
脚本会自动输出每趟运动的：时长、距离、配速、平均/最大心率、步频、
**心率区间占比**、以及**有氧解耦（心血管漂移）**——正好对应你"降心率"的目标。

> 建议：先做一次最大心率测试（见训练方案文档），把真实 HRmax 告诉我，区间分析才准。

---

## 其他可行手段（按麻烦程度）

1. **截图**：直接把 Garmin Connect 的当日/单次运动截图发我，我能读图提取关键数据。最省事但不利于长期对比。
2. **复制文字**：把 App 里的数据摘要（时长/距离/平均心率/配速等）粘贴给我。
3. **第三方中转（进阶）**：把佳明同步到 Strava / Runalyze / intervals.icu，再导出或截图给我。
   适合想做长期趋势面板的人，但需要额外账号配置。
4. **脚本自动拉取（不推荐）**：社区有非官方 Garmin Connect API（如 Python `garminconnect` 库），
   可用你的账号密码自动下载。但**需要把佳明账号密码交给脚本，有隐私与封号风险**，不建议普通使用。

## 推荐工作流
每天跑完 → 从 Garmin Connect 导出当天 `.tcx`/`.fit` → 放进 `inbox/` → 让我跑一次分析。
积累一段时间后，我还能帮你做周/月趋势对比，直观看到"同配速心率是否下降"。
