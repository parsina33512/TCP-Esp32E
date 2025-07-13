from flask import Flask, request, render_template_string, jsonify, redirect, flash, url_for
from datetime import datetime
import json, os, requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- In-memory store ---
# We will only store the MOST RECENT data packet from the ESP32
latest_data_entry = {
    "timestamp": "Never",
    "data": {"slaves": []} # Initialize with an empty slaves array
}

# --- Configuration ---
# IMPORTANT: Update this to the IP your ESP32 will actually have.
# Based on your config, this should be 192.168.100.250
ESP32_IP   = "192.168.100.250"
ESP32_PORT = 80      # The port for the configuration web server
OTA_PORT   = 8080    # The port for the firmware update server

# ─────────────────────────────────────────────────────────────────────
# 1) Endpoint for ESP32 to push multi-slave BMS data
# ─────────────────────────────────────────────────────────────────────
@app.route('/update', methods=['POST'])
def update():
    global latest_data_entry
    raw = request.form.get('data', '')
    if not raw:
        return "No data in form", 400
    try:
        data = json.loads(raw)
        # Basic validation to ensure the expected 'slaves' key exists
        if 'slaves' not in data or not isinstance(data['slaves'], list):
            return "Invalid JSON structure", 400
    except json.JSONDecodeError:
        return "Bad JSON format", 400

    # Update the single latest data entry
    latest_data_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data
    }
    print(f"\n[ BMS DATA RECEIVED at {latest_data_entry['timestamp']} ]")
    print(json.dumps(data, indent=2))
    return "ACK", 200

# ─────────────────────────────────────────────────────────────────────
# 2) Browser polls this for the latest multi-slave JSON data
# ─────────────────────────────────────────────────────────────────────
@app.route('/data', methods=['GET'])
def get_data():
    return jsonify(latest_data_entry)

# ─────────────────────────────────────────────────────────────────────
# 3) Dashboard & Config Page
# ─────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        new_config = {
            'localIP':         request.form.get('localIP', '').strip(),
            'gateway':         request.form.get('gateway', '').strip(),
            'subnet':          request.form.get('subnet', '').strip(),
            'serverIP':        request.form.get('serverIP', '').strip(),
            'serverPort':      request.form.get('serverPort', '').strip(),
            'modbusInterval':  request.form.get('modbusInterval', '').strip(),
            'networkInterval': request.form.get('networkInterval', '').strip()
        }
        try:
            # CORRECTED: Send as form data, not JSON
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

    # Fetch current config from ESP32 to populate the form
    esp_config = {}
    try:
        cfg_resp = requests.get(f"http://{ESP32_IP}:{ESP32_PORT}/config", timeout=3)
        if cfg_resp.ok:
            esp_config = cfg_resp.json()
    except Exception as e:
        print(f"⚠️ Could not fetch ESP32 /config: {e}")

    return render_template_string(DASHBOARD_HTML, esp_config=esp_config)

# ─────────────────────────────────────────────────────────────────────
# 4) Firmware upload form & forwarding
# ─────────────────────────────────────────────────────────────────────
@app.route('/fw', methods=['GET', 'POST'])
def fw_upload():
    if request.method == 'GET':
        return render_template_string('''
            <!DOCTYPE html><html><head><title>Firmware Update</title></head>
            <body><h1>Upload New Firmware (.bin) for {{esp_ip}}:{{ota_port}}</h1>
            <form method="post" enctype="multipart/form-data">
            <input type="file" name="firmware" accept=".bin"><button>Flash ESP32</button>
            </form></body></html>
        ''', esp_ip=ESP32_IP, ota_port=OTA_PORT)

    file = request.files.get('firmware')
    if not file:
        flash("❌ No firmware file provided.")
        return redirect(url_for('fw_upload'))

    try:
        # CORRECTED: Use the dedicated OTA port
        url = f"http://{ESP32_IP}:{OTA_PORT}/update"
        firmware_data = file.read()
        print(f"Uploading {len(firmware_data)} bytes to {url}")
        
        resp = requests.post(
            url,
            data=firmware_data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=60
        )
        flash(f"✅ ESP32 Response: {resp.status_code} - {resp.text}")
    except Exception as e:
        flash(f"❌ Error forwarding firmware to ESP32: {e}")
    
    return redirect(url_for('fw_upload'))

# ─────────────────────────────────────────────────────────────────────
# HTML template for the multi-slave dashboard
# ─────────────────────────────────────────────────────────────────────
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Multi-BMS Monitoring Dashboard</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; background-color: #f4f7f6; }
    .header { background-color: #fff; padding: 20px; border-bottom: 1px solid #ddd; }
    .container { padding: 20px; }
    .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
    .card { background-color: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .card.disconnected { background-color: #fafafa; opacity: 0.6; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
    .slave-id { font-weight: bold; font-size: 1.2em; }
    .status { padding: 5px 10px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
    .status.connected { background-color: #d4edda; color: #155724; }
    .status.disconnected { background-color: #f8d7da; color: #721c24; }
    .data-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9em; }
    .data-item { display: flex; justify-content: space-between; }
    .data-item span:first-child { color: #555; }
    .timestamp { text-align: center; color: #888; margin-bottom: 20px; }
    .config-form { margin-top: 40px; }
    .flash { padding: 15px; margin-bottom: 20px; border-radius: 4px; }
    .flash.success { background-color: #d4edda; color: #155724; }
    .flash.error { background-color: #f8d7da; color: #721c24; }
  </style>
  <script>
    async function fetchData() {
      try {
        const resp = await fetch('/data');
        const json_data = await resp.json();
        const container = document.getElementById('grid-container');
        const timestampEl = document.getElementById('timestamp');
        
        timestampEl.textContent = `Last Update: ${json_data.timestamp}`;
        container.innerHTML = ''; // Clear previous cards

        if (json_data.data.slaves && json_data.data.slaves.length > 0) {
            json_data.data.slaves.forEach(slave => {
                const card = document.createElement('div');
                let cardContent = '';

                if (slave.status === 'connected') {
                    card.className = 'card connected';
                    cardContent = `
                        <div class="card-header">
                            <span class="slave-id">BMS Slave #${slave.id}</span>
                            <span class="status connected">Connected</span>
                        </div>
                        <div class="data-grid">
                            <div class="data-item"><span>Pack Voltage:</span> <span>${slave.pack_voltage.toFixed(2)} V</span></div>
                            <div class="data-item"><span>Current:</span> <span>${slave.current.toFixed(2)} A</span></div>
                            <div class="data-item"><span>SOC:</span> <span>${slave.soc.toFixed(1)}%</span></div>
                            <div class="data-item"><span>SOH:</span> <span>${slave.soh.toFixed(1)}%</span></div>
                            <div class="data-item"><span>Avg Temp:</span> <span>${slave.avg_cell_temp.toFixed(1)} °C</span></div>
                            <div class="data-item"><span>Cycles:</span> <span>${slave.cycles}</span></div>
                        </div>
                    `;
                } else {
                    card.className = 'card disconnected';
                    cardContent = `
                        <div class="card-header">
                            <span class="slave-id">BMS Slave #${slave.id}</span>
                            <span class="status disconnected">Disconnected</span>
                        </div>
                    `;
                }
                card.innerHTML = cardContent;
                container.appendChild(card);
            });
        } else {
            container.innerHTML = '<p>Waiting for first data packet from ESP32...</p>';
        }
      } catch (error) {
        console.error("Failed to fetch data:", error);
      }
    }
    setInterval(fetchData, 2000);
    window.onload = fetchData;
  </script>
</head>
<body>
  <div class="header">
    <h1>Multi-BMS Monitoring Dashboard</h1>
  </div>

  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <div id="timestamp">Loading...</div>
    <div id="grid-container">
      <p>Waiting for data from ESP32...</p>
    </div>

    <div class="config-form card">
      <h2>Network Configuration for ESP32</h2>
      <p>(This will POST to http://{{ esp_config.get('localIP', ESP32_IP) }}:{{ esp_config.get('serverPort', 80) }}/config)</p>
      <form method="post" action="/">
        <div class="data-grid">
            <div>Local IP: <input type="text" name="localIP" value="{{ esp_config.get('localIP', '') }}"></div>
            <div>Gateway: <input type="text" name="gateway" value="{{ esp_config.get('gateway', '') }}"></div>
            <div>Subnet: <input type="text" name="subnet" value="{{ esp_config.get('subnet', '') }}"></div>
            <div>Server IP: <input type="text" name="serverIP" value="{{ esp_config.get('serverIP', '') }}"></div>
            <div>Server Port: <input type="text" name="serverPort" value="{{ esp_config.get('serverPort', '') }}"></div>
            <div>Modbus Interval: <input type="text" name="modbusInterval" value="{{ esp_config.get('modbusInterval', '') }}"></div>
            <div>Network Interval: <input type="text" name="networkInterval" value="{{ esp_config.get('networkInterval', '') }}"></div>
        </div>
        <br><input type="submit" value="Save Configuration to ESP32">
      </form>
    </div>
  </div>
</body>
</html>
'''

if __name__ == '__main__':
    # Use 0.0.0.0 to be accessible from other devices on the network
    app.run(host='0.0.0.0', port=5000, debug=True)