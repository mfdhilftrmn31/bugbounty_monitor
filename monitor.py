import requests
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE = 'known_programs.json'
BASE_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def load_known():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None

def save_known(data):
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def fetch_json(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers, timeout=15)
    return r.json()

def check_hackerone():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/hackerone_data.json")
        for p in data:
            has_bounty = p.get('offers_bounties', False)
            programs.append({
                'id': f"h1_{p.get('handle')}",
                'name': p.get('name', p.get('handle', 'Unknown')),
                'platform': 'HackerOne',
                'url': f"https://hackerone.com/{p.get('handle')}",
                'bounty': has_bounty,
                'reward': 'Ada Bounty' if has_bounty else 'VDP',
                'date': p.get('launched_at', '-')[:10] if p.get('launched_at') else '-'
            })
    except Exception as e:
        print(f"HackerOne error: {e}")
    return programs

def check_bugcrowd():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/bugcrowd_data.json")
        for p in data:
            max_payout = p.get('max_payout', 0) or 0
            programs.append({
                'id': f"bc_{p.get('handle')}",
                'name': p.get('name', p.get('handle', 'Unknown')),
                'platform': 'Bugcrowd',
                'url': f"https://bugcrowd.com/{p.get('handle')}",
                'bounty': max_payout > 0,
                'reward': f"${max_payout:,}" if max_payout > 0 else 'VDP',
                'date': p.get('started_accepting_at', '-')[:10] if p.get('started_accepting_at') else '-'
            })
    except Exception as e:
        print(f"Bugcrowd error: {e}")
    return programs

def check_intigriti():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/intigriti_data.json")
        for p in data:
            handle = p.get('handle', '')
            name = p.get('name', handle)
            url = p.get('url', f"https://app.intigriti.com/programs/{p.get('company_handle','')}/{handle}/detail")

            # bounty berupa dict {"value": 50, "currency": "EUR"}
            min_b = p.get('min_bounty') or {}
            max_b = p.get('max_bounty') or {}
            min_val = min_b.get('value', 0) if isinstance(min_b, dict) else 0
            max_val = max_b.get('value', 0) if isinstance(max_b, dict) else 0
            currency = max_b.get('currency', 'EUR') if isinstance(max_b, dict) else 'EUR'
            has_bounty = max_val > 0 or min_val > 0

            if max_val > 0:
                reward = f"{min_val}-{max_val} {currency}"
            else:
                reward = 'VDP'

            if handle:
                programs.append({
                    'id': f"inti_{handle}",
                    'name': name,
                    'platform': 'Intigriti',
                    'url': url,
                    'bounty': has_bounty,
                    'reward': reward,
                    'date': '-'
                })
    except Exception as e:
        print(f"Intigriti error: {e}")
    return programs

def main():
    known = load_known()
    first_run = known is None

    if first_run:
        known = {}

    h1   = check_hackerone()
    bc   = check_bugcrowd()
    inti = check_intigriti()
    all_programs = h1 + bc + inti

    print(f"HackerOne: {len(h1)} | Bugcrowd: {len(bc)} | Intigriti: {len(inti)}")

    if first_run:
        for p in all_programs:
            known[p['id']] = {
                'name':     p['name'],
                'platform': p['platform'],
                'url':      p['url'],
                'bounty':   p['bounty'],
                'reward':   p.get('reward', '-'),
                'date':     p.get('date', '-')
            }
        send_telegram(
            f"✅ <b>Bug Bounty Monitor Aktif!</b>\n\n"
            f"📊 <b>Total Baseline:</b> {len(known)} program\n"
            f"🔴 HackerOne : {len(h1)} program\n"
            f"🟡 Bugcrowd  : {len(bc)} program\n"
            f"🔵 Intigriti : {len(inti)} program\n\n"
            f"⏰ Cek otomatis setiap 30 menit\n"
            f"🔔 Notif masuk kalau ada program BARU"
        )
        print(f"Baseline tersimpan: {len(known)} program")

    else:
        new_programs = []
        for p in all_programs:
            if p['id'] not in known:
                new_programs.append(p)
                known[p['id']] = {
                    'name':     p['name'],
                    'platform': p['platform'],
                    'url':      p['url'],
                    'bounty':   p['bounty'],
                    'reward':   p.get('reward', '-'),
                    'date':     p.get('date', '-')
                }

        if new_programs:
            print(f"Program baru: {len(new_programs)}")
            for p in new_programs:
                bounty_label = "💰 Ada Bounty" if p['bounty'] else "🎯 VDP (No Bounty)"
                msg = (
                    f"🚨 <b>Program Bug Bounty Baru!</b>\n\n"
                    f"🏢 <b>Nama    :</b> {p['name']}\n"
                    f"📌 <b>Platform:</b> {p['platform']}\n"
                    f"{bounty_label}\n"
                    f"💵 <b>Reward  :</b> {p.get('reward', '-')}\n"
                    f"🔗 <b>Link    :</b> {p['url']}\n"
                    f"📅 <b>Tanggal :</b> {p.get('date', '-')}\n\n"
                    f"⏰ {datetime.now().strftime('%d-%m-%Y %H:%M')} WIB"
                )
                send_telegram(msg)
                print(f"Notif: {p['name']} ({p['platform']})")
        else:
            print(f"Tidak ada program baru. Total: {len(known)}")

    save_known(known)

if __name__ == '__main__':
    main()
