import httpx
import asyncio
import json
import os
from aiohttp import web

# ==================== CONFIGURATION ====================
# Data from your http_req_r.txt
REFRESH_TOKEN = "AMf-vBxm_XPEx1PsTrSQcxyUEoKJzgaOnM8dAekww6WYUsbWlbyK8Z83oYTavJMv1Su2tcacLk_lHTrju4SVoXCo215zYQi-T_W13jOrp2nBOx1qO2g8UK-vMDhBudlXB-KLm_kxN6pFJuNBdxEvbvCmOs1vQSXg7k7AK1yRAMvuYrN6cwdkqM5IALxCeenDfku2XV9glC9zx-8GeijKPoYQ5fYlL9CQ7rOstBbslS6xTTkQdHnLm3DC8erR4oN9BOJzk1DDTBhxhpWhhk6Ji4coaSjmVxq_dVijq0ERm2KTrV_i8KeuTCdBKbFq8Qf4PxIzSkH-GCpmU06juS5lnnfCvz_vrAIsh15ZCi-FKW4WTUirBmSRmOL8ORKXIpSUOmt0m-JPfkWJQqm3l26e7B8mSqTg1wUw0rwix7hEBzTTu24aWrphoHjfosYmRhzLP5-jFgDcyPMw"
FIREBASE_API_KEY = "AIzaSyBOEnsBy37D8sDpsWvfk5cUdZLaQ6kkCd0"

# Target API Details
POSTBACK_URL = "https://us-central1-gamerush-68528.cloudfunctions.net/playGamesPostback"
OFFER_ID = "6a40fcc3ecd41eccfa879d94" # From your rushus.txt
PORT = int(os.environ.get("PORT", 8080))

class TokenManager:
    def __init__(self):
        self.bearer = None

    async def refresh_now(self, client):
        """Exchanges refresh_token for a fresh Bearer token"""
        url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
        payload = {
            "grantType": "refresh_token",
            "refreshToken": REFRESH_TOKEN
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            r = await client.post(url, json=payload, headers=headers)
            data = r.json()
            self.bearer = data.get("id_token")
            print(f"🔄 Token Refreshed: {self.bearer[:15]}...")
            return self.bearer
        except Exception as e:
            print(f"❌ Refresh Error: {e}")
            return None

token_vault = TokenManager()

# -------------------- EARNING LOOP -------------------- #

async def postback_loop():
    print("🚀 Earning Loop Started (3s Interval)")
    
    async with httpx.AsyncClient(http2=True, verify=False) as client:
        # Initial Token Fetch
        await token_vault.refresh_now(client)
        
        while True:
            if not token_vault.bearer:
                await token_vault.refresh_now(client)
                await asyncio.sleep(5)
                continue

            headers = {
                "authorization": f"Bearer {token_vault.bearer}",
                "x-firebase-appcheck": "eyJlcnJvciI6IlVOS05PV05fRVJST1IifQ==",
                "content-type": "application/json; charset=utf-8",
                "user-agent": "okhttp/5.2.1"
            }

            payload = {
                "data": {
                    "coins": {
                        "@type": "type.googleapis.com/google.protobuf.Int64Value",
                        "value": "5"
                    },
                    "offerId": OFFER_ID
                }
            }

            try:
                response = await client.post(POSTBACK_URL, headers=headers, json=payload, timeout=10)
                
                if response.status_code == 200:
                    print(f"✅ Status: 200 | Body: {response.text}")
                elif response.status_code == 401:
                    print("⚠️ Token Expired during loop. Refreshing...")
                    await token_vault.refresh_now(client)
                else:
                    print(f"❌ Error {response.status_code}: {response.text}")

            except Exception as e:
                print(f"📡 Connection Issue: {e}")

            await asyncio.sleep(3) # Unlimited 3-second delay

# -------------------- RENDER WEB SERVER -------------------- #

async def handle(request):
    return web.Response(text=f"BOT RUNNING 24/7\nToken Active: {token_vault.bearer is not None}")

async def main():
    # Start the Earning Loop in the background
    asyncio.create_task(postback_loop())
    
    # Start the Web Server for Render
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    print(f"🌐 Web Server on port {PORT}")
    await site.start()
    
    # Keep the main process alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
