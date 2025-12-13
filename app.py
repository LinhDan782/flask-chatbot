import os
import json
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

# --- HÀM ĐỌC DỮ LIỆU TỪ FILE JSON ---
def load_product_data():
    try:
        with open('products.json', 'r', encoding='utf-8') as f:
            products = json.load(f)
            
        # Chuyển đổi JSON thành văn bản để Gemini đọc
        text_data = ""
        for p in products:
            text_data += f"- Tên: {p['name']}\n"
            text_data += f"  Giá: {p['price']} | Size: {p['sizes']} | Màu: {p['colors']}\n"
            text_data += f"  Mô tả: {p['description']}\n"
            text_data += f"  Link ảnh/mua: {p['url']}\n"
            text_data += "---\n"
            
        return text_data
    except Exception as e:
        return "" # Trả về rỗng nếu lỗi

# Load dữ liệu ngay khi khởi động
PRODUCT_DATA = load_product_data()

STATIC_SHOP_INFO = """
- Shop: OLV Boutique
- Địa chỉ: 224 Yersin, Hiệp Thành, Thủ Dầu Một, Bình Dương
- Liên hệ: 0923003158
- Chính sách: Đổi trả 7 ngày. Freeship đơn > 500k.
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
    Bạn là nhân viên tư vấn của shop thời trang OLV.
    Nhiệm vụ: Tư vấn sản phẩm dựa trên danh sách bên dưới.
    
    QUY TẮC:
    1. Chỉ tư vấn sản phẩm có trong danh sách.
    2. Nếu khách hỏi món không có, gợi ý món tương tự trong danh sách.
    3. Luôn kèm giá và link sản phẩm khi giới thiệu.
    
    DANH SÁCH SẢN PHẨM:
    {PRODUCT_DATA}
    
    THÔNG TIN CHUNG:
    {STATIC_SHOP_INFO}
    
    KHÁCH HỎI: {user_msg}
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
