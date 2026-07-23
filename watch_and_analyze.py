#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin 运动数据 · 分析自动化程序
================================
监控 garmin-data/inbox/ 下的 .tcx / .fit 文件，自动：
  1. 解析并分析 (复用 analyze_garmin.py)
  2. 生成单次报告 -> garmin-data/reports/YYYY-MM-DD_HHMM_<名>.md
  3. 追加到趋势汇总 -> garmin-data/summary.md
  4. 把已分析文件归档到 -> garmin-data/processed/

用法:
  # 处理 inbox 里当前所有文件（一次性，适合手动跑 / 定时任务）
  python watch_and_analyze.py --once

  # 持续监控 inbox，发现新文件立刻处理（常驻服务）
  python watch_and_analyze.py --watch

  # 指定最大心率（默认 200，来自用户实测）
  python watch_and_analyze.py --once --maxhr 200

说明:
  - 真正的"从 Garmin 账号自动拉取数据"不在本程序范围内（需账号登录非官方
    接口，有隐私/封号风险）。本程序负责"数据落地后的全自动分析"。
  - 数据获取仍由用户从 Garmin Connect 导出文件丢进 inbox/。
  - 合规的自动获取替代方案：Garmin -> Strava 官方同步 -> Strava API 拉取。
"""
import os
import sys
import glob
import time
import shutil
import argparse

# 复用同目录的解析器
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_garmin as ag  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(BASE, 'garmin-data', 'inbox')
PROCESSED = os.path.join(BASE, 'garmin-data', 'processed')
REPORTS = os.path.join(BASE, 'garmin-data', 'reports')
SUMMARY = os.path.join(BASE, 'garmin-data', 'summary.md')

DEFAULT_MAXHR = 200  # 用户实测最大心率(来自 D:/Download/最大心率.csv)


def fmt_pace(p):
    if not p:
        return '—'
    m = int(p)
    s = int(round((p - m) * 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}/km"


def find_new():
    pats = glob.glob(os.path.join(INBOX, '*.tcx')) + \
           glob.glob(os.path.join(INBOX, '*.fit'))
    return sorted(pats)


def write_report(path, a, maxhr):
    name = os.path.basename(path)
    stamp = time.strftime('%Y-%m-%d_%H%M')
    out = os.path.join(REPORTS, f"{stamp}_{name}.md")
    lines = [f"# 运动报告 · {name}", f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')} ｜ 最大心率基准: {maxhr:.0f}", ""]
    if not a:
        lines.append("_无法解析或无有效轨迹点_")
    else:
        lines += [
            f"- 时长: {int(a['duration']//60)}分{int(a['duration']%60)}秒",
            f"- 距离: {a['distance_km']:.2f} km",
            f"- 平均配速: {fmt_pace(a['pace_min_km'])}",
        ]
        if a['avg_hr']:
            lines.append(f"- 平均心率: {a['avg_hr']:.0f} bpm（最大 {a['max_hr']:.0f}）")
        if a['avg_cad']:
            lines.append(f"- 平均步频: {a['avg_cad']:.0f} spm")
        if a['zones']:
            znames = ['Z1<60%', 'Z2 60-70%', 'Z3 70-80%', 'Z4 80-90%', 'Z5>90%']
            lines.append("- 心率区间占比:")
            lines.append("  " + "  ".join(f"{znames[i]}:{a['zones'][i]:.0f}%" for i in range(5)))
        if a['decoup'] is not None:
            dh = a['decoup_hr']
            verdict = "优秀(有氧基础好)" if a['decoup'] < 0.05 else ("正常" if a['decoup'] < 0.10 else "偏高,注意补水/强度")
            lines.append(f"- 有氧解耦(心血管漂移): {a['decoup']*100:+.1f}%（前段HR{dh[0]:.0f}/后段HR{dh[1]:.0f}）-> {verdict}")
    with open(out, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    return out


def append_summary(path, a, maxhr):
    name = os.path.basename(path)
    date = time.strftime('%Y-%m-%d')
    if not a:
        row = f"| {date} | {name} | 解析失败 | - | - | - | - | - |"
    else:
        z = a['zones']
        z2 = f"{z[1]:.0f}%" if z else "-"
        dec = f"{a['decoup']*100:+.1f}%" if a['decoup'] is not None else "-"
        row = (f"| {date} | {name} | {a['distance_km']:.2f} km | "
               f"{int(a['duration']//60)}分 | {fmt_pace(a['pace_min_km'])} | "
               f"{a['avg_hr']:.0f} | {z2} | {dec} |")
    header = ("# 运动趋势汇总\n\n"
              "| 日期 | 文件 | 距离 | 时长 | 配速 | 平均HR | Z2占比 | 有氧解耦 |\n"
              "| --- | --- | --- | --- | --- | --- | --- | --- |\n")
    if not os.path.exists(SUMMARY):
        with open(SUMMARY, 'w', encoding='utf-8') as f:
            f.write(header)
    else:
        with open(SUMMARY, 'r', encoding='utf-8') as f:
            content = f.read()
        if '| 日期 |' not in content:
            # 旧格式或无表头，重建
            with open(SUMMARY, 'w', encoding='utf-8') as f:
                f.write(header)
    with open(SUMMARY, 'a', encoding='utf-8') as f:
        f.write(row + "\n")


def process_file(path, maxhr):
    name = os.path.basename(path)
    recs = ag.parse_file(path) or []
    a = ag.analyze(recs, maxhr=maxhr)
    rep = write_report(path, a, maxhr)
    append_summary(path, a, maxhr)
    # 归档
    os.makedirs(PROCESSED, exist_ok=True)
    dst = os.path.join(PROCESSED, name)
    # 避免同名覆盖
    if os.path.exists(dst):
        dst = os.path.join(PROCESSED, f"{time.strftime('%Y%m%d%H%M')}_{name}")
    shutil.move(path, dst)
    print(f"[OK] {name} -> 报告: {os.path.basename(rep)} ; 已归档")
    if a:
        print(f"     距离 {a['distance_km']:.2f}km / 配速 {fmt_pace(a['pace_min_km'])} / 平均HR {a['avg_hr']:.0f}")


def run_once(maxhr):
    os.makedirs(PROCESSED, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    files = find_new()
    if not files:
        print("inbox 为空，无新文件。")
        return 0
    print(f"=== 发现 {len(files)} 个新文件，开始分析 ===")
    for f in files:
        process_file(f, maxhr)
    print(f"=== 完成。趋势汇总: {SUMMARY} ===")
    return len(files)


def run_watch(maxhr, interval=15):
    print(f"监控中: {INBOX} （每 {interval}s 检查一次，Ctrl+C 退出）")
    try:
        while True:
            files = find_new()
            if files:
                for f in files:
                    process_file(f, maxhr)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止监控。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--maxhr', type=float, default=DEFAULT_MAXHR)
    ap.add_argument('--once', action='store_true', help='处理当前 inbox 内所有文件后退出')
    ap.add_argument('--watch', action='store_true', help='持续监控 inbox')
    ap.add_argument('--interval', type=int, default=15, help='--watch 模式检查间隔(秒)')
    args = ap.parse_args()

    if args.watch:
        run_watch(args.maxhr, args.interval)
    else:
        # 默认行为: --once
        run_once(args.maxhr)


if __name__ == '__main__':
    main()
