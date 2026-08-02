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
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print(f"Telegram HTTP error: {r.status_code} | {r.text[:200]}")
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
    r.raise_for_status()
    return r.json()

def check_hackerone():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/hackerone_data.json")

        # === DEBUG: Print sample raw entry ===
        if data:
            print(f"\n[DEBUG] HackerOne sample keys: {list(data[0].keys())}")
            print(f"[DEBUG] HackerOne sample entry: {json.dumps(data[0], indent=2)[:500]}")

        for p in data:
            handle = p.get('handle', '')
            if not handle:
                continue

            has_bounty = p.get('offers_bounties', False)
            name = p.get('name') or p.get('handle') or 'Unknown'
            url = f"https://hackerone.com/{handle}"

            # Coba ambil max reward dari structured_scopes atau top_level info
            max_reward = 0
            if p.get('structured_scopes'):
                for scope in p['structured_scopes']:
                    mr = scope.get('max_severity') or 0
                    # structured_scopes tidak punya reward — skip
            # Coba dari submission_state / response_efficiency_percentage
            # HackerOne API biasanya tidak expose reward di public data

            if has_bounty:
                reward_str = 'Ada Bounty (lihat di halaman)'
            else:
                reward_str = 'VDP (No Bounty)'

            launched = p.get('launched_at', '')
            date_str = launched[:10] if launched else '-'

            programs.append({
                'id': f"h1_{handle}",
                'name': name,
                'platform': 'HackerOne',
                'url': url,
                'bounty': has_bounty,
                'reward': reward_str,
                'date': date_str
            })
    except Exception as e:
        print(f"HackerOne error: {e}")
    return programs

def check_bugcrowd():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/bugcrowd_data.json")

        # === DEBUG: Print sample raw entry ===
        if data:
            print(f"\n[DEBUG] Bugcrowd sample keys: {list(data[0].keys())}")
            print(f"[DEBUG] Bugcrowd sample entry: {json.dumps(data[0], indent=2)[:500]}")

        for p in data:
            handle = p.get('handle', '')
            if not handle:
                continue

            max_payout = p.get('max_payout', 0) or 0
            name = p.get('name') or handle or 'Unknown'
            url = p.get('program_url') or f"https://bugcrowd.com/{handle}"

            if max_payout > 0:
                reward_str = f"Up to ${max_payout:,}"
            else:
                reward_str = 'VDP (No Bounty)'

            started = p.get('started_accepting_at', '')
            date_str = started[:10] if started else '-'

            programs.append({
                'id': f"bc_{handle}",
                'name': name,
                'platform': 'Bugcrowd',
                'url': url,
                'bounty': max_payout > 0,
                'reward': reward_str,
                'date': date_str
            })
    except Exception as e:
        print(f"Bugcrowd error: {e}")
    return programs

def check_intigriti():
    programs = []
    try:
        data = fetch_json(f"{BASE_URL}/intigriti_data.json")

        # === DEBUG: Print sample raw entry ===
        if data:
            print(f"\n[DEBUG] Intigriti sample keys: {list(data[0].keys())}")
            print(f"[DEBUG] Intigriti sample entry: {json.dumps(data[0], indent=2)[:500]}")

        for p in data:
            handle = p.get('handle', '')
            if not handle:
                continue

            name = p.get('name') or handle or 'Unknown'
            company_handle = p.get('company_handle', '')
            url = p.get('url') or f"https://app.intigriti.com/programs/{company_handle}/{handle}/detail"

            min_b = p.get('min_bounty') or {}
            max_b = p.get('max_bounty') or {}
            min_val = min_b.get('value', 0) if isinstance(min_b, dict) else 0
            max_val = max_b.get('value', 0) if isinstance(max_b, dict) else 0
            currency = max_b.get('currency', 'EUR') if isinstance(max_b, dict) else 'EUR'
            has_bounty = max_val > 0 or min_val > 0

            if max_val > 0:
                reward_str = f"{min_val:,}–{max_val:,} {currency}"
            else:
                reward_str = 'VDP (No Bounty)'

            programs.append({
                'id': f"inti_{handle}",
                'name': name,
                'platform': 'Intigriti',
                'url': url,
                'bounty': has_bounty,
                'reward': reward_str,
                'date': '-'
            })
    except Exception as e:
        print(f"Intigriti error: {e}")
    return programs

def build_notif_message(p):
    """Bangun pesan notifikasi Telegram yang lengkap."""
    bounty_icon = "💰" if p['bounty'] else "🎯"
    bounty_label = f"{bounty_icon} <b>Bounty:</b> {p.get('reward', '-')}"

    platform_icon = {
        'HackerOne': '🔴',
        'Bugcrowd': '🟡',
        'Intigriti': '🔵',
    }.get(p['platform'], '⚪')

    date_str = p.get('date', '-')
    url_str = p.get('url', '-')

    # Validasi URL — pastikan tidak kosong/placeholder
    if not url_str or url_str == '-' or 'None' in url_str:
        url_str = '(URL tidak tersedia)'
        url_line = f"🔗 <b>Link:</b> {url_str}"
    else:
        url_line = f"🔗 <b>Link:</b> <a href=\"{url_str}\">{p['name']}</a>"

    msg = (
        f"🚨 <b>Program Bug Bounty Baru!</b>\n\n"
        f"🏢 <b>Nama     :</b> {p['name']}\n"
        f"{platform_icon} <b>Platform :</b> {p['platform']}\n"
        f"{bounty_label}\n"
        f"📅 <b>Tanggal  :</b> {date_str}\n"
        f"{url_line}\n\n"
        f"⏰ {datetime.now().strftime('%d-%m-%Y %H:%M')} WIB"
    )
    return msg

def main():
    known = load_known()
    first_run = known is None

    if first_run:
        known = {}

    h1   = check_hackerone()
    bc   = check_bugcrowd()
    inti = check_intigriti()
    all_programs = h1 + bc + inti

    print(f"\nHackerOne: {len(h1)} | Bugcrowd: {len(bc)} | Intigriti: {len(inti)}")

    # === DEBUG: Cek sample program sebelum simpan ===
    if all_programs:
        sample = all_programs[0]
        print(f"\n[DEBUG] Sample program parsed:")
        print(f"  name   : {sample['name']}")
        print(f"  url    : {sample['url']}")
        print(f"  reward : {sample['reward']}")
        print(f"  date   : {sample['date']}")
        print(f"  bounty : {sample['bounty']}")

    if first_run:
        for p in all_programs:
            known[p['id']] = {
                'name':     p['name'],
                'platform': p['platform'],
                'url':      p['url'],
                'bounty':   p['bounty'],
                'reward':   p['reward'],
                'date':     p['date']
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
                    'reward':   p['reward'],
                    'date':     p['date']
                }

        if new_programs:
            print(f"Program baru ditemukan: {len(new_programs)}")
            for p in new_programs:
                msg = build_notif_message(p)
                print(f"\n[DEBUG] Notif untuk: {p['name']}")
                print(f"  url    : {p['url']}")
                print(f"  reward : {p['reward']}")
                print(f"  date   : {p['date']}")
                send_telegram(msg)
                print(f"Notif terkirim: {p['name']} ({p['platform']})")
        else:
            print(f"Tidak ada program baru. Total: {len(known)}")

    save_known(known)

if __name__ == '__main__':
    main()
