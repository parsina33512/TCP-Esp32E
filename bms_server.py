from flask import Flask, request, render_template_string, jsonify, redirect, flash, url_for
from datetime import datetime
import json, os, requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ─── In‐memory store of all received Modbus packets ───────────────
received_data = []

# ─── Where your ESP32 lives on the LAN (for sending config back) ───
ESP32_IP   = "192.168.100.65"
ESP32_PORT = 80   # ESP32's AsyncWebServer is on port 80

# ─── 1) Endpoint for ESP32 to push data ────────────────────────────
@app.route('/update', methods=['POST'])
def update():
    """
    This route handles POSTs from the ESP32. It tries to parse JSON first,
    then falls back to form‐encoded 'data=<json>'.
    """
    data = request.get_json(silent=True)
    if data is None:
        raw = request.form.get('data', '')
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                return "Bad JSON", 400
        else:
            return "No data provided", 400

    # Stamp it and store in our global list
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data":      data
    }
    received_data.append(entry)

    # Print to console for debugging
    print(f"\nReceived data at {entry['timestamp']}:")
    print(json.dumps(data, indent=2))

    # Return ACK
    return "ACK", 200, {"Connection": "close"}


# ─── 2) Browser polls this for the full array of received packets ───
@app.route('/data', methods=['GET'])
def get_data():
    """
    Returns the entire list of received_data as JSON.
    """
    return jsonify(received_data)


# ─── 3) Dashboard & Config Page ────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Renders a dashboard that:
      - shows all the BMS packets (latest first)
      - allows sending new IP/DNS/subnet/serverIP back to the ESP32
    """
    # If the user just POSTed new network config, forward it to the ESP
    if request.method == 'POST':
        # Gather new configuration from the form
        new_config = {
            'localIP':  request.form.get('localIP', '').strip(),
            'gateway':  request.form.get('gateway', '').strip(),
            'subnet':   request.form.get('subnet', '').strip(),
            'serverIP': request.form.get('serverIP', '').strip()
        }

        # Attempt to push it to ESP32 at http://192.168.100.65/config
        try:
            resp = requests.post(
                f"http://{ESP32_IP}:{ESP32_PORT}/config",
                json=new_config,
                timeout=5
            )
            if resp.ok:
                flash("✅ Configuration sent to ESP32 successfully!")
            else:
                flash(f"⚠️ ESP32 responded: {resp.status_code} {resp.text}")
        except Exception as e:
            flash(f"❌ Error sending config to ESP32: {e}")

        return redirect(url_for('index'))

    # For GET: first fetch the ESP32's current network config (so we can pre-fill the form)
    esp_config = {
        'localIP': '',
        'gateway': '',
        'subnet':  '',
        'serverIP':''
    }
    try:
        # Attempt to GET /config from ESP32
        cfg_resp = requests.get(f"http://{ESP32_IP}:{ESP32_PORT}/config", timeout=3)
        if cfg_resp.ok:
            parsed = cfg_resp.json()
            # Copy fields if they exist
            esp_config['localIP']  = parsed.get('localIP', '')
            esp_config['gateway']  = parsed.get('gateway', '')
            esp_config['subnet']   = parsed.get('subnet', '')
            esp_config['serverIP'] = parsed.get('serverIP', '')
    except Exception as e:
        # If it fails (ESP not reachable?), leave esp_config as empty strings
        print(f"⚠️ Could not fetch ESP32 /config: {e}")

    # Render the dashboard HTML, passing in esp_config for pre-filling
    return render_template_string('''
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
            // Reverse order so latest is on top
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
                </div>`;
              container.appendChild(div);
            });
          }
          // Poll every second
          setInterval(fetchData, 1000);
          window.onload = fetchData;
        </script>
      </head>
      <body>
        <h1>BMS Monitoring System</h1>

        {% with messages = get_flashed_messages() %}
          {% if messages %}
            <div class="flash-messages">
              {% for m in messages %}
                <div class="flash">{{ m }}</div>
              {% endfor %}
            </div>
          {% endif %}
        {% endwith %}

        <!-- Container where the JavaScript will insert all BMS cards -->
        <div id="data-container"></div>

        <hr>
        <h2>Network Configuration for ESP32</h2>
        <p>
          (This will POST to <code>http://{{ esp_url }}/config</code> on the ESP32.)
        </p>
        <form method="post" action="/">
          Local IP:   <input type="text" name="localIP"  value="{{ esp_config.localIP }}"><br>
          Gateway:    <input type="text" name="gateway"  value="{{ esp_config.gateway }}"><br>
          Subnet:     <input type="text" name="subnet"   value="{{ esp_config.subnet }}"><br>
          Server IP:  <input type="text" name="serverIP" value="{{ esp_config.serverIP }}"><br>
          <br>
          <input type="submit" value="Save Configuration">
        </form>
      </body>
    </html>
    ''',
    esp_config=esp_config,
    esp_url=f"{ESP32_IP}:{ESP32_PORT}"
    )


if __name__ == '__main__':
    # Listen on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
