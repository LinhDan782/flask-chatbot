import os
import json
import time
import requests
import base64
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
from google.genai import types

# Cấu hình
load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=api_key)    
MODEL_ID ="gemini-2.5-flash"

# Biến toàn cục lưu dữ liệu trong RAM
PRODUCT_DATA_TEXT = ""
PRODUCT_LIST_JSON = []
CHAT_SESSIONS = {}

# --- PHẦN 1: HÀM CRAWL DỮ LIỆU TỰ ĐỘNG ---
def crawl_olv_data(max_pages=1):
    """Hàm lấy dữ liệu từ nhiều danh mục khác nhau"""
    categories = {
        "Giảm giá": "https://www.olv.vn/pages/flash-sale",
        "Hàng mới về": "https://www.olv.vn/collections/pure-fairy",
        "Bán chạy": "https://www.olv.vn/collections/san-pham-ban-chay",
        "Tất cả sản phẩm": "https://www.olv.vn/collections/tat-ca-san-pham",
    }
    
    crawled_products = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    print("🚀 Bắt đầu cập nhật dữ liệu từ OLV...")
    
    for cat_name, url in categories.items():
        try:
            print(f"--- Đang truy cập danh mục: {cat_name} ...")
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tìm các khối sản phẩm (hỗ trợ nhiều class khác nhau của OLV)
            items = soup.find_all('div', class_=['product-block', 'product-item', 'col-md-3', 'col-sm-6', 'col-xs-6'])
            
            for item in items:
                try:
                    # 1. Tìm tên sản phẩm
                    name_tag = item.find(['h3', 'h4'], class_=['pro-name', 'product-title'])
                    
                    # 2. Tìm giá sản phẩm
                    # Ưu tiên lấy class 'pro-price' nhưng phải loại bỏ phần giá cũ (thẻ del/s) nếu có
                    price_tag = item.find(['p', 'span'], class_=['pro-price', 'current-price', 'price'])
                    
                    if name_tag and price_tag:
                        name = name_tag.get_text(strip=True)
                        
                        # Lấy link sản phẩm
                        a_tag = name_tag.find('a')
                        product_url = "https://www.olv.vn" + a_tag['href'] if a_tag else ""
                        
                        # Xử lý giá: lấy text và làm sạch
                        # Chú ý: .split('₫')[0] sẽ lấy con số đầu tiên trước ký hiệu tiền tệ
                        full_price_text = price_tag.get_text(strip=True)
                        clean_price = full_price_text.split('₫')[0].strip().replace('\n', '') + '₫'
                        
                        # 3. Tìm ảnh sản phẩm
                        img_tag = item.find('img')
                        img_url = ""
                        if img_tag:
                            # Haravan/Shopify thường lưu ảnh thật ở data-src
                            img_url = img_tag.get('data-src') or img_tag.get('src')
                            if img_url and img_url.startswith('//'):
                                img_url = "https:" + img_url

                        # Kiểm tra trùng lặp dựa trên tên
                        if not any(p['name'] == name for p in crawled_products):
                            crawled_products.append({
                                "id": f"OLV_{int(time.time())}_{len(crawled_products)}",
                                "name": name,
                                "price": clean_price,
                                "category": cat_name, # Gán nhãn để Gemini nhận biết
                                "url": product_url,
                                "image_url": img_url
                            })
                except Exception as e:
                    continue
        except Exception as e:
            print(f"❌ LỖI API: {e}")
            return jsonify({'reply': 'Hệ thống đang bảo trì một chút xíu ạ 😅 (Lỗi server)'})
                                    
    if len(crawled_products) == 0:
        print("⚠️ Không lấy được dữ liệu online. Giữ nguyên dữ liệu cũ.")
        return None
        
    print(f"✅ Đã crawl xong tổng cộng {len(crawled_products)} sản phẩm.")
    return crawled_products

# --- PHẦN 2: HÀM QUẢN LÝ DỮ LIỆU ---
def save_and_reload_data(new_data=None):
    global PRODUCT_DATA_TEXT, PRODUCT_LIST_JSON
    
    if new_data:
        with open('products.json', 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
            print("💾 Đã lưu file products.json mới.")

    try:
        with open('products.json', 'r', encoding='utf-8') as f:
            PRODUCT_LIST_JSON = json.load(f)
            
        text_data = ""
        for p in PRODUCT_LIST_JSON:
            # Thêm thông tin Danh mục vào text cho Gemini học
            text_data += f"- Tên: {p['name']} | Giá: {p['price']} | Nhóm: {p.get('category', 'Sản phẩm')}\n"
            text_data += f"  Link: {p['url']}\n---\n"
        
        PRODUCT_DATA_TEXT = text_data
        print("🔄 Đã nạp dữ liệu đa danh mục vào bộ nhớ Bot.")
    except FileNotFoundError:
        pass

# Khởi động lần đầu
save_and_reload_data()

STATIC_SHOP_INFO = """
- Shop: OLV Boutique
- Website mua hàng: https://www.olv.vn/
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
    
# --- Route 2: Cập nhật dữ liệu sản phẩm ---
@app.route('/admin/update-products', methods=['GET'])
def update_products():
    try:
        # 1. Chạy Crawler lấy 5 trang đầu
        new_data = crawl_olv_data(max_pages=5)
        
        # 2. Lưu và nạp lại dữ liệu
        save_and_reload_data(new_data)
        
        return jsonify({
            "status": "success", 
            "message": f"Đã cập nhật thành công {len(new_data)} sản phẩm mới nhất!",
            "total_products": len(new_data)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
# --- Route 3: Xóa lịch sử chat ---
@app.route('/clear_history', methods=['POST'])
def clear_history():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id in CHAT_SESSIONS:
        del CHAT_SESSIONS[session_id] # Xóa khỏi RAM
        return jsonify({'status': 'success', 'message': 'Đã xóa ký ức!'})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy session'})
# --- Route 4: API Chat ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get('message')
    image_data = data.get('image')
    session_id = data.get('session_id')
    if not user_msg and not image_data:
        return jsonify({'reply': 'Bạn chưa nhập gì cả!'})
    # Khởi tạo lịch sử nếu chưa có
    if session_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[session_id] = []

    prompt = [ 
        f"""
        Bạn là AI tư vấn chuyên nghiệp của OLV Boutique. 🌸
        Dữ liệu sản phẩm (bao gồm Hàng mới, Giảm giá, Bán chạy, Tất cả sản phẩm):
        {PRODUCT_DATA_TEXT}
        Thông tin shop:
        {STATIC_SHOP_INFO}
        Yêu cầu:
        1. Trả lời ngắn gọn, thân thiện (dùng icon 🌸).
        2. Khi khách hỏi về "giảm giá", "sale", "hàng mới" hoặc "bán chạy", hãy lọc trong dữ liệu theo phần 'Nhóm' tương ứng để trả lời.
        3. Nếu có nhiều sản phẩm, hãy gợi ý khoảng 3-4 mẫu nổi bật nhất.
        4. Khi giới thiệu sản phẩm:
           - BẮT BUỘC dùng định dạng danh sách gạch đầu dòng (-).
           - Cấu trúc mỗi dòng: **[Tên sản phẩm](URL sản phẩm)** - Giá: ... - Mô tả siêu ngắn (dưới 15 từ).
           - Ví dụ: 
             - **[Đầm ABC](https://...)** - Giá: 500k - Thiết kế xinh xắn.
        5. Không viết thành đoạn văn dài dòng. Mỗi ý xuống dòng rõ ràng.
        """
    ]
# 2. Xử lý input người dùng
    user_parts_for_api = []
    saved_image_bytes = None
    saved_mime_type = "image/jpeg"
    if image_data:
        if ";base64," in image_data:
            saved_mime_type = image_data.split(";")[0].split(":")[1]
        if "," in image_data:
            header,image_payload = image_data.split(",")[1]
            if ":" in header and ";" in header:
                saved_mime_type = header.split(":")[1].split(";")[0]
        else:
            image_payload = image_data
        saved_image_bytes = base64.b64decode(image_payload)
        img = Image.open(BytesIO(base64.b64decode(image_data)))
        user_parts_for_api.append(img)
    if user_msg:
        user_parts_for_api.append(f"Khách: {user_msg}")
    missing_padding = len(image_payload) % 4
    if missing_padding:
        image_payload += '=' * (4 - missing_padding)
    try:
        # 3. Giải mã một lần duy nhất
        saved_image_bytes = base64.b64decode(image_payload)
            
        # 4. Sử dụng BytesIO để PIL Image có thể đọc được
        img = Image.open(BytesIO(saved_image_bytes))
            
        # Gemini SDK chấp nhận trực tiếp đối tượng PIL Image hoặc bytes
        user_parts_for_api.append(img)
    except Exception as e:
            print(f"❌ Lỗi xử lý ảnh: {e}")
            return jsonify({'reply': 'Định dạng ảnh không hợp lệ, bạn gửi lại giúp shop nhé! 🌸'})
    # 3. Ghép: [Prompt] + [Lịch sử] + [Tin nhắn mới]
    contents = [prompt] + CHAT_SESSIONS[session_id] + [user_parts_for_api]

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents
        )
        bot_reply = response.text

        # 4. Lưu lại hội thoại vào RAM
        history_parts = []
        if saved_image_bytes:
            history_parts.append(types.Part.from_bytes(
                data=saved_image_bytes, 
                mime_type=saved_mime_type
            ))
        if user_msg:
            history_parts.append(types.Part.from_text(text=user_msg))
        # Lưu vào lịch sử User
        if history_parts:
            CHAT_SESSIONS[session_id].append(types.Content(
                role="user", 
                parts=history_parts
            ))      
        # Lưu câu trả lời của Bot
        CHAT_SESSIONS[session_id].append(types.Content(
            role="model",
            parts=[types.Part.from_text(text=bot_reply)]
        ))
        # Tìm sản phẩm để hiển thị Card
        product_detail = None
        for p in PRODUCT_LIST_JSON:
            if p['name'].lower() in bot_reply.lower(): 
                product_detail = p
                break 
                
        return jsonify({
            'reply': bot_reply,
            'product_info': product_detail
        })
        
    except Exception as e:
        print(e)
        return jsonify({'reply': 'Hệ thống đang bảo trì một chút xíu ạ 😅'})

if __name__ == '__main__':
    app.run(debug=True)