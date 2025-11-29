import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import google.generativeai as genai

# Cấu hình
load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("Cảnh báo: Chưa cấu hình GEMINI_API_KEY")
else:
    genai.configure(api_key=api_key)
    
model = genai.GenerativeModel('gemini-2.5-flash')

SHOP_DATA = """
- Shop tên: Vintage Store.
- Giờ làm việc: 8h - 22h hàng ngày.
- Địa chỉ: 123 Đường ABC, Quận 1.
- Chính sách: Đổi trả trong 3 ngày nếu lỗi.
- Ship: Đồng giá 30k toàn quốc.
"""
app = Flask(__name__)
CORS(app)

# --- Route 1: Trang chủ (Hiển thị giao diện) ---
@app.route('/')
def home():
    return render_template('index.html')

# --- Route 2: API Chat ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get('message')
    
    if not user_msg:
        return jsonify({'reply': 'Bạn chưa nhập gì cả!'})

    prompt = f"""
    Bạn là nhân viên tư vấn của Vintage Store. Hãy trả lời câu hỏi sau của khách dựa trên thông tin shop.
    Thông tin shop: {SHOP_DATA}
    Câu hỏi khách: {user_msg}
    Trả lời ngắn gọn, thân thiện, có icon:
    """
    
    try:
        response = model.generate_content(prompt)
        bot_reply = response.text
    except Exception as e:
        print(f"Lỗi Gemini: {e}")
        bot_reply = "Xin lỗi, hệ thống đang bận. Bạn thử lại sau nhé!"

    return jsonify({'reply': bot_reply})

if __name__ == '__main__':
    app.run(debug=True)
