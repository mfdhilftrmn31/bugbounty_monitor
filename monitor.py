import requests
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID        = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE     = 'known_programs.json'
BASE_URL       = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data"
HEADERS        = {'User-Agent': 'Mozilla/5.0'}

# ──────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print(f"[TELEGRAM ERR] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {e}")

# ──────────────────────────────────────────────
# State file
# ──────────────────────────────────────────────
def load_known():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None

def save_known(data):
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ──────────────────────────────────────────────
# Fetch helper
# ──────────────────────────────────────────────
def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

# ──────────────────────────────────────────────
# Scoring helpers — HackerOne
# Proxy "active/fresh": managed + high severity + response cepat
# ──────────────────────────────────────────────
SEV_MAP = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}

def h1_severity_and_scope(p):
    best  = 0
    count = 0
    for t in p.get('targets', {}).get('in_scope', []):
        best = max(best, SEV_MAP.get(t.get('max_severity'), 0))
        count += 1
    return best, count

def h1_score(p):
    sev, _     = h1_severity_and_scope(p)
    resp_eff   = p.get('response_efficiency_percentage') or 0
    avg_bounty = p.get('average_time_to_bounty_awarded') or 9999
    managed    = 1 if p.get('managed_program') else 0
    return (sev * 1000) + (resp_eff * 10) + (managed * 500) - (avg_bounty / 10)

# ──────────────────────────────────────────────
# HackerOne — bounty + open, sort by score
# ──────────────────────────────────────────────
def get_hackerone(top_n=15):
    result = []
    try:
        data = fetch_json(f"{BASE_URL}/hackerone_data.json")
        candidates = [
            p for p in data
            if p.get('offers_bounties') and p.get('submission_state') == 'open'
        ]
        candidates.sort(key=h1_score, reverse=True)

        sev_label = {4: 'critical', 3: 'high', 2: 'medium', 1: 'low', 0: 'varies'}

        for p in candidates:
            handle   = p.get('handle', '').strip()
            name     = p.get('name') or handle
            url      = p.get('url') or f"https://hackerone.com/{handle}"
            sev, cnt = h1_severity_and_scope(p)
            resp_eff = p.get('response_efficiency_percentage') or 0
            managed  = p.get('managed_program', False)
            reward   = (
                f"Severity: {sev_label.get(sev,'varies')} | "
                f"Response: {resp_eff}% | Scopes: {cnt}"
                + (" | Managed" if managed else "")
            )
            result.append({
                'id': f"h1_{handle}", 'name': name,
                'platform': 'HackerOne', 'url': url,
                'bounty': True, 'reward': reward,
            })
    except Exception as e:
        print(f"[H1 ERROR] {e}")
    return result, result[:top_n]

# ──────────────────────────────────────────────
# Bugcrowd — sort by max_payout desc
# ──────────────────────────────────────────────
def get_bugcrowd(top_n=15):
    result = []
    try:
        data = fetch_json(f"{BASE_URL}/bugcrowd_data.json")
        candidates = sorted(
            [p for p in data if (p.get('max_payout') or 0) > 0],
            key=lambda x: -(x.get('max_payout') or 0)
        )
        for p in candidates:
            name = (p.get('name') or '').strip()
            url  = (p.get('url')  or '').strip()
            if not name or not url:
                continue
            max_payout = p.get('max_payout') or 0
            managed    = p.get('managed_by_bugcrowd', False)
            slug       = url.rstrip('/').split('/')[-1]
            reward     = f"Up to ${max_payout:,}" + (" | Managed" if managed else "")
            result.append({
                'id': f"bc_{slug}", 'name': name,
                'platform': 'Bugcrowd', 'url': url,
                'bounty': True, 'reward': reward,
            })
    except Exception as e:
        print(f"[BC ERROR] {e}")
    return result, result[:top_n]

# ──────────────────────────────────────────────
# Intigriti — open + bounty, sort by max_bounty desc
# ──────────────────────────────────────────────
def get_intigriti(top_n=15):
    result = []
    try:
        data = fetch_json(f"{BASE_URL}/intigriti_data.json")

        def _max(p):
            mb = p.get('max_bounty') or {}
            return mb.get('value', 0) if isinstance(mb, dict) else 0

        def _min(p):
            mb = p.get('min_bounty') or {}
            return mb.get('value', 0) if isinstance(mb, dict) else 0

        def _cur(p):
            mb = p.get('max_bounty') or {}
            return mb.get('currency', 'EUR') if isinstance(mb, dict) else 'EUR'

        candidates = sorted(
            [p for p in data if p.get('status') == 'open' and _max(p) > 0],
            key=_max, reverse=True
        )
        for p in candidates:
            handle = (p.get('handle') or '').strip()
            name   = (p.get('name')   or handle).strip()
            url    = (p.get('url')    or '').strip()
            if not handle or not url:
                continue
            mn     = _min(p)
            mx     = _max(p)
            cur    = _cur(p)
            reward = f"{mn:,}–{mx:,} {cur}" if mn > 0 else f"Up to {mx:,} {cur}"
            result.append({
                'id': f"inti_{handle}", 'name': name,
                'platform': 'Intigriti', 'url': url,
                'bounty': True, 'reward': reward,
            })
    except Exception as e:
        print(f"[INTI ERROR] {e}")
    return result, result[:top_n]

# ──────────────────────────────────────────────
# Build pesan notif program baru (individual)
# ──────────────────────────────────────────────
def build_message(p):
    icon = {'HackerOne': '🔴', 'Bugcrowd': '🟡', 'Intigriti': '🔵'}.get(p['platform'], '⚪')
    ts   = datetime.now().strftime('%d-%m-%Y %H:%M')
    url  = p['url']
    return (
        f"🚨 <b>Program Bug Bounty Baru!</b>\n\n"
        f"🏢 <b>Nama     :</b> {p['name']}\n"
        f"{icon} <b>Platform :</b> {p['platform']}\n"
        f"💵 <b>Reward   :</b> 💰 {p['reward']}\n"
        f"🔗 <b>Link     :</b> <a href=\"{url}\">{url}</a>\n\n"
        f"⏰ {ts} WIB"
    )

# ──────────────────────────────────────────────
# Kirim top 15 dalam 1 pesan per platform
# ──────────────────────────────────────────────
def send_top_batch(programs, platform):
    icon = {'HackerOne': '🔴', 'Bugcrowd': '🟡', 'Intigriti': '🔵'}.get(platform, '⚪')
    ts   = datetime.now().strftime('%d-%m-%Y %H:%M')

    lines = [f"{icon} <b>Top {len(programs)} {platform} — Active Programs</b>\n"]
    for i, p in enumerate(programs, 1):
        lines.append(f"{i}. <a href=\"{p['url']}\">{p['name']}</a>")
        lines.append(f"   💰 {p['reward']}\n")
    lines.append(f"⏰ {ts} WIB")

    send_telegram("\n".join(lines))

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    known     = load_known()
    first_run = known is None
    if first_run:
        known = {}

    all_h1,   top_h1   = get_hackerone(top_n=15)
    all_bc,   top_bc   = get_bugcrowd(top_n=15)
    all_inti, top_inti = get_intigriti(top_n=15)
    all_programs = all_h1 + all_bc + all_inti

    print(f"Fetched — H1: {len(all_h1)} | BC: {len(all_bc)} | Inti: {len(all_inti)}")
    print(f"Top 15  — H1: {len(top_h1)} | BC: {len(top_bc)} | Inti: {len(top_inti)}")

    if first_run:
        for p in all_programs:
            known[p['id']] = {k: p[k] for k in ('name', 'platform', 'url', 'bounty', 'reward')}

        send_telegram(
            f"✅ <b>Bug Bounty Monitor Aktif!</b>\n\n"
            f"📊 <b>Total Baseline:</b> {len(known)} program\n"
            f"🔴 HackerOne : {len(all_h1)} program\n"
            f"🟡 Bugcrowd  : {len(all_bc)} program\n"
            f"🔵 Intigriti : {len(all_inti)} program\n\n"
            f"⬇️ Mengirim Top 15 per platform...\n"
            f"⏰ Auto-cek setiap 30 menit"
        )

        send_top_batch(top_h1,   'HackerOne')
        send_top_batch(top_bc,   'Bugcrowd')
        send_top_batch(top_inti, 'Intigriti')

        print(f"\nBaseline tersimpan: {len(known)} program")

    else:
        new_programs = []
        for p in all_programs:
            if p['id'] not in known:
                new_programs.append(p)
                known[p['id']] = {k: p[k] for k in ('name', 'platform', 'url', 'bounty', 'reward')}

        if new_programs:
            print(f"\nProgram baru: {len(new_programs)}")
            for p in new_programs:
                print(f"  → {p['name']} ({p['platform']}) | {p['reward']}")
                send_telegram(build_message(p))
        else:
            print(f"\nTidak ada program baru. Total tracked: {len(known)}")

    save_known(known)

if __name__ == '__main__':
    main()
