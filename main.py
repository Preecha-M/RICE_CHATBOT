from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, TextSendMessage, LocationMessage,
    TemplateSendMessage, ButtonsTemplate, PostbackAction, PostbackEvent
)
from gradio_client import Client, handle_file
from datetime import datetime
import os
import json
import uvicorn

# LINE credentials
LINE_CHANNEL_ACCESS_TOKEN = "KbjaeoEXCN1kHwF0t4nxC6ErPY+BGapJGFcf663laX180ksXTjaOJXtBo0VWk3Zw/YBSvg6cpHMZkBEOs55+J4PZIpKrntHkase5Xz/B0MMS5Bm3cezHztwMlzmP9vY6cKzwixqQQrrfxR2AWI+2QwdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "2cf4efbc5245333f341f7734c5c1c35a"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
gr_client = Client("Teayear/Rice")

app = FastAPI()

# เก็บสถานะรอการตั้งชื่อ "Location" หลังส่ง Location
user_pending_location_naming = {}

# เก็บสถานะรอการจับคู่ "Image + Location" หลังส่งรูป
user_pending_naming = {}

# ========== FastAPI Callback ==========

@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get('x-line-signature')
    background_tasks.add_task(handle_events, body, signature)
    return JSONResponse(content={"message": "OK"}, status_code=200)

def handle_events(body, signature):
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Handle error: {e}")

# ========== Handler สำหรับ Location ==========

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    latitude = event.message.latitude
    longitude = event.message.longitude
    address = event.message.address

    save_temp_location(user_id, latitude, longitude, address)

    # 📌 เก็บสถานะว่ากำลังรอให้ตั้งชื่อ Location
    user_pending_location_naming[user_id] = True

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text=f"✅ ได้รับตำแหน่งแล้ว\n📍 {address}\nละติจูด: {latitude}\nลองจิจูด: {longitude}\n\n📝 ต้องการตั้งชื่อสถานที่ไหม?\nถ้าใช่ พิมพ์ชื่อสถานที่ใหม่ ✏️\n(ถ้าไม่ต้องการ พิมพ์ 'ไม่ตั้งชื่อ')"
        )
    )

def save_temp_location(user_id, latitude, longitude, address):
    os.makedirs("temp_location", exist_ok=True)
    filepath = f"temp_location/{user_id}.json"

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    data.append({
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "timestamp": datetime.now().isoformat()
    })

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ========== Handler สำหรับ Image ==========

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    message_content = line_bot_api.get_message_content(event.message.id)

    os.makedirs("static", exist_ok=True)
    image_path = f"static/{event.message.id}.jpg"
    with open(image_path, "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    # Predict
    result = gr_client.predict(
        image=handle_file(image_path),
        api_name="/predict"
    )

    save_temp_prediction(user_id, image_path, result)
    ask_user_to_select_location(user_id, event.reply_token)

def save_temp_prediction(user_id, image_path, result):
    os.makedirs("temp_prediction", exist_ok=True)
    filepath = f"temp_prediction/{user_id}.json"

    # ดึงข้อมูลโปรไฟล์
    profile = line_bot_api.get_profile(user_id)
    display_name = profile.display_name

    record = {
        "user_id": user_id,
        "display_name": display_name,
        "image_path": image_path,
        "prediction": result,
        "timestamp": datetime.now().isoformat()
    }

    # โหลดข้อมูลเก่า ถ้ามี
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    data.append(record)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def ask_user_to_select_location(user_id, reply_token):
    filepath = f"temp_location/{user_id}.json"

    if not os.path.exists(filepath):
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="❌ ยังไม่ได้ส่ง location กรุณาส่งตำแหน่งมาก่อนค่ะ")
        )
        return

    with open(filepath, "r", encoding="utf-8") as f:
        locations = json.load(f)

    buttons = []
    for loc in locations[-4:]:
        address = loc.get("address", "Unknown")
        latitude = loc.get("latitude")
        longitude = loc.get("longitude")
        action_data = json.dumps({
            "latitude": latitude,
            "longitude": longitude,
            "address": address
        })

        buttons.append(
            PostbackAction(label=address[:20], data=action_data)
        )

    template = ButtonsTemplate(
        title="เลือกตำแหน่งที่จะจับคู่กับรูปภาพ",
        text="กรุณาเลือกตำแหน่งที่ต้องการ",
        actions=buttons
    )

    message = TemplateSendMessage(
        alt_text="กรุณาเลือกตำแหน่ง",
        template=template
    )

    line_bot_api.reply_message(reply_token, message)

# ========== Handler สำหรับ Postback ==========

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    selected_data = json.loads(event.postback.data)

    latitude = selected_data.get("latitude")
    longitude = selected_data.get("longitude")
    address = selected_data.get("address")

    prediction_path = f"temp_prediction/{user_id}.json"
    if not os.path.exists(prediction_path):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="❌ ไม่พบข้อมูลรูป กรุณาส่งรูปใหม่ค่ะ")
        )
        return

    with open(prediction_path, "r", encoding="utf-8") as f:
        data_list = json.load(f)

    # ✅ ใช้ข้อมูลล่าสุด
    latest_data = data_list[-1]

    user_pending_naming[user_id] = {
        "image_path": latest_data.get("image_path"),
        "prediction": latest_data.get("prediction"),
        "timestamp": latest_data.get("timestamp"),
        "latitude": latitude,
        "longitude": longitude,
        "address": address
    }

    # ✅ ลบ record ล่าสุดออกจาก temp
    data_list.pop()
    if data_list:
        with open(prediction_path, "w", encoding="utf-8") as f:
            json.dump(data_list, f, indent=4, ensure_ascii=False)
    else:
        os.remove(prediction_path)

    save_final_userdata(user_id, event.reply_token)

# ========== Handler สำหรับรับข้อความ Text ==========

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()

    # ตั้งชื่อสถานที่ หลังส่ง Location
    if user_id in user_pending_location_naming:
        filepath = f"temp_location/{user_id}.json"

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                locations = json.load(f)

            if user_text not in ["ไม่ตั้งชื่อ", "ไม่", "no", "No"]:
                locations[-1]["address"] = user_text  # แก้ไข address ของตำแหน่งล่าสุด

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(locations, f, indent=4, ensure_ascii=False)

            reply = f"✅ ตั้งชื่อสถานที่เป็น: {user_text}" if user_text not in ["ไม่ตั้งชื่อ", "ไม่", "no", "No"] else "✅ ใช้ชื่อเดิมที่ LINE ส่งมา"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply)
            )

        del user_pending_location_naming[user_id]

def save_final_userdata(user_id, reply_token):
    os.makedirs("userdata", exist_ok=True)
    save_path = f"userdata/{user_id}.json"

    temp_data = user_pending_naming[user_id]

    # ดึงข้อมูลโปรไฟล์
    profile = line_bot_api.get_profile(user_id)
    display_name = profile.display_name
    temp_data["display_name"] = display_name

    # โหลดข้อมูลเก่าถ้ามี
    if os.path.exists(save_path):
        with open(save_path, "r", encoding="utf-8") as f:
            user_records = json.load(f)
    else:
        user_records = []

    # เพิ่มรายการใหม่
    user_records.append(temp_data)

    # บันทึกข้อมูลทั้งหมด
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(user_records, f, indent=4, ensure_ascii=False)

    # ส่งข้อความยืนยัน
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(
            text=f"✅ บันทึกข้อมูลเรียบร้อย!\n👤 ชื่อ: {display_name}\n📍 สถานที่: {temp_data['address']}\n\n🔍 ผลทำนาย:\n{temp_data['prediction']}"
        )
    )

    del user_pending_naming[user_id]

# ========== WEB Dashboard ==========
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# ตั้งค่า Template และ Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

from fastapi import Request
import glob

from collections import defaultdict

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    records = []
    user_ids = set()
    heat_data = []

    # สำหรับ Bar Chart
    disease_by_location = defaultdict(lambda: defaultdict(int))  # {location: {disease: count}}
    all_diseases_set = set()
    location_list = []

    for file_path in glob.glob("userdata/*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
            user_data_list = content if isinstance(content, list) else [content]

            for data in user_data_list:
                data["user_id"] = os.path.basename(file_path).replace(".json", "")
                records.append(data)
                user_ids.add(data["user_id"])

                # Extract disease name
                prediction_text = data.get("prediction", "")
                disease_line = prediction_text.split("\n")[0] if "\n" in prediction_text else prediction_text
                disease_name = disease_line.replace("🔍 ผลการทำนาย:", "").strip()
                all_diseases_set.add(disease_name)

                # Location for chart
                location = data.get("address", "ไม่ระบุสถานที่")
                disease_by_location[location][disease_name] += 1

                # Heatmap data
                if data.get("latitude") and data.get("longitude"):
                    heat_data.append([data["latitude"], data["longitude"], 1])

    # Prepare chart data
    all_diseases = sorted(all_diseases_set)
    location_list = sorted(disease_by_location.keys())

    datasets_for_chart = []
    for i, disease in enumerate(all_diseases):
        data_points = []
        for loc in location_list:
            data_points.append(disease_by_location[loc].get(disease, 0))
        datasets_for_chart.append({
            'label': disease,
            'data': data_points,
            'backgroundColor': f'rgba({(i*50)%255}, {(i*100)%255}, {(i*150)%255}, 0.6)'
        })

    # Summary
    location_counter = {loc: sum(counts.values()) for loc, counts in disease_by_location.items()}
    most_common_location = max(location_counter, key=location_counter.get, default="ไม่พบข้อมูล")
    disease_summary = {disease: sum(disease_by_location[loc].get(disease, 0) for loc in location_list) for disease in all_diseases}

    summary = {
        "total_users": len(user_ids),
        "most_common_location": most_common_location,
        "disease_summary": disease_summary,
        "location_list": location_list,
        "datasets_for_chart": datasets_for_chart
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "records": records,
        "summary": summary,
        "heat_data": heat_data
    })

# ========== Guide ==========
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app.mount("/guide_images", StaticFiles(directory="guide_images"), name="guide_images")
templates = Jinja2Templates(directory="templates")

@app.get("/guide", response_class=HTMLResponse)
async def get_guide_page(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

# ========== Main ==========

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
