import requests
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID        = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE     = 'known_programs.json'
BASE_URL       = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data"

HEADERS = {'User-Agent': 'Mozilla/5.0'}

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
# Fetch helpers
# ──────────────────────────────────────────────
def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

# ──────────────────────────────────────────────
# HackerOne
# Data: handle, name, url, offers_bounties
# Reward: tidak ada nominal di public data → tampilkan "Ada Bounty" atau "VDP"
#         + max_severity dari scope sebagai indikator
# ──────────────────────────────────────────────
def check_hackerone():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/hackerone_data.json")
        for p in data:
            handle = p.get('handle', '').strip()
            if not handle:
                continue

            name         = p.get('name') or handle
            url          = p.get('url') or f"https://hackerone.com/{handle}"
            has_bounty   = bool(p.get('offers_bounties'))

            # Cari max_severity tertinggi dari in_scope targets
            severity_map = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1, None: 0}
            max_sev = None
            for t in p.get('targets', {}).get('in_scope', []):
                s = t.get('max_severity')
                if severity_map.get(s, 0) > severity_map.get(max_sev, 0):
                    max_sev = s

            if has_bounty:
                reward = f"💰 Bounty · Max severity: {max_sev or 'varies'}"
            else:
                reward = "🎯 VDP (No Bounty)"

            programs.append({
                'id':       f"h1_{handle}",
                'name':     name,
                'platform': 'HackerOne',
                'url':      url,
                'bounty':   has_bounty,
                'reward':   reward,
                'date':     '-',
            })
    except Exception as e:
        print(f"[H1 ERROR] {e}")
    return programs

# ──────────────────────────────────────────────
# Bugcrowd
# Data: name, url (langsung ada), max_payout
# ──────────────────────────────────────────────
def check_bugcrowd():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/bugcrowd_data.json")
        for p in data:
            name = (p.get('name') or '').strip()
            url  = (p.get('url') or '').strip()
            if not name or not url:
                continue

            max_payout = p.get('max_payout') or 0

            if max_payout > 0:
                reward = f"💰 Up to ${max_payout:,}"
            else:
                reward = "🎯 VDP (No Bounty)"

            # Buat ID dari URL karena tidak ada handle
            slug = url.rstrip('/').split('/')[-1]

            programs.append({
                'id':       f"bc_{slug}",
                'name':     name,
                'platform': 'Bugcrowd',
                'url':      url,
                'bounty':   max_payout > 0,
                'reward':   reward,
                'date':     '-',
            })
    except Exception as e:
        print(f"[BC ERROR] {e}")
    return programs

# ──────────────────────────────────────────────
# Intigriti
# Data: name, url (langsung ada), min_bounty, max_bounty (dict)
# ──────────────────────────────────────────────
def check_intigriti():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/intigriti_data.json")
        for p in data:
            handle = (p.get('handle') or '').strip()
            name   = (p.get('name')   or handle).strip()
            url    = (p.get('url')    or '').strip()

            if not handle or not url:
                continue

            min_b    = p.get('min_bounty') or {}
            max_b    = p.get('max_bounty') or {}
            min_val  = min_b.get('value', 0) if isinstance(min_b, dict) else 0
            max_val  = max_b.get('value', 0) if isinstance(max_b, dict) else 0
            currency = max_b.get('currency', 'EUR') if isinstance(max_b, dict) else 'EUR'
            has_bounty = max_val > 0 or min_val > 0

            if has_bounty:
                if min_val > 0 and max_val > 0:
                    reward = f"💰 {min_val:,}–{max_val:,} {currency}"
                elif max_val > 0:
                    reward = f"💰 Up to {max_val:,} {currency}"
                else:
                    reward = f"💰 Min {min_val:,} {currency}"
            else:
                reward = "🎯 VDP (No Bounty)"

            programs.append({
                'id':       f"inti_{handle}",
                'name':     name,
                'platform': 'Intigriti',
                'url':      url,
                'bounty':   has_bounty,
                'reward':   reward,
                'date':     '-',
            })
    except Exception as e:
        print(f"[INTI ERROR] {e}")
    return programs

# ──────────────────────────────────────────────
# Build Telegram message
# ──────────────────────────────────────────────
def build_message(p):
    icon = {'HackerOne': '🔴', 'Bugcrowd': '🟡', 'Intigriti': '🔵'}.get(p['platform'], '⚪')
    url  = p['url']
    ts   = datetime.now().strftime('%d-%m-%Y %H:%M')

    return (
        f"🚨 <b>Program Bug Bounty Baru!</b>\n\n"
        f"🏢 <b>Nama     :</b> {p['name']}\n"
        f"{icon} <b>Platform :</b> {p['platform']}\n"
        f"💵 <b>Reward   :</b> {p['reward']}\n"
        f"📅 <b>Tanggal  :</b> {p['date']}\n"
        f"🔗 <b>Link     :</b> <a href=\"{url}\">{p['name']}</a>\n\n"
        f"⏰ {ts} WIB"
    )

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    known     = load_known()
    first_run = known is None
    if first_run:
        known = {}

    h1   = check_hackerone()
    bc   = check_bugcrowd()
    inti = check_intigriti()
    all_programs = h1 + bc + inti

    print(f"HackerOne: {len(h1)} | Bugcrowd: {len(bc)} | Intigriti: {len(inti)}")

    # Verifikasi sample output
    if all_programs:
        s = all_programs[0]
        print(f"\nSample [{s['platform']}]")
        print(f"  name  : {s['name']}")
        print(f"  url   : {s['url']}")
        print(f"  reward: {s['reward']}")
        print(f"  date  : {s['date']}")

        # Sample Bugcrowd
        for x in bc[:1]:
            print(f"\nSample [Bugcrowd]")
            print(f"  name  : {x['name']}")
            print(f"  url   : {x['url']}")
            print(f"  reward: {x['reward']}")

        # Sample Intigriti
        for x in inti[:1]:
            print(f"\nSample [Intigriti]")
            print(f"  name  : {x['name']}")
            print(f"  url   : {x['url']}")
            print(f"  reward: {x['reward']}")

    if first_run:
        for p in all_programs:
            known[p['id']] = {k: p[k] for k in ('name','platform','url','bounty','reward','date')}

        send_telegram(
            f"✅ <b>Bug Bounty Monitor Aktif!</b>\n\n"
            f"📊 <b>Total Baseline:</b> {len(known)} program\n"
            f"🔴 HackerOne : {len(h1)} program\n"
            f"🟡 Bugcrowd  : {len(bc)} program\n"
            f"🔵 Intigriti : {len(inti)} program\n\n"
            f"⏰ Cek otomatis setiap 30 menit\n"
            f"🔔 Notif kalau ada program BARU"
        )
        print(f"\nBaseline tersimpan: {len(known)} program")

    else:
        new_programs = []
        for p in all_programs:
            if p['id'] not in known:
                new_programs.append(p)
                known[p['id']] = {k: p[k] for k in ('name','platform','url','bounty','reward','date')}

        if new_programs:
            print(f"\nProgram baru: {len(new_programs)}")
            for p in new_programs:
                msg = build_message(p)
                print(f"  → {p['name']} ({p['platform']}) | {p['reward']} | {p['url']}")
                send_telegram(msg)
        else:
            print(f"\nTidak ada program baru. Total: {len(known)}")

    save_known(known)

if __name__ == '__main__':
    main()
