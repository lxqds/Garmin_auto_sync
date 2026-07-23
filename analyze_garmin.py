#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin 运动数据分析器 (支持 .tcx / .fit)
用法:
  python analyze_garmin.py <文件或目录> [--maxhr 190]
示例:
  python analyze_garmin.py garmin-data/inbox
  python analyze_garmin.py garmin-data/inbox/2026-07-22.tcx --maxhr 188

输出: 单次/批量运动摘要 (时长、距离、配速、平均/最大心率、步频、
      心率区间占比、有氧解耦/心血管漂移)。
"""
import sys
import os
import glob
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime


def local(tag):
    return tag.split('}')[-1] if '}' in tag else tag


def parse_tcx(path):
    tree = ET.parse(path)
    root = tree.getroot()
    recs = []
    for tp in root.iter():
        if local(tp.tag) != 'Trackpoint':
            continue
        rec = {}
        for child in tp:
            n = local(child.tag)
            if n == 'Time':
                rec['time'] = child.text
            elif n == 'HeartRateBpm':
                for v in child.iter():
                    if local(v.tag) == 'Value' and v.text is not None:
                        rec['hr'] = float(v.text)
            elif n == 'DistanceMeters':
                rec['dist'] = float(child.text)
            elif n == 'Cadence':
                rec['cad'] = float(child.text)
            elif n == 'Extensions':
                for e in child.iter():
                    ln = local(e.tag)
                    if ln in ('RunCadence', 'Cadence') and e.text is not None:
                        rec['cad'] = float(e.text)
                    if ln == 'Speed' and e.text is not None:
                        rec['speed'] = float(e.text)
        if 'time' in rec:
            recs.append(rec)
    return recs


def parse_fit(path):
    from fitparse import Activity
    act = Activity(path)
    recs = []
    for msg in act.get_messages('record'):
        rec = {}
        for field in msg:
            n = field.name
            v = field.value
            if v is None:
                continue
            if n in ('heart_rate',):
                rec['hr'] = float(v)
            elif n == 'distance':
                rec['dist'] = float(v)
            elif n in ('cadence', 'running_cadence'):
                rec['cad'] = float(v)
            elif n == 'timestamp':
                rec['time'] = str(v)
            elif n == 'speed':
                rec['speed'] = float(v)
        if 'time' in rec:
            recs.append(rec)
    return recs


def parse_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.tcx':
        return parse_tcx(path)
    elif ext == '.fit':
        return parse_fit(path)
    else:
        return None


def to_dt(s):
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def analyze(recs, maxhr=None):
    hr = [r['hr'] for r in recs if 'hr' in r]
    dist = [r['dist'] for r in recs if 'dist' in r]
    cad = [r['cad'] for r in recs if 'cad' in r]
    times = [to_dt(r['time']) for r in recs if 'time' in r]
    valid = [i for i, t in enumerate(times) if t]
    if not valid:
        return None
    t0, t1 = times[valid[0]], times[valid[-1]]
    duration = (t1 - t0).total_seconds()
    if duration <= 0:
        return None
    total_dist = 0.0
    if len(dist) >= 2:
        total_dist = max(dist) - min(dist)
    pace = (duration / 60.0 / (total_dist / 1000.0)) if total_dist > 0 else None
    avg_hr = sum(hr) / len(hr) if hr else None
    max_hr = max(hr) if hr else None
    avg_cad = sum(cad) / len(cad) if cad else None

    # 心率区间占比 (%HRmax)
    zones = None
    if maxhr and hr:
        bands = [(0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 2.0)]
        counts = [0] * len(bands)
        for h in hr:
            p = h / maxhr
            for i, (lo, hi) in enumerate(bands):
                if lo <= p < hi:
                    counts[i] += 1
                    break
        zones = [c / len(hr) * 100 for c in counts]

    # 有氧解耦 / 心血管漂移: 按时间对半分
    decoup = None
    if len(hr) >= 4:
        mid = len(hr) // 2
        h1, h2 = hr[:mid], hr[mid:]
        d1, d2 = dist[:mid], dist[mid:]
        if d1 and d2 and max(d1) > min(d1) and max(d2) > min(d2):
            pace1 = (max(d1) - min(d1)) / 1000.0
            pace2 = (max(d2) - min(d2)) / 1000.0
            if pace1 > 0 and pace2 > 0:
                hr1, hr2 = sum(h1) / len(h1), sum(h2) / len(h2)
                # 解耦% = (HR2/HR1)/(pace2/pace1) - 1 ; pace 用 m/s
                v1, v2 = pace1, pace2
                decoup = (hr2 / hr1) / (v2 / v1) - 1
                decoup_hr = (hr1, hr2)
                decoup_pace = (pace1, pace2)

    return {
        'duration': duration,
        'distance_km': total_dist / 1000.0 if total_dist else 0,
        'pace_min_km': pace,
        'avg_hr': avg_hr,
        'max_hr': max_hr,
        'avg_cad': avg_cad,
        'zones': zones,
        'decoup': decoup,
        'decoup_hr': decoup_hr if decoup is not None else None,
        'decoup_pace': decoup_pace if decoup is not None else None,
        'n': len(recs),
    }


def fmt_pace(p):
    if not p:
        return '—'
    m = int(p)
    s = int(round((p - m) * 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}/km"


def report(path, a, maxhr):
    name = os.path.basename(path)
    lines = [f"📄 {name}"]
    if not a:
        lines.append("  (无法解析或无有效轨迹点)")
        return "\n".join(lines)
    lines.append(f"  时长      : {int(a['duration']//60)}分{int(a['duration']%60)}秒")
    lines.append(f"  距离      : {a['distance_km']:.2f} km")
    lines.append(f"  平均配速  : {fmt_pace(a['pace_min_km'])}")
    if a['avg_hr']:
        lines.append(f"  平均心率  : {a['avg_hr']:.0f} bpm  (最大 {a['max_hr']:.0f})")
    if a['avg_cad']:
        lines.append(f"  平均步频  : {a['avg_cad']:.0f} spm")
    if a['zones']:
        znames = ['Z1<60%', 'Z2 60-70%', 'Z3 70-80%', 'Z4 80-90%', 'Z5>90%']
        zline = "  ".join(f"{znames[i]}:{a['zones'][i]:.0f}%" for i in range(5))
        lines.append(f"  心率区间  : {zline}")
    if a['decoup'] is not None:
        dh = a['decoup_hr']
        dp = a['decoup_pace']
        verdict = "优秀(有氧基础好)" if a['decoup'] < 0.05 else ("正常" if a['decoup'] < 0.10 else "偏高,注意补水/强度")
        lines.append(f"  有氧解耦  : {a['decoup']*100:+.1f}%  (前段HR{dh[0]:.0f}/后段HR{dh[1]:.0f}) -> {verdict}")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--maxhr', type=float, default=None)
    args = ap.parse_args()
    if os.path.isdir(args.path):
        files = sorted(glob.glob(os.path.join(args.path, '*.tcx')) +
                       glob.glob(os.path.join(args.path, '*.fit')))
        if not files:
            print(f"目录 {args.path} 下没有 .tcx/.fit 文件")
            return
        print(f"=== 批量分析: {len(files)} 个文件 ===\n")
        for f in files:
            a = analyze(parse_file(f) or [], args.maxhr)
            print(report(f, a, args.maxhr))
    else:
        a = analyze(parse_file(args.path) or [], args.maxhr)
        print(report(args.path, a, args.maxhr))


if __name__ == '__main__':
    main()
