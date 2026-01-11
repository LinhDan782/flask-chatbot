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
# --- SYSTEM INSTRUCTION (Tính năng: System Prompt & Fine-tuning logic) ---
SYSTEM_INSTRUCTION = """
Bạn là Lily - Chuyên gia tư vấn thời trang tâm lý và nhiệt huyết của OLV Boutique. 🌸
Phong cách của bạn: Ngọt ngào, tinh tế, luôn khen ngợi khách hàng một cách chân thành.

Nhiệm vụ của bạn:
1. Q&A: Giải đáp thắc mắc về size, chất liệu và phối đồ. Nếu khách gửi ảnh, hãy phân tích màu sắc/kiểu dáng để khen hoặc tư vấn món đồ phù hợp.
2. RAG: Sử dụng dữ liệu sản phẩm được cung cấp để gợi ý. Không bao giờ nói "Tôi không biết", hãy khéo léo gợi ý sang sản phẩm tương tự.
3. Cảm xúc: Sử dụng các từ ngữ như "nàng ơi", "yêu lắm", "cực xinh", "sang xịn mịn".
4. Định dạng: 
   - Dùng gạch đầu dòng cho danh sách.
   - **[Tên sản phẩm](URL)** - Giá - Nhận xét ngắn về phong cách.
   - LƯU Ý: Phải sử dụng chính xác URL được cung cấp trong phần "Bối cảnh sản phẩm", không tự chế link.
"""
STATIC_SHOP_INFO = """
- Shop: OLV Boutique
- Website mua hàng: https://www.olv.vn/
- Địa chỉ: 224 Yersin, Hiệp Thành, Thủ Dầu Một, Bình Dương
- Liên hệ: 0923003158
- Chính sách: Đổi trả 7 ngày. Freeship đơn > 500k.
"""
# Biến toàn cục lưu dữ liệu trong RAM
PRODUCT_DATA_TEXT = ""
PRODUCT_LIST_JSON = []
CHAT_SESSIONS = {}

# --- PHẦN 1: HÀM CRAWL DỮ LIỆU TỰ ĐỘNG ---
def crawl_olv_data(max_pages=1):
    """Hàm lấy dữ liệu từ nhiều danh mục khác nhau"""
    categories = {
        "Giảm giá": "https://www.olv.vn/pages/flash-sale",
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
                        href = a_tag.get('href', '') if a_tag else ""
                        if href.startswith('http'):
                            product_url = href
                        else:
                        # Đảm bảo có dấu / giữa domain và path
                            product_url = "https://www.olv.vn" + ("" if href.startswith('/') else "/") + href
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
    
    #Chỉ ghi file nếu có dữ liệu mới để tránh mất dữ liệu cũ khi crawl lỗi
    if new_data and len(new_data) > 0:
        with open('products.json', 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
            print(f"💾 Đã lưu {len(new_data)} sản phẩm mới vào products.json.")

    try:
        if os.path.exists('products.json'):
            with open('products.json', 'r', encoding='utf-8') as f:
                PRODUCT_LIST_JSON = json.load(f)
            
            text_data = ""
            for p in PRODUCT_LIST_JSON:
                text_data += f"- Tên: {p['name']} | Giá: {p['price']} | Nhóm: {p.get('category', 'Sản phẩm')}\n"
                text_data += f"  Link: {p['url']}\n---\n"
            
            PRODUCT_DATA_TEXT = text_data
            print("🔄 Đã nạp dữ liệu vào bộ nhớ Bot.")
    except Exception as e:
        print(f"❌ Lỗi khi nạp dữ liệu: {e}")
# --- RAG LOGIC (Tìm kiếm sản phẩm liên quan) ---
def get_relevant_products(query, top_k=5):
    if not query: return ""
    query_lc = query.lower()
    relevant = [p for p in PRODUCT_LIST_JSON if query_lc in p['name'].lower() or query_lc in p.get('category', '').lower()]
    
    context = "Dưới đây là các sản phẩm phù hợp với yêu cầu của bạn:\n"
    for p in relevant[:top_k]:
        context += f"- {p['name']} | Giá: {p['price']} | Link: {p['url']} | Nhóm: {p.get('category')}\n"
    return context if len(relevant) > 0 else "Hiện tại shop đang cập nhật thêm mẫu mới, bạn xem các mẫu bán chạy nhé!"
# Khởi động lần đầu
save_and_reload_data()

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
        CHAT_SESSIONS[session_id] = client.chats.create(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7 # Độ sáng tạo vừa phải để trả lời mượt mà
            )
        )
    # RAG: Lấy ngữ cảnh sản phẩm dựa trên tin nhắn
    product_context = get_relevant_products(user_msg)
# 2. Xử lý input người dùng
    user_parts_for_api = []
    saved_image_bytes = None
    saved_mime_type = "image/jpeg"
    image_payload = None
    if image_data:
        try:
            # Tách header và payload
            if "," in image_data:
                header, image_payload = image_data.split(",", 1)
                if ":" in header and ";" in header:
                    saved_mime_type = header.split(":")[1].split(";")[0]
            else:
                image_payload = image_data

            # Sửa lỗi Padding cho Base64
            missing_padding = len(image_payload) % 4
            if missing_padding:
                image_payload += '=' * (4 - missing_padding)

            # Giải mã 1 lần duy nhất thành bytes
            saved_image_bytes = base64.b64decode(image_payload)
            
            # Chuyển đổi sang PIL Image để gửi cho Gemini
            img = Image.open(BytesIO(saved_image_bytes))
            user_parts_for_api.append(img)
            
        except Exception as e:
            print(f"❌ Lỗi xử lý ảnh: {e}")
            return jsonify({'reply': 'Định dạng ảnh không hợp lệ, bạn gửi lại giúp shop nhé! 🌸'})

    if user_msg:
        user_parts_for_api.append(f"Khách: {user_msg}")
    
    # Kết hợp tin nhắn của khách và ngữ cảnh sản phẩm (RAG)
    full_user_query = f"Bối cảnh sản phẩm: {product_context}\n\nCâu hỏi khách hàng: {user_msg}"
    content_parts = []
    if saved_image_bytes:
        content_parts.append(types.Part.from_bytes(data=saved_image_bytes, mime_type=saved_mime_type))
    content_parts.append(types.Part.from_text(text=full_user_query))

    try:
        # Gửi đến Gemini
        response = CHAT_SESSIONS[session_id].send_message(message=content_parts)
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
        print(f"❌ Lỗi Gemini API: {e}")
        return jsonify({'reply': 'Lily đang bận chuẩn bị đồ một chút, nàng đợi xíu nhé! 🌸'})

if __name__ == '__main__':
    #Tự động cập nhật dữ liệu khi bắt đầu chạy server
    print("⏳ Đang tự động cập nhật sản phẩm từ website OLV...")
    try:
        initial_data = crawl_olv_data(max_pages=5)
        if initial_data:
            save_and_reload_data(initial_data)
        else:
            print("⚠️ Không có dữ liệu mới, sử dụng dữ liệu cũ từ file.")
            save_and_reload_data() # Nạp lại dữ liệu cũ nếu crawl thất bại
    except Exception as e:
        print(f"❌ Lỗi cập nhật lúc khởi động: {e}")
        save_and_reload_data()

    app.run(debug=True)