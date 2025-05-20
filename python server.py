from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import threading

app = Flask(__name__)

# Thread-safe list of received pings
pings = []
pings_lock = threading.Lock()

# HTML template for dashboard
DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <title>Ping Dashboard</title>
  <style>
    body { font-family: sans-serif; margin: 2em; }
    .item { padding: 0.5em; border-bottom: 1px solid #ddd; }
    .time { color: #555; font-size: 0.9em; }
    pre { background: #f9f9f9; padding: 0.5em; }
  </style>
</head>
<body>
  <h1>Received Pings</h1>
  {% for entry in entries %}
    <div class="item">
      <div class="time">[{{ entry.time }}] from {{ entry.source }}</div>
      <pre>{{ entry.data }}</pre>
    </div>
  {% else %}
    <p><em>No pings received yet.</em></p>
  {% endfor %}
</body>
</html>
"""

@app.route('/ping', methods=['POST'])
def receive_ping():
    """Accepts JSON POSTs at /ping and stores them."""
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "message": str(e)}), 400

    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": request.remote_addr,
        "data": data
    }
    with pings_lock:
        pings.append(entry)
    print(f"[+] {entry['time']} ← {entry['source']}  {data}")
    return jsonify({"status": "ok"}), 200

@app.route('/')
def dashboard():
    """Renders an HTML dashboard of all received pings."""
    with pings_lock:
        entries = list(reversed(pings))
    return render_template_string(DASHBOARD_HTML, entries=entries)

@app.route('/api/pings', methods=['GET'])
def api_pings():
    """Returns all received pings as JSON."""
    with pings_lock:
        return jsonify(pings)

if __name__ == '__main__':
    # Listen on all interfaces so your ESP32 can reach it
    app.run(host='0.0.0.0', port=5000, debug=True)
