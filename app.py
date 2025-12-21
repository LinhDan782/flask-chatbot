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
client = genai.Client(api_key=api_key)    
MODEL_ID ="gemini-2.5-flash"

# Biến toàn cục lưu dữ liệu trong RAM
PRODUCT_DATA_TEXT = ""
PRODUCT_LIST_JSON = []

# --- PHẦN 1: HÀM CRAWL DỮ LIỆU TỰ ĐỘNG ---
def crawl_olv_data():
    """Hàm lấy dữ liệu từ nhiều danh mục khác nhau"""
    categories = {
        "Giảm giá (Flash Sale)": "https://www.olv.vn/pages/flash-sale",
        "Hàng mới về (Pure Fairy)": "https://www.olv.vn/collections/pure-fairy",
        "Bán chạy": "https://www.olv.vn/collections/san-pham-ban-chay",
        "Tất cả sản phẩm": "https://www.olv.vn/collections/tat-ca-san-pham",
    }
    
    crawled_products = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    print("🚀 Bắt đầu cập nhật dữ liệu từ các danh mục OLV...")
    
    for cat_name, url in categories.items():
        try:
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            # Lưu ý: Một số trang Flash Sale có thể dùng class khác, 
            # nhưng thông thường OLV dùng 'product-block' cho hầu hết danh mục.
            items = soup.find_all('div', class_='product-block')
            
            print(f"--- Đang lấy {len(items)} sản phẩm từ: {cat_name}")

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
                            "id": f"OLV_{len(crawled_products)}",
                            "name": name,
                            "price": price,
                            "category": cat_name, # Thêm nhãn danh mục để Bot biết
                            "url": link,
                            "image_url": img_url
                        })
                except: continue
        except Exception as e:
            print(f"Lỗi khi lấy dữ liệu {cat_name}: {e}")
            
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
    Bạn là AI tư vấn chuyên nghiệp của OLV Boutique. 🌸
    Dữ liệu sản phẩm (bao gồm Hàng mới, Giảm giá, Bán chạy, Tất cả sản phẩm):
    {PRODUCT_DATA_TEXT}
    Thông tin shop:
    {STATIC_SHOP_INFO}
    Yêu cầu:
    1. Trả lời ngắn gọn, thân thiện (dùng icon 🌸).
    2. Khi khách hỏi về "giảm giá", "sale", "hàng mới" hoặc "bán chạy", hãy lọc trong dữ liệu theo phần 'Nhóm' tương ứng để trả lời.
    3. Nếu có nhiều sản phẩm, hãy gợi ý khoảng 3-4 mẫu nổi bật nhất.
    4. Luôn kèm theo giá và mô tả ngắn gọn, thân thiện.
    5. Không hiển thị URL trực tiếp trong câu trả lời văn bản.
    6. Chỉ cần nhắc đến tên sản phẩm chính xác như trong dữ liệu để hệ thống tự hiển thị thẻ sản phẩm.
    
    Khách: {user_msg}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        bot_reply = response.text
        product_detail = None
        # Duyệt qua danh sách sản phẩm để tìm sản phẩm được nhắc đến đầu tiên
        for p in PRODUCT_LIST_JSON:
            # Kiểm tra xem tên sản phẩm có xuất hiện trong câu trả lời của Bot không
            if p['name'].lower() in bot_reply.lower(): 
                product_detail = p
                break # Lấy sản phẩm đầu tiên tìm thấy để hiển thị Card
                
        return jsonify({
            'reply': bot_reply,
            'product_info': product_detail
        })
        
    except Exception as e:
        print(e)
        return jsonify({'reply': 'Hệ thống đang bảo trì một chút xíu ạ 😅'})

if __name__ == '__main__':
    app.run(debug=True)
