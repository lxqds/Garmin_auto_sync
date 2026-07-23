#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
睡眠质量可视化仪表盘生成器
读取 garmin-data/health_records.json（佳明直连拉取的每日健康数据），
生成 garmin-data/sleep_quality.html：
  - 顶部摘要卡（平均睡眠分 / 平均时长 / 优/良/差夜数 / 最佳&最差夜）
  - 睡眠分期堆叠图（深睡 / 浅睡 / REM / 清醒，按小时）
  - 睡眠质量评分曲线（带 优/良/差 阈值区间）
  - HRV 与静息心率对照（恢复质量语境）
依赖：仅标准库 + ECharts(CDN)。
"""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'garmin-data', 'health_records.json')
OUT = os.path.join(BASE, 'garmin-data', 'sleep_quality.html')


def hms(sec):
    if not sec:
        return 0.0
    return round(sec / 3600.0, 2)


def load():
    with open(SRC, encoding='utf-8') as f:
        data = json.load(f)
    rows = []
    for date, r in data.items():
        if r.get('sleep_score') is None or r.get('sleep_seconds') is None:
            continue
        rows.append({
            'date': date,
            'score': r.get('sleep_score'),
            'total': hms(r.get('sleep_seconds')),
            'deep': hms(r.get('deep_seconds')),
            'light': hms(r.get('light_seconds')),
            'rem': hms(r.get('rem_seconds')),
            'awake': hms(r.get('awake_seconds')),
            'hrv': r.get('hrv_avg'),
            'rhr': r.get('resting_hr'),
        })
    rows.sort(key=lambda x: x['date'])
    return rows


def summarize(rows):
    n = len(rows)
    avg_score = round(sum(r['score'] for r in rows) / n, 1)
    avg_dur = round(sum(r['total'] for r in rows) / n, 2)
    good = sum(1 for r in rows if r['score'] >= 75)
    fair = sum(1 for r in rows if 50 <= r['score'] < 75)
    poor = sum(1 for r in rows if r['score'] < 50)
    best = max(rows, key=lambda r: r['score'])
    worst = min(rows, key=lambda r: r['score'])
    avg_deep = round(sum(r['deep'] for r in rows) / n, 2)
    return {
        'n': n, 'avg_score': avg_score, 'avg_dur': avg_dur,
        'good': good, 'fair': fair, 'poor': poor,
        'best': best, 'worst': worst, 'avg_deep': avg_deep,
    }


def main():
    rows = load()
    if not rows:
        print('没有可用的睡眠数据')
        return
    s = summarize(rows)
    dates = [r['date'][5:] for r in rows]  # MM-DD
    deep = [r['deep'] for r in rows]
    light = [r['light'] for r in rows]
    rem = [r['rem'] for r in rows]
    awake = [r['awake'] for r in rows]
    scores = [r['score'] for r in rows]
    hrv = [r['hrv'] for r in rows]
    rhr = [r['rhr'] for r in rows]

    data_js = json.dumps({
        'dates': dates, 'deep': deep, 'light': light, 'rem': rem,
        'awake': awake, 'scores': scores, 'hrv': hrv, 'rhr': rhr,
    }, ensure_ascii=False)

    html = TEMPLATE.replace('__DATA__', data_js).replace('__SUMMARY__', json.dumps(s, ensure_ascii=False))

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'已生成: {OUT}')
    print(f'  有效睡眠夜: {s["n"]} 天 | 平均睡眠分 {s["avg_score"]} | 平均时长 {s["avg_dur"]}h')
    print(f'  优 {s["good"]} / 良 {s["fair"]} / 差 {s["poor"]} 夜')


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>睡眠质量仪表盘 · 佳明</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: linear-gradient(135deg, #f5f7fa 0%, #e8edf3 100%); color: #2c3e50; padding: 28px; }
  .wrap { max-width: 1080px; margin: 0 auto; }
  h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; color: #1a202c; }
  .sub { color: #718096; font-size: 13px; margin-bottom: 22px; }
  .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }
  .card { background: #fff; border-radius: 16px; padding: 18px 16px; box-shadow: 0 4px 16px rgba(60,80,120,.08); }
  .card .k { font-size: 12px; color: #a0aec0; margin-bottom: 6px; }
  .card .v { font-size: 26px; font-weight: 700; }
  .card .u { font-size: 13px; color: #a0aec0; font-weight: 400; }
  .card.good .v { color: #38a169; }
  .card.warn .v { color: #d69e2e; }
  .card.bad .v { color: #e53e3e; }
  .card.info .v { color: #3182ce; }
  .panel { background: #fff; border-radius: 16px; padding: 18px 16px 8px; box-shadow: 0 4px 16px rgba(60,80,120,.08); margin-bottom: 20px; }
  .panel h2 { font-size: 15px; font-weight: 600; margin-bottom: 6px; color: #2d3748; }
  .panel .hint { font-size: 12px; color: #a0aec0; margin-bottom: 8px; }
  .chart { width: 100%; height: 340px; }
  .legend-note { font-size: 12px; color: #a0aec0; margin: 4px 2px 12px; }
  .footer { text-align: center; color: #cbd5e0; font-size: 12px; margin-top: 8px; }
  @media (max-width: 720px){ .cards { grid-template-columns: repeat(2,1fr);} }
</style>
</head>
<body>
<div class="wrap">
  <h1>🌙 睡眠质量仪表盘</h1>
  <div class="sub" id="subtitle"></div>

  <div class="cards" id="cards"></div>

  <div class="panel">
    <h2>睡眠分期构成（小时）</h2>
    <div class="hint">深睡 + 浅睡 + REM + 清醒 = 当夜总卧床时长。深睡占比越高通常恢复越好。</div>
    <div id="stages" class="chart"></div>
  </div>

  <div class="panel">
    <h2>睡眠质量评分</h2>
    <div class="hint">阈值：≥75 优 · 50–74 良 · &lt;50 差。曲线为每日睡眠分。</div>
    <div id="score" class="chart"></div>
  </div>

  <div class="panel">
    <h2>恢复质量语境：HRV 与静息心率</h2>
    <div class="hint">HRV（蓝，左轴）越高、静息心率（红，右轴）越低，通常表示身体恢复越充分。</div>
    <div id="recovery" class="chart"></div>
  </div>

  <div class="footer">数据来源：佳明直连（中国区 garmin.cn）· 自动同步生成</div>
</div>

<script>
const D = __DATA__;
const S = __SUMMARY__;
document.getElementById('subtitle').textContent =
  `统计区间 ${D.dates[0]} ~ ${D.dates[D.dates.length-1]} ｜ 有效睡眠夜 ${S.n} 天`;

// ---- 摘要卡 ----
const cards = [
  {k:'平均睡眠分', v:S.avg_score, u:'/100', cls: S.avg_score>=75?'good':(S.avg_score>=50?'warn':'bad')},
  {k:'平均睡眠时长', v:S.avg_dur, u:'h', cls:'info'},
  {k:'优/良/差 夜数', v:`${S.good}/${S.fair}/${S.poor}`, u:'', cls:'good'},
  {k:'平均深睡', v:S.avg_deep, u:'h', cls:'info'},
];
document.getElementById('cards').innerHTML = cards.map(c=>
  `<div class="card ${c.cls}"><div class="k">${c.k}</div><div class="v">${c.v}<span class="u">${c.u}</span></div></div>`
).join('');

const axisStyle = { axisLine:{lineStyle:{color:'#cbd5e0'}}, axisLabel:{color:'#718096'}, splitLine:{lineStyle:{color:'#edf2f7'}} };

// ---- 睡眠分期堆叠 ----
echarts.init(document.getElementById('stages')).setOption({
  tooltip:{trigger:'axis', axisPointer:{type:'shadow'}},
  legend:{data:['深睡','浅睡','REM','清醒'], top:0, textStyle:{color:'#4a5568'}},
  grid:{left:48, right:20, top:38, bottom:30},
  xAxis:{type:'category', data:D.dates, ...axisStyle},
  yAxis:{type:'value', name:'小时', ...axisStyle},
  series:[
    {name:'深睡', type:'bar', stack:'s', data:D.deep, itemStyle:{color:'#5a67d8', borderRadius:[3,3,0,0]}},
    {name:'浅睡', type:'bar', stack:'s', data:D.light, itemStyle:{color:'#90cdf4'}},
    {name:'REM',  type:'bar', stack:'s', data:D.rem, itemStyle:{color:'#b794f4'}},
    {name:'清醒', type:'bar', stack:'s', data:D.awake, itemStyle:{color:'#fc8181', borderRadius:[0,0,3,3]}},
  ]
});

// ---- 睡眠质量评分曲线 + 阈值带 ----
echarts.init(document.getElementById('score')).setOption({
  tooltip:{trigger:'axis'},
  grid:{left:46, right:20, top:24, bottom:30},
  xAxis:{type:'category', data:D.dates, ...axisStyle},
  yAxis:{type:'value', min:0, max:100, name:'分', ...axisStyle,
    splitLine:{lineStyle:{color:['#fed7d7','#fefcbf','#c6f6d5'][0]}}},
  visualMap:{show:false, type:'continuous', min:0, max:100, dimension:1,
    seriesIndex:0,
    inRange:{color:['#e53e3e','#dd6b20','#d69e2e','#38a169']}},
  series:[{
    type:'line', data:D.scores, smooth:true, symbolSize:7,
    lineStyle:{width:3},
    areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[
      {offset:0,color:'rgba(56,161,105,.28)'},{offset:1,color:'rgba(56,161,105,0)'}])},
    markLine:{silent:true, symbol:'none', lineStyle:{type:'dashed', color:'#a0aec0'},
      data:[{yAxis:75, label:{formatter:'优 75', color:'#38a169'}},
            {yAxis:50, label:{formatter:'良 50', color:'#d69e2e'}}]}
  }]
});

// ---- HRV / 静息心率 ----
echarts.init(document.getElementById('recovery')).setOption({
  tooltip:{trigger:'axis'},
  legend:{data:['HRV','静息心率'], top:0, textStyle:{color:'#4a5568'}},
  grid:{left:46, right:48, top:38, bottom:30},
  xAxis:{type:'category', data:D.dates, ...axisStyle},
  yAxis:[
    {type:'value', name:'HRV(ms)', ...axisStyle},
    {type:'value', name:'静息(bpm)', ...axisStyle, splitLine:{show:false}}
  ],
  series:[
    {name:'HRV', type:'line', smooth:true, data:D.hrv, symbolSize:6, itemStyle:{color:'#3182ce'}, lineStyle:{width:2.5, color:'#3182ce'}},
    {name:'静息心率', type:'line', yAxisIndex:1, smooth:true, data:D.rhr, symbolSize:6, itemStyle:{color:'#e53e3e'}, lineStyle:{width:2.5, color:'#e53e3e'}}
  ]
});

window.addEventListener('resize', ()=>{
  ['stages','score','recovery'].forEach(id=>echarts.getInstanceByDom(document.getElementById(id)).resize());
});
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
