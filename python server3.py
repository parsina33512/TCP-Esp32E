import threading
import socket
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

app = Flask(__name__)
data_lock = threading.Lock()
received_data = []

TCP_HOST = "0.0.0.0"
HTTP_PORT = 8000

@app.route('/api/update', methods=['POST'])
def update():
    payload = request.get_json(force=True, silent=True)
    timestamp = datetime.now().isoformat()
    entry = {
        "timestamp": timestamp,
        "source": f"http:{request.remote_addr}:{request.environ.get('REMOTE_PORT')}",
        "data": payload
    }
    with data_lock:
        received_data.append(entry)
    print("📥 HTTP POST:", entry)
    return jsonify({"status":"ok"}),200

@app.route('/')
def dashboard():
    html = """
    <html>
      <head><title>ESP32 Data</title></head>
      <body>
        <h1>Received Data (newest first)</h1>
        {% for e in data %}
          <pre>[{{e.timestamp}}] {{e.source}}
{{ e.data | tojson(indent=2) }}</pre>
        {% endfor %}
      </body>
    </html>
    """
    with data_lock:
        data = list(reversed(received_data))
    return render_template_string(html, data=data)

def run_http():
    app.run(host='0.0.0.0', port=8000, debug=True)

if __name__=="__main__":
    print(f"🌐 HTTP Server on port {HTTP_PORT}")
    run_http()
