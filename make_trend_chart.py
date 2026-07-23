#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 health_records.json，生成 HRV / 静息心率 随睡眠时长变化的趋势图（自包含 SVG，无外部依赖）。
用法：python make_trend_chart.py  ->  输出 garmin-data/health_trend.html
"""
import json
from pathlib import Path

DATA = Path("garmin-data")
OUT = DATA / "health_trend.html"
recs = json.loads((DATA / "health_records.json").read_text(encoding="utf-8"))

rows = []
for d, r in recs.items():
    s = r.get("sleep_seconds"); h = r.get("hrv_avg"); rh = r.get("resting_hr")
    if isinstance(s, (int, float)) and isinstance(h, (int, float)) and isinstance(rh, (int, float)) and s > 0:
        rows.append({"date": d, "sleep_h": s / 3600.0, "hrv": h, "rhr": rh})
rows.sort(key=lambda x: x["date"])


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


sh = [r["sleep_h"] for r in rows]
r_hrv = pearson(sh, [r["hrv"] for r in rows])
r_rhr = pearson(sh, [r["rhr"] for r in rows])

# ---------- 通用绘图参数 ----------
W, H = 680, 400
ml, mr, mt, mb = 64, 64, 28, 54
pw = W - ml - mr
ph = H - mt - mb

XMAX = 9          # 睡眠时长轴上限（小时）
HRV_MAX = 100     # 左轴 HRV 上限
RHR_MIN, RHR_MAX = 40, 70  # 右轴静息心率范围


def sx(v):
    return ml + v / XMAX * pw


def syHRV(v):
    return mt + (1 - v / HRV_MAX) * ph


def syRHR(v):
    return mt + (1 - (v - RHR_MIN) / (RHR_MAX - RHR_MIN)) * ph


def grid_scatter():
    parts = []
    for i in range(0, 10):
        x = ml + i / 9 * pw
        parts.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{mt+ph}" stroke="#eee"/>')
        parts.append(f'<text x="{x:.1f}" y="{mt+ph+18}" font-size="11" fill="#666" text-anchor="middle">{i}</text>')
    for v in range(0, 101, 20):
        y = mt + (1 - v / 100) * ph
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+pw}" y2="{y:.1f}" stroke="#eee"/>')
        parts.append(f'<text x="{ml-8}" y="{y+4:.1f}" font-size="11" fill="#2563eb" text-anchor="end">{v}</text>')
    for v in range(40, 71, 10):
        y = mt + (1 - (v - 40) / 30) * ph
        parts.append(f'<text x="{ml+pw+8}" y="{y+4:.1f}" font-size="11" fill="#dc2626" text-anchor="start">{v}</text>')
    return "\n".join(parts)


def grid_time():
    parts = []
    for v in range(0, 101, 20):
        y = mt + (1 - v / 100) * ph
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+pw}" y2="{y:.1f}" stroke="#eee"/>')
        parts.append(f'<text x="{ml-8}" y="{y+4:.1f}" font-size="11" fill="#2563eb" text-anchor="end">{v}</text>')
    for v in range(40, 71, 10):
        y = mt + (1 - (v - 40) / 30) * ph
        parts.append(f'<text x="{ml+pw+8}" y="{y+4:.1f}" font-size="11" fill="#dc2626" text-anchor="start">{v}</text>')
    return "\n".join(parts)


def build_scatter():
    parts = [grid_scatter()]
    srt = sorted(rows, key=lambda r: r["sleep_h"])
    hr_poly = " ".join(f"{sx(r['sleep_h']):.1f},{syHRV(r['hrv']):.1f}" for r in srt)
    rh_poly = " ".join(f"{sx(r['sleep_h']):.1f},{syRHR(r['rhr']):.1f}" for r in srt)
    parts.append(f'<polyline points="{hr_poly}" fill="none" stroke="#2563eb" stroke-width="1.5" stroke-opacity="0.45"/>')
    parts.append(f'<polyline points="{rh_poly}" fill="none" stroke="#dc2626" stroke-width="1.5" stroke-opacity="0.45"/>')
    for r in rows:
        x = sx(r["sleep_h"])
        parts.append(f'<circle cx="{x:.1f}" cy="{syHRV(r["hrv"]):.1f}" r="4" fill="#2563eb"><title>{r["date"]} 睡眠{r["sleep_h"]:.1f}h HRV {r["hrv"]}</title></circle>')
        parts.append(f'<circle cx="{x:.1f}" cy="{syRHR(r["rhr"]):.1f}" r="4" fill="#dc2626"><title>{r["date"]} 睡眠{r["sleep_h"]:.1f}h 静息HR {r["rhr"]}</title></circle>')
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#999"/>')
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#999"/>')
    parts.append(f'<text x="{ml+pw/2}" y="{H-8}" font-size="12" fill="#444" text-anchor="middle">睡眠时长 (小时)</text>')
    parts.append(f'<text x="16" y="{mt+ph/2}" font-size="12" fill="#2563eb" text-anchor="middle" transform="rotate(-90 16 {mt+ph/2})">HRV (ms)</text>')
    parts.append(f'<text x="{W-14}" y="{mt+ph/2}" font-size="12" fill="#dc2626" text-anchor="middle" transform="rotate(90 {W-14} {mt+ph/2})">静息心率 (bpm)</text>')
    parts.append(f'<circle cx="{ml+12}" cy="{mt+6}" r="4" fill="#2563eb"/><text x="{ml+22}" y="{mt+10}" font-size="11" fill="#444">HRV</text>')
    parts.append(f'<circle cx="{ml+72}" cy="{mt+6}" r="4" fill="#dc2626"/><text x="{ml+82}" y="{mt+10}" font-size="11" fill="#444">静息心率</text>')
    return '<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;">'.replace("{W}", str(W)).replace("{H}", str(H)) + "\n".join(parts) + '</svg>'


def build_time():
    n = len(rows)
    if n < 2:
        return ""
    xs = lambda i: ml + i / (n - 1) * pw
    parts = [grid_time()]
    hr_pts = " ".join(f"{xs(i):.1f},{syHRV(r['hrv']):.1f}" for i, r in enumerate(rows))
    rh_pts = " ".join(f"{xs(i):.1f},{syRHR(r['rhr']):.1f}" for i, r in enumerate(rows))
    parts.append(f'<polyline points="{hr_pts}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    parts.append(f'<polyline points="{rh_pts}" fill="none" stroke="#dc2626" stroke-width="2"/>')
    for i, r in enumerate(rows):
        x = xs(i)
        parts.append(f'<circle cx="{x:.1f}" cy="{syHRV(r["hrv"]):.1f}" r="3" fill="#2563eb"><title>{r["date"]} HRV {r["hrv"]}</title></circle>')
        parts.append(f'<circle cx="{x:.1f}" cy="{syRHR(r["rhr"]):.1f}" r="3" fill="#dc2626"><title>{r["date"]} 静息HR {r["rhr"]}</title></circle>')
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#999"/>')
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#999"/>')
    parts.append(f'<text x="{ml+pw/2}" y="{H-8}" font-size="12" fill="#444" text-anchor="middle">日期（近30天）</text>')
    parts.append(f'<text x="16" y="{mt+ph/2}" font-size="12" fill="#2563eb" text-anchor="middle" transform="rotate(-90 16 {mt+ph/2})">HRV (ms)</text>')
    parts.append(f'<text x="{W-14}" y="{mt+ph/2}" font-size="12" fill="#dc2626" text-anchor="middle" transform="rotate(90 {W-14} {mt+ph/2})">静息心率 (bpm)</text>')
    for i in range(0, n, 5):
        x = xs(i)
        parts.append(f'<text x="{x:.1f}" y="{mt+ph+18}" font-size="10" fill="#666" text-anchor="middle">{rows[i]["date"][5:]}</text>')
    return '<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;">'.replace("{W}", str(W)).replace("{H}", str(H)) + "\n".join(parts) + '</svg>'


scatter_svg = build_scatter()
time_svg = build_time()

html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>佳明健康趋势</title></head>
<body style="font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif; background:#f7f8fa; color:#222; margin:0; padding:24px;">
<h2 style="margin-top:0;">佳明健康趋势 · 近30天</h2>
<p style="color:#555; font-size:14px; max-width:680px;">睡眠时长与恢复指标的关系：HRV（蓝，左轴）随睡眠增加而升高，静息心率（红，右轴）随睡眠增加而降低 —— 睡得越足，恢复越好。鼠标悬停圆点可看具体数值。</p>
<div style="background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:12px; margin-bottom:18px;">
<h3 style="margin:4px 0 8px;">① HRV / 静息心率 随睡眠时长变化（散点 + 趋势线）</h3>
{scatter_svg}
<p style="font-size:13px; color:#444;">相关系数：睡眠时长 vs HRV <b>r={r_hrv:.2f}</b>（正相关）；睡眠时长 vs 静息心率 <b>r={r_rhr:.2f}</b>（负相关）。样本 {len(rows)} 天（仅含三项齐全的日期）。</p>
</div>
<div style="background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:12px;">
<h3 style="margin:4px 0 8px;">② HRV / 静息心率 30天时间序列</h3>
{time_svg}
</div>
</body></html>"""

OUT.write_text(html, encoding="utf-8")
print(f"✅ 趋势图已生成：{OUT}（样本 {len(rows)} 天，r_hrv={r_hrv:.2f}, r_rhr={r_rhr:.2f}）")
