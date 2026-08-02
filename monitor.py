import requests
import json
import os
import hashlib
from datetime import datetime

TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE = 'known_programs.json'

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    requests.post(url, json=payload)

def load_known():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_known(data):
    with open(STATE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def check_hackerone():
    programs = []
    try:
        url = "https://hackerone.com/programs/search?query=type%3Ahackerone&sort=published_at%3Adescending&page=1"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        }
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        for p in data.get('results', []):
            programs.append({
                'id': f"h1_{p.get('handle')}",
                'name': p.get('name', ''),
                'handle': p.get('handle', ''),
                'platform': 'HackerOne',
                'url': f"https://hackerone.com/{p.get('handle')}",
                'bounty': p.get('offers_bounties', False)
            })
    except Exception as e:
        print(f"HackerOne error: {e}")
    return programs

def check_bugcrowd():
    programs = []
    try:
        url = "https://bugcrowd.com/programs.json?sort[]=promoted-desc&hidden[]=false&page=1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        for p in data.get('programs', []):
            programs.append({
                'id': f"bc_{p.get('code')}",
                'name': p.get('name', ''),
                'handle': p.get('code', ''),
                'platform': 'Bugcrowd',
                'url': f"https://bugcrowd.com/{p.get('code')}",
                'bounty': p.get('max_payout', 0) > 0
            })
    except Exception as e:
        print(f"Bugcrowd error: {e}")
    return programs

def check_intigriti():
    programs = []
    try:
        url = "https://api.intigriti.com/core/researcher/programs?limit=20&offset=0&status=open"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        for p in data.get('records', []):
            programs.append({
                'id': f"inti_{p.get('handle')}",
                'name': p.get('name', ''),
                'handle': p.get('handle', ''),
                'platform': 'Intigriti',
                'url': f"https://app.intigriti.com/researcher/programs/{p.get('handle')}",
                'bounty': p.get('maxBounty', {}).get('value', 0) > 0
            })
    except Exception as e:
        print(f"Intigriti error: {e}")
    return programs

def main():
    known = load_known()
    all_programs = []
    all_programs.extend(check_hackerone())
    all_programs.extend(check_bugcrowd())
    all_programs.extend(check_intigriti())

    new_programs = []
    for p in all_programs:
        if p['id'] not in known:
            new_programs.append(p)
            known[p['id']] = {
                'name': p['name'],
                'found_at': datetime.now().isoformat()
            }

    if new_programs:
        for p in new_programs:
            bounty_label = "💰 Ada Bounty" if p['bounty'] else "🎯 VDP (No Bounty)"
            msg = (
                f"🚨 <b>Program Bug Bounty Baru!</b>\n\n"
                f"🏢 <b>Nama:</b> {p['name']}\n"
                f"📌 <b>Platform:</b> {p['platform']}\n"
                f"{bounty_label}\n"
                f"🔗 <b>Link:</b> {p['url']}\n\n"
                f"⏰ {datetime.now().strftime('%d-%m-%Y %H:%M')} WIB"
            )
            send_telegram(msg)
            print(f"Notifikasi terkirim: {p['name']}")
    else:
        print(f"Tidak ada program baru. Total terpantau: {len(known)}")

    save_known(known)

if __name__ == '__main__':
    main()
