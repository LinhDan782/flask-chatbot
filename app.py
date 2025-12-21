import os
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai

# Cấu hình
load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    print("Cảnh báo: Chưa cấu hình GEMINI_API_KEY")
else:
    genai.configure(api_key=api_key)
client = genai.Client(api_key=api_key)    
MODEL_ID ="gemini-2.5-flash"

# Biến toàn cục lưu dữ liệu trong RAM
PRODUCT_DATA_TEXT = ""
PRODUCT_LIST_JSON = []

# --- PHẦN 1: HÀM CRAWL DỮ LIỆU TỰ ĐỘNG (SCRAPER) ---
def crawl_olv_data(max_pages=3):
    """Hàm này sẽ đi lấy dữ liệu trực tiếp từ web OLV"""
    base_url = "https://www.olv.vn/collections/tat-ca-san-pham"
    crawled_products = []
    
    headers = {'User-Agent': 'Mozilla/5.0...'} # Giả lập trình duyệt

    print("🚀 Bắt đầu cập nhật dữ liệu từ OLV...")
    
    for page in range(1, max_pages + 1):
        try:
            url = f"{base_url}?sort_by=created-descending&page={page}" # Lấy sản phẩm mới nhất
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            items = soup.find_all('div', class_='product-block')
            
            if not items: break

            for item in items:
                try:
                    name_tag = item.find('h3', class_='pro-name').find('a')
                    price_tag = item.find('p', class_='pro-price')
                    img_tag = item.find('div', class_='product-img').find('img')
                    
                    if name_tag and price_tag:
                        name = name_tag.text.strip()
                        link = "https://www.olv.vn" + name_tag['href']
                        price = price_tag.text.strip().replace('\n', ' ').split('₫')[0] + '₫'
                        
                        img_url = ""
                        if img_tag:
                            src = img_tag.get('src') or img_tag.get('data-src')
                            if src:
                                img_url = "https:" + src if src.startswith('//') else src

                        crawled_products.append({
                            "id": f"OLV_{len(crawled_products)}", # Tạo ID tự động
                            "name": name,
                            "price": price,
                            "sizes": "S, M, L (Xem chi tiết)", 
                            "colors": "Theo hình",
                            "description": f"Sản phẩm {name} chính hãng OLV.",
                            "url": link,
                            "image_url": img_url
                        })
                except Exception as e:
                    continue
        except Exception as e:
            print(f"Lỗi trang {page}: {e}")
            
    print(f"✅ Đã lấy được {len(crawled_products)} sản phẩm.")
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
            
        # Chuyển đổi sang text cho Gemini học
        text_data = ""
        for p in PRODUCT_LIST_JSON:
            text_data += f"- Tên: {p['name']} | Giá: {p['price']}\n"
            text_data += f"  Link: {p['url']}\n"
            text_data += f"  Ảnh: {p['image_url']}\n---\n"
        
        PRODUCT_DATA_TEXT = text_data
        print("🔄 Đã nạp dữ liệu vào bộ nhớ Bot.")
        
    except FileNotFoundError:
        PRODUCT_LIST_JSON = []
        PRODUCT_DATA_TEXT = ""

# Khởi động lần đầu
save_and_reload_data()

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
    
# ===> ROUTE MỚI: Bấm vào đây để cập nhật dữ liệu <===
@app.route('/admin/update-products', methods=['GET'])
def update_products():
    try:
        # 1. Chạy Crawler lấy 2 trang đầu (khoảng 60 sp mới nhất)
        new_data = crawl_olv_data(max_pages=2) 
        
        # 2. Lưu và nạp lại dữ liệu
        save_and_reload_data(new_data)
        
        return jsonify({
            "status": "success", 
            "message": f"Đã cập nhật thành công {len(new_data)} sản phẩm mới nhất!",
            "total_products": len(new_data)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- Route 2: API Chat ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get('message')
    
    if not user_msg:
        return jsonify({'reply': 'Bạn chưa nhập gì cả!'})

    prompt = f"""
    Bạn là AI tư vấn của OLV Boutique.
    Dữ liệu sản phẩm hiện có:
    {PRODUCT_DATA_TEXT}
    Thông tin shop:
    {STATIC_SHOP_INFO}
    Yêu cầu:
    1. Trả lời ngắn gọn, thân thiện (dùng icon 🌸).
    2. Nếu khách hỏi sản phẩm, tìm trong danh sách trên.
    3. Phải có tên, giá và link mua hàng.
    4. Link ảnh gốc trong dữ liệu (image_url) để hiển thị card.
    
    Khách: {user_msg}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        bot_reply = response.text
# Tìm lại thông tin chi tiết để hiển thị thẻ sản phẩm (Product Card)
        product_detail = None
        for p in PRODUCT_LIST_JSON:
            if p['name'] in bot_reply: # So khớp đơn giản
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
