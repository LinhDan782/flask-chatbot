from flask import Flask, request, render_template_string
from flask import Flask
from flask_session import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

# ====== Huấn luyện mô hình học máy ======
data = [
    ("giờ làm việc của bạn là gì", "working_hours"),
    ("khi nào mở cửa", "working_hours"),
    ("có làm việc cuối tuần không", "working_hours"),
    ("bạn mở cửa lúc mấy giờ", "working_hours"),

    ("chính sách hoàn tiền thế nào", "refund_policy"),
    ("tôi muốn đổi/trả hàng", "refund_policy"),
    ("trả hàng mất phí không", "refund_policy"),
    ("tôi đã mua sai, hoàn tiền được không", "refund_policy"),

    ("tôi muốn liên hệ", "contact"),
    ("làm sao để gọi cho bạn", "contact"),
    ("email hỗ trợ của bạn là gì", "contact"),
    ("số điện thoại của shop là gì", "contact"),

    ("bạn có ship không", "shipping"),
    ("phí giao hàng là bao nhiêu", "shipping"),
    ("ship COD không", "shipping"),
    ("giao hàng mất bao lâu", "shipping"),
]
texts, labels = zip(*data)
vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(texts)
clf = MultinomialNB()
clf.fit(X, labels)

# ====== Các phản hồi theo intent ======
intent_responses = {
    "working_hours": "⏰ Chúng tôi làm việc từ 8h đến 17h, từ thứ 2 đến thứ 6.",
    "refund_policy": "💸 Bạn có thể hoàn trả trong vòng 7 ngày kể từ ngày mua.",
    "contact": "📞 Bạn có thể liên hệ qua email: support@example.com hoặc gọi 0123.456.789.",
    "shipping": "🚚 Chúng tôi giao hàng toàn quốc, hỗ trợ COD và phí giao từ 20K tuỳ khu vực."
}

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Giao diện HTML đơn giản
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Chatbot thông minh</title>
    <style>
        body, html {
            margin: 0;
            padding: 0;
            height: 100%%;
            font-family: Arial, sans-serif;
            background-color: #f0f2f5;
        }
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 100%%;
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            border-radius: 0;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        .messages {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }
        .message {
            padding: 10px 15px;
            border-radius: 20px;
            margin-bottom: 10px;
            max-width: 75%%;
            display: inline-block;
            clear: both;
        }
        .user {
            background-color: #0084ff;
            color: white;
            float: right;
        }
        .bot {
            background-color: #e4e6eb;
            color: black;
            float: left;
        }
        form {
            display: flex;
            border-top: 1px solid #ccc;
        }
        input[name="message"] {
            flex: 1;
            padding: 15px;
            border: none;
            font-size: 16px;
        }
        input[type="submit"] {
            background-color: #0084ff;
            color: white;
            border: none;
            padding: 15px 25px;
            cursor: pointer;
            font-size: 16px;
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="messages" id="messages">
            {% for m in history %}
                <div class="message user">{{ m[0] }}</div>
                <div class="message bot">{{ m[1] }}</div>
            {% endfor %}
        </div>
        <form method="POST">
            <input name="message" placeholder="Nhập tin nhắn..." autocomplete="off" required />
            <input type="submit" value="Gửi" />
        </form>
    </div>
    <script>
        var messagesDiv = document.getElementById("messages");
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    </script>
</body>
</html>
"""

# Tạo ứng dụng Flask
@app.route("/", methods=["GET", "POST"])
def chatbot():
    if 'history' not in Session:
        Session['history'] = []

    if request.method == "POST":
        user_message = request.form['message']
        response = "🤖 Xin lỗi, tôi chưa hiểu câu hỏi."
        for key in faq:
            if key in user_message.lower():
                response = faq[key]
                break
        Session['history'].append((user_message, response))
        Session.modified = True
        return redirect(url_for('chatbot'))

    return render_template_string(HTML_TEMPLATE, history=Session['history'])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
app.run()
