#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
strava_sync.py — 合规自动拉取 Strava 上的运动数据，落进 inbox/ 供分析。

链路:  Garmin Connect ──(官方同步)──▶ Strava ──(OAuth API)──▶ 本程序 ──▶ garmin-data/inbox/ ──▶ analyze_garmin.py

为什么合规:
  - 不碰 Garmin 账号密码，不走非官方接口
  - 用 Strava 官方 OAuth 2.0，权限仅 activity:read（只读运动数据）
  - token 存在本地保密文件，不进代码、不进 git

用法:
  python strava_sync.py auth            # 首次授权（会生成配置模板并引导拿 code）
  python strava_sync.py fetch           # 拉取新活动 -> inbox/ -> 自动分析
  python strava_sync.py fetch --days 14 # 只拉最近 14 天（首次/补历史用）
  python strava_sync.py fetch --after 2026-07-01   # 拉某天之后的
  python strava_sync.py status          # 看 token 是否有效、上次拉取时间
  python strava_sync.py test            # 验证配置+token+一次 API 调用

依赖: requests（managed venv 已装）
"""
import sys
import os
import io
import json
import time
import glob
import argparse
import zipfile
import subprocess
import datetime
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
GD = BASE / "garmin-data"
INBOX = GD / "inbox"
CONFIG = GD / ".strava_config.json"      # 含 client_id / client_secret（机密）
TOKENS = GD / ".strava_tokens.json"      # 含 access / refresh token（机密）
STATE = GD / ".strava_state.json"        # 含 last_fetch_epoch / downloaded_ids（非机密）

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API = "https://www.strava.com/api/v3"
REDIRECT = "http://localhost"            # Strava 白名单回调，本地用最方便
SCOPE = "activity:read"                  # 只读公开/关注者活动；含"仅自己"请改 activity:read_all
DEFAULT_MAXHR = 200

TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"


# ----------------------------- 基础工具 -----------------------------
def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config():
    """读取 client_id/secret；不存在则生成模板并指引。"""
    if not CONFIG.exists():
        save_json(CONFIG, {"client_id": "在此填写", "client_secret": "在此填写"})
        print(f"未找到配置，已生成模板: {CONFIG}")
        print("请到 https://www.strava.com/settings/api 创建应用，把 client_id / client_secret 填进去后重跑。")
        sys.exit(1)
    cfg = load_json(CONFIG, {})
    if not cfg.get("client_id") or str(cfg.get("client_id")).strip() in ("在此填写", ""):
        print(f"请在 {CONFIG} 中填入真实的 client_id / client_secret 后重跑。")
        sys.exit(1)
    return cfg


def api_get(url, token, params=None, retries=4):
    """带 429 退避的 GET。"""
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            if i == retries - 1:
                raise
            time.sleep(5)
            continue
        if r.status_code == 429:
            wait = 15 * (i + 1)
            print(f"  ⏳ 触发限流(429)，{wait}s 后重试…")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("Strava API 多次限流，放弃本次请求")


# ----------------------------- 鉴权 -----------------------------
def cmd_auth():
    cfg = load_config()
    url = (f"{AUTH_URL}?client_id={cfg['client_id']}"
           f"&response_type=code&redirect_uri={REDIRECT}"
           f"&scope={SCOPE}&approval_prompt=force")
    print("请在本机浏览器打开下面的链接并完成授权：\n")
    print("  " + url + "\n")
    print(f"授权后 Strava 会跳转到  {REDIRECT}?code=XXXX&scope=...")
    print("（localhost 没有服务，页面可能显示无法连接——没关系，只需从地址栏复制 code= 后面那段）\n")
    code = input("把 code 粘贴到这里: ").strip()
    if not code:
        print("未输入 code，已退出。")
        sys.exit(1)
    r = requests.post(TOKEN_URL, data={
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
    }, timeout=30)
    r.raise_for_status()
    d = r.json()
    save_json(TOKENS, {
        "access_token": d["access_token"],
        "refresh_token": d["refresh_token"],
        "expires_at": d.get("expires_at", int(time.time()) + 3600),
    })
    print("\n✅ 授权成功，token 已保存到", TOKENS)
    print("现在可以运行:  python strava_sync.py fetch")


def refresh_token():
    cfg = load_config()
    toks = load_json(TOKENS, {})
    r = requests.post(TOKEN_URL, data={
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": toks["refresh_token"],
    }, timeout=30)
    r.raise_for_status()
    d = r.json()
    new = {
        "access_token": d["access_token"],
        "refresh_token": d.get("refresh_token", toks["refresh_token"]),  # Strava 会轮换 refresh
        "expires_at": d.get("expires_at", int(time.time()) + 3600),
    }
    save_json(TOKENS, new)
    return new["access_token"]


def ensure_token():
    """返回有效的 access_token；必要时自动刷新。"""
    toks = load_json(TOKENS, {})
    if not toks.get("refresh_token"):
        print("尚未授权，请先运行: python strava_sync.py auth")
        sys.exit(1)
    expires = int(toks.get("expires_at", 0))
    if expires - 60 > time.time():
        return toks["access_token"]
    print("  🔄 access token 过期，自动刷新…")
    return refresh_token()


# ----------------------------- 下载活动原始文件 -----------------------------
def _write_inbox(act, ext, content):
    start = (act.get("start_date_local") or act.get("start_date") or "")[:19]
    start = start.replace(":", "-").replace("T", "_")
    name = f"strava_{act['id']}_{start}.{ext}"
    p = INBOX / name
    p.write_bytes(content)
    return p


def _save_original_response(r, act):
    """把 export_original 的响应（可能是 zip 或单文件）落盘，返回路径。"""
    cd = r.headers.get("Content-Disposition", "")
    fname = ""
    if "filename=" in cd:
        fname = cd.split("filename=")[-1].strip().strip('"').strip("'")
    ctype = r.headers.get("Content-Type", "")
    data = r.content

    is_zip = fname.lower().endswith(".zip") or "zip" in ctype.lower() or data[:2] == b"PK"
    if is_zip:
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            for n in z.namelist():
                low = n.lower()
                if low.endswith((".fit", ".tcx", ".gpx")):
                    return _write_inbox(act, low.rsplit(".", 1)[-1], z.read(n))
        except zipfile.BadZipFile:
            pass
    # 单文件
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "fit"
    if ext not in ("fit", "tcx", "gpx"):
        ext = "fit"
    return _write_inbox(act, ext, data)


def download_original(act, token):
    aid = act["id"]
    # 1) API 端点
    try:
        r = api_get(f"{API}/athlete/activities/{aid}/export_original", token)
        if r.status_code == 200 and len(r.content) > 0:
            return _save_original_response(r, act)
    except Exception as e:
        print(f"  (export_original API 失败: {e})")
    # 2) 网站端点（同样可带 Bearer）
    try:
        r = api_get(f"https://www.strava.com/activities/{aid}/export_original", token)
        if r.status_code == 200 and len(r.content) > 0:
            return _save_original_response(r, act)
    except Exception as e:
        print(f"  (export_original web 失败: {e})")
    # 3) 兜底：用 streams 合成 TCX（保证至少有心率/距离/配速）
    return build_tcx_from_streams(act, token)


def build_tcx_from_streams(act, token):
    """当 export_original 不可用时，用 /streams 接口合成标准 TCX。"""
    keys = "time,distance,heartrate,velocity_smooth,cadence,altitude"
    r = api_get(f"{API}/activities/{act['id']}/streams", token,
                params={"keys": keys, "key_by_type": "true"})
    streams = r.json()
    if "time" not in streams or not streams["time"].get("data"):
        print(f"  (活动 {act['id']} 无可用 stream，跳过)")
        return None
    t = streams["time"]["data"]
    dist = streams.get("distance", {}).get("data", [None] * len(t))
    hr = streams.get("heartrate", {}).get("data", [None] * len(t))
    cad = streams.get("cadence", {}).get("data", [None] * len(t))
    start_iso = act.get("start_date") or act.get("start_date_local")
    try:
        base = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except Exception:
        base = datetime.datetime.now(datetime.timezone.utc)

    def iso(off):
        return (base + datetime.timedelta(seconds=off)).strftime("%Y-%m-%dT%H:%M:%SZ")

    sport = (act.get("type") or "Run").lower()
    sport = "Biking" if sport == "ride" else ("Running" if sport == "run" else "Other")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<TrainingCenterDatabase xmlns="{TCX_NS}">',
        "  <Activities>",
        f'    <Activity Sport="{sport}">',
        f'      <Id>{iso(0)}</Id>',
        f'      <Lap StartTime="{iso(0)}">',
        "        <Track>",
    ]
    for i in range(len(t)):
        lines.append("          <Trackpoint>")
        lines.append(f"            <Time>{iso(t[i])}</Time>")
        if dist[i] is not None:
            lines.append(f"            <DistanceMeters>{dist[i]}</DistanceMeters>")
        if hr[i] is not None:
            lines.append(f"            <HeartRateBpm><Value>{int(hr[i])}</Value></HeartRateBpm>")
        if cad[i] is not None:
            lines.append(f"            <Cadence>{int(cad[i])}</Cadence>")
        lines.append("          </Trackpoint>")
    lines += [
        "        </Track>",
        "      </Lap>",
        "    </Activity>",
        "  </Activities>",
        "</TrainingCenterDatabase>",
    ]
    content = ("\n".join(lines)).encode("utf-8")
    return _write_inbox(act, "tcx", content)


# ----------------------------- 拉取主流程 -----------------------------
def cmd_fetch(args):
    token = ensure_token()
    state = load_json(STATE, {})
    after = None
    if args.after:
        after = int(datetime.datetime.fromisoformat(args.after).timestamp())
    elif args.days:
        after = int(time.time()) - args.days * 86400
    elif state.get("last_fetch_epoch"):
        after = state["last_fetch_epoch"]
    if after is None:
        after = int(time.time()) - 30 * 86400  # 默认最近 30 天

    print(f"拉取 {datetime.datetime.utcfromtimestamp(after).strftime('%Y-%m-%d')} 之后的活动…")
    acts = []
    page = 1
    while True:
        r = api_get(f"{API}/athlete/activities", token,
                    params={"after": after, "per_page": 50, "page": page})
        batch = r.json()
        if not batch:
            break
        acts.extend(batch)
        if len(batch) < 50:
            break
        page += 1
        time.sleep(1)

    downloaded = set(str(x) for x in state.get("downloaded_ids", []))
    new = [a for a in acts if str(a["id"]) not in downloaded]
    new.sort(key=lambda a: a.get("start_date", ""))
    if not new:
        print("✅ 没有新活动。")
    else:
        print(f"发现 {len(new)} 个新活动，开始下载原始文件：")
        for a in new:
            try:
                p = download_original(a, token)
            except Exception as e:
                print(f"  ✗ {a['id']} {a.get('name')} 下载失败: {e}")
                continue
            if p:
                downloaded.add(str(a["id"]))
                print(f"  + {a['id']} 《{a.get('name')}》 -> {p.name}")
                time.sleep(1)

    state["downloaded_ids"] = sorted(downloaded, key=lambda x: int(x))
    state["last_fetch_epoch"] = int(time.time())
    save_json(STATE, state)

    run_analysis(args.maxhr)


def run_analysis(maxhr):
    wa = BASE / "watch_and_analyze.py"
    if not wa.exists():
        print("⚠️ 未找到 watch_and_analyze.py，跳过自动分析。")
        return
    cmd = [sys.executable, str(wa), "--once", "--maxhr", str(maxhr)]
    print("\n▶ 运行自动分析…")
    subprocess.run(cmd, cwd=str(BASE))


# ----------------------------- 其他命令 -----------------------------
def cmd_status():
    toks = load_json(TOKENS, {})
    cfg = load_json(CONFIG, {})
    if not cfg.get("client_id"):
        print("配置未就绪，请先运行 auth。")
        return
    if not toks.get("refresh_token"):
        print("未授权，请运行: python strava_sync.py auth")
        return
    exp = int(toks.get("expires_at", 0))
    left = exp - int(time.time())
    print(f"access token: {'有效' if left > 60 else '已过期(下次 fetch 会自动刷新)'}"
          f"（剩余 {left}s）" if left > 0 else "已过期")
    state = load_json(STATE, {})
    lf = state.get("last_fetch_epoch")
    print(f"已下载活动数: {len(state.get('downloaded_ids', []))}")
    if lf:
        print(f"上次拉取: {datetime.datetime.utcfromtimestamp(lf).strftime('%Y-%m-%d %H:%M UTC')}")


def cmd_test():
    cfg = load_config()
    token = ensure_token()
    r = api_get(f"{API}/athlete", token)
    me = r.json()
    print("✅ API 连通正常。")
    print(f"  athlete id : {me.get('id')}")
    print(f"  firstname  : {me.get('firstname')} {me.get('lastname')}")
    print(f"  今日限流   : {r.headers.get('X-RateLimit-Usage')} / {r.headers.get('X-RateLimit-Limit')}")


def main():
    ap = argparse.ArgumentParser(description="Strava 运动数据合规拉取 (Garmin→Strava→本地分析)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("auth", help="首次 OAuth 授权")
    pf = sub.add_parser("fetch", help="拉取新活动并自动分析")
    pf.add_argument("--days", type=int, default=None, help="只拉最近 N 天")
    pf.add_argument("--after", type=str, default=None, help="拉该日期(YYYY-MM-DD)之后的")
    pf.add_argument("--maxhr", type=float, default=DEFAULT_MAXHR, help="最大心率(默认200)")
    sub.add_parser("status", help="查看 token / 上次拉取状态")
    sub.add_parser("test", help="验证配置与 API 连通")
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    if args.cmd == "auth":
        cmd_auth()
    elif args.cmd == "fetch":
        cmd_fetch(args)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "test":
        cmd_test()


if __name__ == "__main__":
    main()
