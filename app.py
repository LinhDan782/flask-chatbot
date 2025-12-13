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

# LƯU DỮ LIỆU JSON DẠNG LIST ĐỂ TÌM KIẾM
def load_product_list():
    try:
        with open('products.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []
        
PRODUCT_LIST = load_product_list() # Danh sách các Object sản phẩm

STATIC_SHOP_INFO = """
- Shop: OLV Boutique
- Địa chỉ: 224 Yersin, Hiệp Thành, Thủ Dầu Một, Bình Dương
- Liên hệ: 0923003158
- Chính sách: Đổi trả 7 ngày. Freeship đơn > 500k.
"""
#Dò tìm sản phẩm trong câu trả lời của Gemini
def find_product_details(text):
    """Dò tìm tên sản phẩm trong câu trả lời của Bot và trả về Object sản phẩm tương ứng."""
    for product in PRODUCT_LIST:
        # Kiểm tra xem tên sản phẩm có xuất hiện trong câu trả lời của Bot không
        if product['name'] in text:
            # Ghi đè URL ảnh để đảm bảo có https:
            image_url_full = "https:" + product['image_url']
            return {
                'name': product['name'],
                'price': product['price'],
                'url': product['url'],
                'image_url': image_url_full
            }
    return None
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
    YÊU CẦU:
    1. Nếu khách hỏi câu tương tự trong "Cẩm nang", hãy trả lời giống như mẫu.
    2. Nếu khách hỏi về sản phẩm, hãy tra cứu trong "Danh sách sản phẩm".
    3. Dùng icon (🌸, 👗) để câu văn sinh động.
    """
    
    try:
        response = model.generate_content(prompt)
        bot_reply = response.text
    # Tìm kiếm chi tiết sản phẩm sau khi Bot trả lời
        product_detail = find_product_details(bot_reply)
        
    except Exception as e:
        bot_reply = "Xin lỗi, hệ thống đang bận xíu."
        product_detail = None

    # Trả về cả câu trả lời và chi tiết sản phẩm (nếu tìm thấy)
    return jsonify({
        'reply': bot_reply,
        'product_info': product_detail 
    })

if __name__ == '__main__':
    app.run(debug=True)
