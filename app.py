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
STATIC_SHOP_INFO = """
- Shop: OLV Boutique
- Website mua hàng: https://www.olv.vn/
- Địa chỉ: 224 Yersin, Hiệp Thành, Thủ Dầu Một, Bình Dương
- Liên hệ: 0923003158
- Chính sách: Đổi trả 7 ngày. Freeship đơn > 500k.
"""
SYSTEM_INSTRUCTION = """
Bạn là Lily - Trợ lý bán hàng AI của OLV Boutique.
Nhiệm vụ: Tư vấn và CUNG CẤP LINK ở định dạng Markdown.

QUY TẮC BẮT BUỘC:
1. Khi liệt kê sản phẩm, PHẢI dùng định dạng: 👉 [Tên sản phẩm - Giá](URL)
   Ví dụ: 👉 [Áo Dài Phiêu Vân - 1,490,000đ](https://www.olv.vn/products/ao-dai-phieu-van)
2. Khi dẫn link website, PHẢI dùng: 👉 [Website OLV](https://www.olv.vn/)
3. TUYỆT ĐỐI không được dùng chữ "undefined". Nếu không biết link, hãy dùng https://www.olv.vn/
4. Trả lời ngắn gọn, thân thiện.

Bối cảnh cửa hàng:
{shop_info}
"""
SYSTEM_INSTRUCTION = SYSTEM_INSTRUCTION.format(shop_info=STATIC_SHOP_INFO)

# Biến toàn cục lưu dữ liệu trong RAM
PRODUCT_DATA_TEXT = ""
PRODUCT_LIST_JSON = []
CHAT_SESSIONS = {}
# Bật / Tắt Gemini để test thực nghiệm
USE_GEMINI = True   # True: bật Gemini | False: tắt Gemini

# --- PHẦN 1: HÀM CRAWL DỮ LIỆU TỰ ĐỘNG ---
def crawl_olv_data(max_pages=3):
    """Hàm lấy dữ liệu từ nhiều danh mục, duyệt qua nhiều trang"""
    categories = {
        "Giảm giá": "https://www.olv.vn/pages/flash-sale",
        "Bán chạy": "https://www.olv.vn/collections/san-pham-ban-chay",
        "Tất cả sản phẩm": "https://www.olv.vn/collections/tat-ca-san-pham",
    }
    
    crawled_products = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    print("🚀 Bắt đầu cập nhật dữ liệu từ OLV...")
    
    for cat_name, base_url in categories.items():
        for page in range(1, max_pages + 1): # Vòng lặp duyệt page
            try:
                url = f"{base_url}?page={page}"
                print(f"--- Đang truy cập: {cat_name} (Trang {page}) ...")
                
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Tìm khối sản phẩm
                items = soup.find_all('div', class_=['product-block', 'product-item', 'col-md-3'])
                
                if not items:
                    print(f"   ⚠️ Không tìm thấy sản phẩm ở trang {page}, dừng danh mục này.")
                    break # Hết sản phẩm thì dừng, qua danh mục khác
                
                for item in items:
                    try:
                        name_tag = item.find(['h3', 'h4'], class_=['pro-name', 'product-title'])
                        price_tag = item.find(['p', 'span'], class_=['pro-price', 'current-price', 'price'])
                        
                        if name_tag and price_tag:
                            name = name_tag.get_text(strip=True)
                            
                            # Lấy link và xử lý link tương đối
                            a_tag = name_tag.find('a')
                            href = a_tag.get('href', '') if a_tag else ""
                            if not href.startswith('http'):
                                product_url = "https://www.olv.vn" + ("" if href.startswith('/') else "/") + href
                            else:
                                product_url = href

                            # Xử lý giá
                            full_price_text = price_tag.get_text(strip=True)
                            clean_price = full_price_text.split('₫')[0].strip().replace('\n', '') + '₫'
                            
                            # Lấy ảnh
                            img_tag = item.find('img')
                            img_url = "https://theme.hstatic.net/200000039986/1000723835/14/share_fb_home.png?v=999" # Ảnh mặc định nếu lỗi
                            if img_tag:
                                raw_img = img_tag.get('data-src') or img_tag.get('src')
                                if raw_img:
                                    if raw_img.startswith('//'):
                                        img_url = "https:" + raw_img
                                    elif raw_img.startswith('http'):
                                        img_url = raw_img

                            # Kiểm tra trùng lặp ID hoặc Tên
                            if not any(p['name'] == name for p in crawled_products):
                                crawled_products.append({
                                    "id": f"OLV_{len(crawled_products)}",
                                    "name": name,
                                    "price": clean_price,
                                    "category": cat_name,
                                    "url": product_url,
                                    "image_url": img_url
                                })
                    except Exception as loop_e:
                        continue
            except Exception as e:
                print(f"❌ Lỗi trang {page}: {e}")
                continue
                                    
    if len(crawled_products) == 0:
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
    query_lc = query.lower() if query else ""
    context = "DANH SÁCH SẢN PHẨM KHẢ DỤNG (Dùng link này để trả lời):\n"
    # Ưu tiên thông tin Website
    context += f"- Website chính thức: https://www.olv.vn/\n"
    # Tìm kiếm sản phẩm
    relevant = [p for p in PRODUCT_LIST_JSON if query_lc in p['name'].lower()]
    if not relevant:
        relevant = PRODUCT_LIST_JSON[:top_k] # Lấy mẫu nếu không thấy
    
    for p in relevant[:top_k]:
        # Tạo cấu trúc rõ ràng: Tên | Giá | Link
        context += f"Sản phẩm: {p['name']} | Giá: {p['price']} | Link: {p['url']}\n"
        
    return context
# --- TEST MÔ HÌNH 1: Tìm kiếm truyền thống (không AI) ---
def search_products_traditional(query):
    query = query.lower()
    results = []

    for p in PRODUCT_LIST_JSON:
        if query in p['name'].lower():
            results.append(p)

    return results[:5]
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
    
    # Nếu tắt Gemini → dùng tìm kiếm truyền thống
    if not USE_GEMINI:
        results = search_products_traditional(user_msg)
        
        if results:
            reply = "Shop tìm thấy các sản phẩm sau:\n"
            for p in results:
                reply += f"👉 [{p['name']} - {p['price']}]({p['url']})\n"
        else:
            reply = "Hiện chưa tìm thấy sản phẩm phù hợp."
        
        return jsonify({
            "reply": reply,
            "product_info": results[0] if results else None
        })
    
    # Nếu bật Gemini → chạy hệ thống AI hiện tại
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