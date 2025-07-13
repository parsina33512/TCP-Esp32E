from flask import Flask, request, render_template_string, jsonify, redirect, flash, url_for
from datetime import datetime
import json, os, requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ─── In‐memory store of all received Modbus packets ─────────────────
received_data = []

# ─── Where your ESP32 lives on the LAN (for sending config & firmware) ─
ESP32_IP   = "192.168.100.85"
ESP32_PORT = 80   # ESP32's EthernetServer is on port 80

# ─────────────────────────────────────────────────────────────────────
#  1) Endpoint for ESP32 to push BMS data (including modbusError)
# ─────────────────────────────────────────────────────────────────────
@app.route('/update', methods=['POST'])
def update():
    data = request.get_json(silent=True)
    if data is None:
        raw = request.form.get('data', '')
        if raw:
            try:
                data = json.loads(raw)
            except:
                return "Bad JSON", 400
        else:
            return "No data provided", 400
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data":      data
    }
    received_data.append(entry)
    print(f"\n[ BMS DATA RECEIVED at {entry['timestamp']} ]")
    print(json.dumps(data, indent=2))
    return "ACK", 200, {"Connection": "close"}

# ─────────────────────────────────────────────────────────────────────
#  1.5) Endpoint for ESP32 to push its network config
# ─────────────────────────────────────────────────────────────────────
@app.route('/config', methods=['POST'])
def receive_config():
    data = request.get_json(silent=True)
    if data is None:
        raw = request.form.get('data', '')
        if raw:
            try:
                data = json.loads(raw)
            except:
                return "Bad JSON", 400
        else:
            return "No data provided", 400
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[ CONFIG RECEIVED at {ts} ]")
    print(json.dumps(data, indent=2))
    return "CONFIG-ACK", 200, {"Connection": "close"}

# ─────────────────────────────────────────────────────────────────────
#  2) Browser polls this for BMS JSON history
# ─────────────────────────────────────────────────────────────────────
@app.route('/data', methods=['GET'])
def get_data():
    return jsonify(received_data)

# ─────────────────────────────────────────────────────────────────────
#  3) Dashboard & Config Page
# ─────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        new_config = {
            'localIP':        request.form.get('localIP', '').strip(),
            'gateway':        request.form.get('gateway', '').strip(),
            'subnet':         request.form.get('subnet', '').strip(),
            'serverIP':       request.form.get('serverIP', '').strip(),
            'serverPort':     request.form.get('serverPort', '').strip(),
            'modbusInterval': request.form.get('modbusInterval', '').strip(),
            'networkInterval':request.form.get('networkInterval', '').strip()
        }
        try:
            resp = requests.post(
                f"http://{ESP32_IP}:{ESP32_PORT}/config",
                 data=new_config,
                timeout=5
            )
            if resp.ok:
                flash("✅ Configuration sent to ESP32 successfully!")
            else:
                flash(f"⚠️ ESP32 responded: {resp.status_code} {resp.text}")
        except Exception as e:
            flash(f"❌ Error sending config to ESP32: {e}")
        return redirect(url_for('index'))

    esp_config = {
        'localIP':'', 'gateway':'', 'subnet':'',
        'serverIP':'', 'serverPort':'',
        'modbusInterval':'', 'networkInterval':''
    }
    try:
        cfg_resp = requests.get(f"http://{ESP32_IP}:{ESP32_PORT}/config", timeout=3)
        if cfg_resp.ok:
            parsed = cfg_resp.json()
            for key in esp_config:
                esp_config[key] = parsed.get(key, '')
    except Exception as e:
        print(f"⚠️ Could not fetch ESP32 /config: {e}")

    return render_template_string(DASHBOARD_HTML,
        received_data=received_data,
        esp_config=esp_config,
        esp_url=f"{ESP32_IP}:{ESP32_PORT}"
    )

# ─────────────────────────────────────────────────────────────────────
#  4) Firmware upload form & forwarding
# ─────────────────────────────────────────────────────────────────────
@app.route('/fw', methods=['GET'])
def fw_form():
    return render_template_string('''
      <!DOCTYPE html>
      <html>
        <head><title>ESP32 Ethernet Firmware Update</title></head>
        <body>
          <h1>Upload New Firmware (.bin)</h1>
          <form action="/fw" method="post" enctype="multipart/form-data">
            <input type="file" name="fw" accept=".bin"><button>Flash ESP32</button>
          </form>
        </body>
      </html>
    ''')

@app.route('/fw', methods=['POST'])
def fw_upload():
    file = request.files.get('fw')
    if not file:
        flash("❌ No firmware file uploaded")
        return redirect(url_for('fw_form'))

    # --- DEBUG: report incoming file size ---
    content = file.read()
    size = len(content)
    print(f"[ FW_UPLOAD ] Received firmware file of {size} bytes")
    file.stream.seek(0)

    # save to temp
    temp_path = os.path.join('/tmp', file.filename)
    file.save(temp_path)
    print(f"[ FW_UPLOAD ] Saved to {temp_path}")

    # NEW - USES CORRECT OTA PORT 8080
    url = f"http://{ESP32_IP}:8080/update"
    try:
        with open(temp_path, 'rb') as f_data:
            resp = requests.post(
                url,
                data=f_data,
                headers={"Content-Type": "application/octet-stream"},
                timeout=60
            )
        print(f"[ FW_UPLOAD ] ESP32 responded: {resp.status_code} {resp.text}")
    except Exception as e:
        flash(f"❌ Error forwarding to ESP32: {e}")
        os.remove(temp_path)
        return redirect(url_for('fw_form'))
    finally:
        os.remove(temp_path)

    flash(f"ESP32 responded: {resp.status_code} {resp.text}")
    return redirect(url_for('fw_form'))

# ─────────────────────────────────────────────────────────────────────
#  HTML template for dashboard
# ─────────────────────────────────────────────────────────────────────
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>BMS Monitoring Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .card { border: 1px solid #ddd; padding: 15px; margin: 10px; border-radius: 5px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap: 10px; }
    .timestamp { color: #666; font-size: 0.9em; margin-bottom: 5px; }
    .flash-messages { margin-bottom: 20px; }
    .flash { background: #eef; padding: 10px; border: 1px solid #99c; margin-bottom: 5px; }
    form { margin-top: 30px; }
    form input { width: 250px; margin-bottom: 10px; }
  </style>
  <script>
    async function fetchData() {
      let resp = await fetch('/data');
      let arr  = await resp.json();
      const container = document.getElementById('data-container');
      container.innerHTML = '';
      arr.slice().reverse().forEach(entry => {
        const div = document.createElement('div');
        div.className = 'card';
        div.innerHTML = `
          <div class="timestamp">${entry.timestamp}</div>
          <h3>BMS Status</h3>
          <div class="grid">
            <div>Pack Voltage:       ${entry.data.pack_voltage} V</div>
            <div>Current:            ${entry.data.current} A</div>
            <div>Remaining Capacity: ${entry.data.capacity_remaining} Ah</div>
            <div>SOC:                ${entry.data.soc}%</div>
            <div>SOH:                ${entry.data.soh}%</div>
            <div>Avg Cell Temp:      ${entry.data.avg_cell_temp} °C</div>
            <div>Env Temp:           ${entry.data.env_temp} °C</div>
            <div>Cycles:             ${entry.data.cycles}</div>
            <div>Max Cell Voltage:   ${entry.data.max_cell_voltage} V</div>
            <div>Min Cell Voltage:   ${entry.data.min_cell_voltage} V</div>
            <div>Modbus Error:       ${entry.data.modbusError ? "Yes" : "No"}</div>
          </div>`;
        container.appendChild(div);
      });
    }
    setInterval(fetchData, 1000);
    window.onload = fetchData;
  </script>
</head>
<body>
  <h1>BMS Monitoring System</h1>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="flash-messages">
        {% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}
      </div>
    {% endif %}
  {% endwith %}
  <div id="data-container"></div>
  <hr>
  <h2>Network Configuration for ESP32</h2>
  <p>(This will POST to <code>http://{{ esp_url }}/config</code>)</p>
  <form method="post" action="/">
    Local IP:        <input type="text" name="localIP"  value="{{ esp_config.localIP }}"><br>
    Gateway:         <input type="text" name="gateway"  value="{{ esp_config.gateway }}"><br>
    Subnet:          <input type="text" name="subnet"   value="{{ esp_config.subnet }}"><br>
    Server IP:       <input type="text" name="serverIP" value="{{ esp_config.serverIP }}"><br>
    Server Port:     <input type="text" name="serverPort" value="{{ esp_config.serverPort }}"><br>
    Modbus Interval: <input type="text" name="modbusInterval"  value="{{ esp_config.modbusInterval }}"><br>
    Network Interval:<input type="text" name="networkInterval" value="{{ esp_config.networkInterval }}"><br>
    <br><input type="submit" value="Save Configuration">
  </form>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
