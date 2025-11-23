from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# --- CẤU HÌNH GEMINI ---
# Dán API Key của bạn vào đây
genai.configure(api_key='DÁN_API_KEY_CỦA_BẠN_VÀO_ĐÂY') 

model = genai.GenerativeModel('gemini-1.5-flash')

# Dữ liệu shop của bạn
SHOP_DATA = """
- Shop tên: Vintage Store.
- Giờ làm việc: 8h - 22h hàng ngày.
- Địa chỉ: 123 Đường ABC, Quận 1.
- Chính sách: Đổi trả trong 3 ngày nếu lỗi.
- Ship: Đồng giá 30k toàn quốc.
"""

app = Flask(__name__)
CORS(app)

# Giao diện
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chatbot Shop</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', sans-serif;
        }

        body {
            /* Hình nền */
            background-image: url('https://images.unsplash.com/photo-1557683316-973673baf926?q=80&w=2029&auto=format&fit=crop');
            background-size: cover;
            background-position: center;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        /* Khung điện thoại mô phỏng */
        .phone-container {
            width: 100%;
            max-width: 400px;
            height: 90vh;
            background: rgba(255, 255, 255, 0.1); /* Nền kính mờ */
            backdrop-filter: blur(15px); /* Hiệu ứng làm mờ hậu cảnh */
            border-radius: 30px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            display: flex;
            flex-direction: column;
            box-shadow: 0 20px 50px rgba(0,0,0,0.3);
            overflow: hidden;
            position: relative;
        }
        /* Khu vực hiển thị tin nhắn */
        .chat-box {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 15px;
            /* Scrollbar ẩn cho đẹp */
            scrollbar-width: none; 
        }
        .chat-box::-webkit-scrollbar { display: none; }

        /* Bong bóng chat */
        .message {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 0.95rem;
            line-height: 1.4;
            position: relative;
            animation: fadeIn 0.3s ease;
        }

        /* Tin nhắn của Bot (Bên trái) */
        .message.bot {
            align-self: flex-start;
            background: rgba(255, 255, 255, 0.85);
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }

        /* Tin nhắn của Khách (Bên phải) */
        .message.user {
            align-self: flex-end;
            background: #6C63FF; /* Màu tím giống style bên phải hoặc xanh */
            color: white;
            border-bottom-right-radius: 4px;
            box-shadow: 0 2px 10px rgba(108, 99, 255, 0.3);
        }

        /* Khu vực nhập liệu */
        .input-area {
            padding: 20px;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .input-wrapper {
            flex: 1;
            position: relative;
        }

        input {
            width: 100%;
            padding: 14px 45px 14px 20px;
            border-radius: 30px;
            border: none;
            background: rgba(255, 255, 255, 0.9);
            outline: none;
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        input:focus {
            box-shadow: 0 0 0 2px #6C63FF;
        }

        /* Nút gửi */
        .send-btn {
            background: #6C63FF;
            color: white;
            border: none;
            width: 45px;
            height: 45px;
            border-radius: 50%;
            cursor: pointer;
            transition: 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .send-btn:hover {
            transform: scale(1.1);
        }

        /* Hiệu ứng xuất hiện */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        </style>
</head>
<body>

    <div class="phone-container">
        <img src="https://cdn3d.iconscout.com/3d/premium/thumb/robot-assistant-5649462-4706751.png" class="character-overlay" alt="Bot">

        <div class="header">
            <div class="status-badge">● Online</div>
            <h3>Trợ lý Shop</h3>
            <p style="font-size: 0.8rem; opacity: 0.8;">Luôn sẵn sàng hỗ trợ bạn</p>
        </div>

        <div class="chat-box" id="chatBox">
            <div class="message bot">
                Chào bạn! 👋 Mình là trợ lý ảo của Shop. Hôm nay mình có thể giúp gì cho bạn nè?
            </div>
        </div>

        <div class="input-area">
            <div class="input-wrapper">
                <input type="text" id="userInput" placeholder="Nhập câu hỏi..." onkeypress="handleEnter(event)">
            </div>
            <button class="send-btn" onclick="sendMessage()">
                <i class="fas fa-paper-plane"></i>
            </button>
        </div>
    </div>

    <script>
        function handleEnter(e) {
            if (e.key === 'Enter') sendMessage();
        }

        function sendMessage() {
            const input = document.getElementById('userInput');
            const chatBox = document.getElementById('chatBox');
            const message = input.value.trim();

            if (message) {
                // 1. Hiển thị tin nhắn người dùng
                appendMessage(message, 'user');
                input.value = '';

                // 2. Giả lập Bot đang gõ (typing...)
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'message bot';
                loadingDiv.innerHTML = '<i class="fas fa-ellipsis-h fa-spin"></i>';
                loadingDiv.id = 'loading';
                chatBox.appendChild(loadingDiv);
                chatBox.scrollTop = chatBox.scrollHeight;

                // 3. GỌI API GEMINI
                fetch('http://127.0.0.1:5000/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
                })
                .then(response => response.json())
                .then(data => {
                    // Xóa icon loading
                    document.getElementById('loading').remove();
                    // Bot trả lời
                    appendMessage(data.reply, 'bot'); // Hiển thị câu trả lời của Gemini
                    .catch(error => {
                    console.error('Lỗi:', error);
                    document.getElementById('loading').remove();
                    appendMessage("Lỗi kết nối server rồi bạn ơi!", 'bot');
                    });
            }
        }
        function appendMessage(text, sender) {
            const chatBox = document.getElementById('chatBox');
            const div = document.createElement('div');
            div.className = `message ${sender}`;
            div.textContent = text;
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight; // Tự cuộn xuống cuối
        }
    </script>
</body>
</html>
"""

# Tạo ứng dụng Flask
@app.route('/chat', methods=['POST'])
def chat():
    # 1. Nhận tin nhắn từ file giao diện HTML gửi lên
    data = request.json
    user_msg = data.get('message')
    
    if not user_msg:
        return jsonify({'reply': 'Bạn chưa nhập gì cả!'})

    # 2. Gửi cho Gemini xử lý
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
        bot_reply = "Xin lỗi, hệ thống đang bận. Bạn thử lại sau nhé!"

    # 3. Trả câu trả lời về cho giao diện HTML
    return jsonify({'reply': bot_reply})

# Chạy server
if __name__ == '__main__':
    print("Server đang chạy tại http://127.0.0.1:5000")
    app.run(port=5000, debug=True)
