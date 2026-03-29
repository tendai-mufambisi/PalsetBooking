import requests
from pathlib import Path
import os
from urllib.parse import urlencode

BASE = Path(__file__).resolve().parent.parent
# load .env key
env = {}
env_file = BASE / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k,v = line.split('=',1)
            env[k.strip()] = v.strip().strip("'\"")

KEY = env.get('PAYNOW_INTEGRATION_KEY','')
print('Using key:', KEY[:8]+'...' if KEY else '(none)')

# payload from your logs
payload = {
    'reference': 'f1895f26-97c0-4d47-9cbe-ef9cda1fc395',
    'paynowreference': '35216224',
    'amount': '1324.50',
    'status': 'Awaiting Delivery',
    'pollurl': 'https://www.paynow.co.zw/Interface/CheckPayment/?guid=e88e691a-8791-4eff-9c2b-721a485942d7'
}
# compute sha512 concat end key
import hashlib
concat = f"{payload['reference']}{payload['paynowreference']}{payload['amount']}{payload['status']}{payload['pollurl']}{KEY}"
sign = hashlib.sha512(concat.encode('utf-8')).hexdigest()
payload['hash'] = sign

url = 'http://127.0.0.1:8000/paynow/result/'
print('Posting to', url)
try:
    resp = requests.post(url, data=payload, timeout=10)
    print('HTTP', resp.status_code)
    print(resp.text)
except Exception as e:
    print('Request failed:', e)

