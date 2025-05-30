import subprocess
import time
import requests
import json
import sys
import threading

# เพิ่มฟังก์ชันอัปเดต Webhook
def update_line_webhook(new_url):
    LINE_CHANNEL_ACCESS_TOKEN = "KbjaeoEXCN1kHwF0t4nxC6ErPY+BGapJGFcf663laX180ksXTjaOJXtBo0VWk3Zw/YBSvg6cpHMZkBEOs55+J4PZIpKrntHkase5Xz/B0MMS5Bm3cezHztwMlzmP9vY6cKzwixqQQrrfxR2AWI+2QwdB04t89/1O/w1cDnyilFU="
    headers = {
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    body = {
        "endpoint": new_url + "/callback"
    }
    response = requests.put("https://api.line.me/v2/bot/channel/webhook/endpoint", headers=headers, json=body)
    if response.status_code == 200:
        print("✅ อัปเดต Webhook สำเร็จแล้ว!")
    else:
        print(f"❌ อัปเดต Webhook ไม่สำเร็จ: {response.text}")

def run_uvicorn():
    # รัน FastAPI Server
    subprocess.run(["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"])

def run_ngrok():
    # รัน ngrok http 8000
    subprocess.Popen(["ngrok", "http", "8000"])
    time.sleep(2)  # รอ ngrok เปิดตัวสัก 2 วิ

def get_public_url():
    try:
        ngrok_api = "http://localhost:4040/api/tunnels"
        tunnels_info = requests.get(ngrok_api).text
        tunnels = json.loads(tunnels_info)["tunnels"]
        for tunnel in tunnels:
            if tunnel["proto"] == "https":
                public_url = tunnel["public_url"]
                return public_url
    except Exception as e:
        print(f"Error fetching ngrok URL: {e}")
        return None

if __name__ == "__main__":
    # เปิด ngrok ก่อน
    threading.Thread(target=run_ngrok, daemon=True).start()
    
    # รอให้ ngrok เปิดจริงๆ
    time.sleep(5)
    
    public_url = get_public_url()
    if public_url:
        print("\n🚀 Server Ready!")
        print(f"📨 ใส่ Webhook URL นี้ใน LINE Developer: {public_url}/callback\n")
        
        # อัปเดต Webhook อัตโนมัติ
        update_line_webhook(public_url)
    else:
        print("❌ ไม่เจอ ngrok URL")

    # จากนั้นเปิด uvicorn server
    run_uvicorn()
