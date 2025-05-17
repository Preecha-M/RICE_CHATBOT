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

    data = {
        "user_id": user_id,
        "image_path": image_path,
        "prediction": result,
        "timestamp": datetime.now().isoformat()
    }

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
        prediction_data = json.load(f)

    user_pending_naming[user_id] = {
        "image_path": prediction_data.get("image_path"),
        "prediction": prediction_data.get("prediction"),
        "timestamp": prediction_data.get("timestamp"),
        "latitude": latitude,
        "longitude": longitude,
        "address": address
    }

    os.remove(prediction_path)

    # ไม่ต้องถามชื่อสถานที่ใหม่อีกแล้ว เพราะตั้งตั้งหลังส่ง location ไปแล้ว
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
    save_path = f"userdata/{user_id}.json"
    os.makedirs("userdata", exist_ok=True)

    temp_data = user_pending_naming[user_id]
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(temp_data, f, indent=4, ensure_ascii=False)

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(
            text=f"✅ บันทึกข้อมูลเรียบร้อย!\n📍 สถานที่: {temp_data['address']}\n\n🔍 ผลทำนาย:\n{temp_data['prediction']}"
        )
    )

    del user_pending_naming[user_id]

# ========== Main ==========

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
