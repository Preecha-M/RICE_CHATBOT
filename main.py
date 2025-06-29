from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, ImageMessage, TextMessage, TextSendMessage, LocationMessage,
    TemplateSendMessage, ButtonsTemplate, PostbackAction, PostbackEvent
)
from gradio_client import Client, handle_file
from datetime import datetime, timedelta

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

# ========== API Weather  ==========
import requests
from datetime import datetime

def weather_condition_label(code):
    table = {
        1: "ฟ้าแจ้ง (Clear)",
        2: "มีเมฆบางส่วน (Partly cloudy)",
        3: "เมฆเป็นส่วนมาก (Cloudy)",
        4: "มีเมฆมาก (Overcast)",
        5: "ฝนเล็กน้อย (Light rain)",
        6: "ฝนปานกลาง (Moderate rain)",
        7: "ฝนหนัก (Heavy rain)",
        8: "พายุฝนฟ้าคะนอง (Thunderstorm)",
        9: "อากาศหนาวจัด (Very cold)",
        10: "อากาศหนาว (Cold)",
        11: "อากาศร้อน (Hot)",
        12: "อากาศร้อนจัด (Very hot)"
    }
    return table.get(code, f"Unknown ({code})")


async def fetch_api_data(date: str, lat: str, lon: str):
    url = "https://data.tmd.go.th/nwpapi/v1/forecast/location/hourly/at"  # ✅ ต้องใช้ /hourly/at เพื่อดึง hourly ไม่ใช่ daily
    querystring = {
        "lat": lat,
        "lon": lon,
        "fields": "tc,rh,rain,slp,ws10m,wd10m,cloudlow,cloudmed,cloudhigh,cond",
        "date": date,
        "duration": "1"
    }
    headers = {
        "accept": "application/json",
        "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6ImM4OTllMTViMWMxMjRlN2U2ZjdiZmZkNWI3MTllY2RkOWI0NjM5OTM3MDczODk4YmNjYjhhMzI0MDJjZGEzYzFiZDMwMTA5YjVhY2I5ODdhIn0.eyJhdWQiOiIyIiwianRpIjoiYzg5OWUxNWIxYzEyNGU3ZTZmN2JmZmQ1YjcxOWVjZGQ5YjQ2Mzk5MzcwNzM4OThiY2NiOGEzMjQwMmNkYTNjMWJkMzAxMDliNWFjYjk4N2EiLCJpYXQiOjE3NTA1ODc0NDcsIm5iZiI6MTc1MDU4NzQ0NywiZXhwIjoxNzgyMTIzNDQ3LCJzdWIiOiI0MDMwIiwic2NvcGVzIjpbXX0.h4u9XYN8rZn9gkiY2GD5pCzTCsYANEhDGVUNPXZDxUOYjh2T8HK_TCEb7YGTd933Vrz4LAKzTNChz7zy8Bqffa9NrNagHajIukIiNFujPKicIvzLag_gwodHPvgQ_YDMsoTgQzCk-ysZnqGYoKZiSHORWE6Gp6ohzb5a-bBh2-F0M7CaAiX7ziy508sgCjWarJXOKQd_Re_WmJCS7SB99n95-idB12IGzF8s_CVpNvznnMdDrSb-HIZVyLTQhSZArTjXHSS6FWQA18LyoZje1xBfQwNwFcopum4mirJrdI3vGk4HcPQ1G5zjZcAAbZ_NuLZuq_1a5eUJq7mIp-3Q753vCiCnTDICVwKjhV3UcEzkSsKHCRUXycR7BdvTjDKnrv3WyJuse5-9M3_ofr2dbD4GS7RR2cxO3SrPOnt5KfQwuSzlXd0QCIbBwIat2dWOEMx9CeQqhxmF9un0DfgnBLhGJ2vZF6mYmgx0hODq2PvW_7Ae7-nmhTryc-qoGASZ0RCCks1gWHRHDM0W7UOgNh86MdEonSB3rzHyeI4KvosECxyGkuTyV6NHYejdwKzloQXVoPGKXEjpWjA_OmFYXn76b8VKhQSr3zt3trOB4FMEfzbZZiBLCs980dxg7513kLSTJdt2lEYRroLALlY_jXoH2rUa50VAsMpyZEVaUmc"
    }
    try:
        response = requests.get(url, headers=headers, params=querystring)
        print("[DEBUG]", response.status_code, response.text)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API error: {response.status_code} - {response.text}"}
    except Exception as e:
        return {"error": str(e)}

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

def remove_expired_requests():
    now = datetime.now()
    expired_keys = []
    for user_id, data in user_pending_location_request.items():
        ts = datetime.fromisoformat(data["timestamp"])
        if now - ts > timedelta(minutes=EXPIRY_MINUTES):
            expired_keys.append(user_id)
    for key in expired_keys:
        del user_pending_location_request[key]
        
# ========== Gemini API             ==========

import google.generativeai as genai
import mimetypes

# ตั้งค่า Gemini API
genai.configure(api_key="AIzaSyBHTMLZ0Mp9AVhTWYFWL-ALxcBiwHswHvQ")
client = genai.GenerativeModel("gemini-1.5-flash")

def is_image(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith("image")

def analyze_input(input_data):
    try:
        if os.path.exists(input_data) and is_image(input_data):
            # กรณีเป็นรูปภาพ
            my_file = genai.upload_file(input_data)
            prompt = "นี่คือรูปของใบข้าวหรือรวงข้าวใช่หรือไม่? ตอบว่า 'ใช่' หรือ 'ไม่ใช่' เท่านั้น"
            response = client.generate_content([my_file, prompt])
        else:
            # กรณีเป็นข้อความ
            contents = [f"""คุณเป็นผู้เชี่ยวชาญด้านการเกษตรข้าว
คำสั่ง:
- ถ้าข้อความพูดถึงโรคของข้าว วิธีรักษา หรือปุ๋ย ให้ตอบข้อความนั้นสั้น ๆ หรือให้คำแนะนำเบื้องต้น
- ถ้าไม่เกี่ยวกับข้าว ให้ตอบว่า 'ขออภัย ข้อมูลนี้เกินขอบเขตที่ระบบสามารถวิเคราะห์ได้' 

ข้อความ: {input_data}"""]
            response = client.generate_content(contents)
        return response.text
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาด: {str(e)}"


# ========== Handler สำหรับ Location ==========

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    latitude = event.message.latitude
    longitude = event.message.longitude
    address = event.message.address

    save_temp_location(user_id, latitude, longitude, address)
    update_location_in_userdata(user_id, latitude, longitude, address)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text=f"✅ ได้รับตำแหน่งแล้ว!\n📍 {address}\nละติจูด: {latitude}\nลองจิจูด: {longitude}\n\nระบบบันทึกพิกัดเรียบร้อยแล้วครับ ✅"
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

def save_direct_to_userdata(user_id, image_path, result):
    os.makedirs("userdata", exist_ok=True)
    save_path = f"userdata/{user_id}.json"

    profile = line_bot_api.get_profile(user_id)
    display_name = profile.display_name

    record = {
        "user_id": user_id,
        "display_name": display_name,
        "image_path": image_path,
        "prediction": result,
        "timestamp": datetime.now().isoformat(),
        "address": "ไม่ระบุ",
        "latitude": None,
        "longitude": None
    }

    if os.path.exists(save_path):
        with open(save_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        records = []

    records.append(record)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def update_location_in_userdata(user_id, latitude, longitude, address):
    save_path = f"userdata/{user_id}.json"
    if not os.path.exists(save_path):
        return

    with open(save_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if records:
        records[-1]["latitude"] = latitude
        records[-1]["longitude"] = longitude
        records[-1]["address"] = address

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

# ========== Handler สำหรับ Image ==========

# เพิ่ม dict ใหม่
user_pending_location_request = {}

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    message_content = line_bot_api.get_message_content(event.message.id)

    os.makedirs("static", exist_ok=True)
    image_path = f"static/{event.message.id}.jpg"
    with open(image_path, "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    # ✅ ตรวจสอบด้วย Gemini ว่าเป็นใบข้าวหรือไม่ (เพิ่ม try-except ตรงนี้)
    try:
        gemini_check = analyze_input(image_path)
        if "ไม่ใช่" in gemini_check.lower():
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="🚫 ภาพนี้ไม่ใช่ใบข้าว ระบบจะไม่ทำการวิเคราะห์ต่อครับ")
            )
            return
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"❌ ไม่สามารถวิเคราะห์ภาพด้วย Gemini ได้: {str(e)}")
        )
        return

    # ✅ หากผ่านเงื่อนไขว่าเป็นใบข้าว ค่อยส่งเข้าโมเดล Gradio
    result = gr_client.predict(
        image=handle_file(image_path),
        api_name="/predict"
    )

    # ✅ บันทึกไปยัง userdata เลยทันที
    save_direct_to_userdata(user_id, image_path, result)

    # ✅ แจ้งผลและแนะนำส่ง location
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text=f"🔍 ผลการวิเคราะห์:\n{result}\n\n📍 ต้องการส่งตำแหน่งแปลงนาไหม?\nหากต้องการ โปรดส่ง Location มาต่อจากนี้\nหากไม่ต้องการ ระบบจะบันทึกข้อมูลตามภาพที่ส่งมาครับ"
        )
    )

# def save_temp_prediction(user_id, image_path, result):
#     os.makedirs("temp_prediction", exist_ok=True)
#     filepath = f"temp_prediction/{user_id}.json"

#     # ดึงข้อมูลโปรไฟล์
#     profile = line_bot_api.get_profile(user_id)
#     display_name = profile.display_name

#     record = {
#         "user_id": user_id,
#         "display_name": display_name,
#         "image_path": image_path,
#         "prediction": result,
#         "timestamp": datetime.now().isoformat()
#     }

#     # โหลดข้อมูลเก่า ถ้ามี
#     if os.path.exists(filepath):
#         with open(filepath, "r", encoding="utf-8") as f:
#             data = json.load(f)
#     else:
#         data = []

#     data.append(record)

#     with open(filepath, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=4, ensure_ascii=False)

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

# @handler.add(MessageEvent, message=TextMessage)
# def handle_text(event):
#     user_id = event.source.user_id
#     user_text = event.message.text.strip()

#     # ตั้งชื่อสถานที่ หลังส่ง Location
#     if user_id in user_pending_location_naming:
#         filepath = f"temp_location/{user_id}.json"

#         if os.path.exists(filepath):
#             with open(filepath, "r", encoding="utf-8") as f:
#                 locations = json.load(f)

#             if user_text not in ["ไม่ตั้งชื่อ", "ไม่", "no", "No"]:
#                 locations[-1]["address"] = user_text  # แก้ไข address ของตำแหน่งล่าสุด

#             with open(filepath, "w", encoding="utf-8") as f:
#                 json.dump(locations, f, indent=4, ensure_ascii=False)

#             reply = f"✅ ตั้งชื่อสถานที่เป็น: {user_text}" if user_text not in ["ไม่ตั้งชื่อ", "ไม่", "no", "No"] else "✅ ใช้ชื่อเดิมที่ LINE ส่งมา"
#             line_bot_api.reply_message(
#                 event.reply_token,
#                 TextSendMessage(text=reply)
#             )

#         del user_pending_location_naming[user_id]

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id

    # เรียก Gemini วิเคราะห์ข้อความ
    gemini_response = analyze_input(user_text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=gemini_response)
    )


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
from datetime import datetime, timedelta

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    selected_date = request.query_params.get("date") or datetime.now().strftime("%Y-%m-%d")
    selected_lat = request.query_params.get("lat") or "13.10"
    selected_lon = request.query_params.get("lon") or "100.10"
    page = int(request.query_params.get("page", 1))
    per_page = 5
    start = (page - 1) * per_page
    end = start + per_page

    max_date = (datetime.now() + timedelta(days=126)).strftime("%Y-%m-%d")

    # ✅ ส่งค่า lat lon ไปเรียก API
    api_data = await fetch_api_data(selected_date, selected_lat, selected_lon)

    # ✅ สร้าง label mapping ภาษาไทย
    field_labels = {
        "tc": "อุณหภูมิ (°C)",
        "rh": "ความชื้นสัมพัทธ์ (%)",
        "rain": "ปริมาณฝน (mm)",
        "slp": "ความกดอากาศระดับน้ำทะเล (hPa)",
        "ws10m": "ความเร็วลมที่ 10 เมตร (m/s)",
        "wd10m": "ทิศทางลมที่ 10 เมตร (องศา)",
        "cloudlow": "ปริมาณเมฆระดับต่ำ (%)",
        "cloudmed": "ปริมาณเมฆระดับกลาง (%)",
        "cloudhigh": "ปริมาณเมฆระดับสูง (%)",
        "cond": "สภาพอากาศโดยทั่วไป"
    }

# ✅ แปลงเป็น list
# สร้าง weather_list สำหรับ daily
    weather_list = []
    if "WeatherForecasts" in api_data:
        for fc in api_data["WeatherForecasts"][0]["forecasts"]:
            entry = {
                "time": fc["time"],
                "data": []
            }
            for k, v in fc["data"].items():
                label = field_labels.get(k, k)
                if k == "cond":
                    v = weather_condition_label(int(v))
                entry["data"].append({
                    "label": label,
                    "value": v
                })
            weather_list.append(entry)

    # 2) โหลดข้อมูล userdata ตามเดิม
    records = []
    user_ids = set()
    heat_data = []
    disease_by_location = defaultdict(lambda: defaultdict(int))
    all_diseases_set = set()

    for file_path in glob.glob("userdata/*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
            user_data_list = content if isinstance(content, list) else [content]
            for data in user_data_list:
                data["user_id"] = os.path.basename(file_path).replace(".json", "")
                records.append(data)
                user_ids.add(data["user_id"])
                prediction_text = data.get("prediction", "")
                disease_line = prediction_text.split("\n")[0] if "\n" in prediction_text else prediction_text
                disease_name = disease_line.replace("🔍 ผลการทำนาย:", "").strip()
                all_diseases_set.add(disease_name)
                location = data.get("address", "ไม่ระบุสถานที่")
                disease_by_location[location][disease_name] += 1
                if data.get("latitude") and data.get("longitude"):
                    heat_data.append([data["latitude"], data["longitude"], 1])

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
    
    paginated_records = records[start:end]
    total_pages = (len(records) + per_page - 1) // per_page

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "records": paginated_records,
        "page": page,
        "total_pages": total_pages,
        "summary": summary,
        "heat_data": heat_data,
        "api_data": api_data,
        "selected_date": selected_date,
        "selected_lat": selected_lat,
        "selected_lon": selected_lon,
        "max_date": max_date,
        "weather_list": weather_list
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
