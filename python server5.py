from flask import Flask, request, render_template_string, jsonify, redirect, flash, url_for
from datetime import datetime
import json, os, requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In‐memory store of all received packets
received_data = []

# Where your ESP32 lives on the LAN (for sending config back)
ESP32_IP = "192.168.100.65"


# ─── 1) Endpoint for ESP32 to push data ───────────────────────────────────────
@app.route('/update', methods=['POST'])
def update():
    """
    This route handles POSTs from the ESP32. It tries JSON first,
    then falls back to form‐encoded 'data=<json>'.
    """
    # 1) Try parsing a raw JSON body
    data = request.get_json(silent=True)
    if data is None:
        # 2) Otherwise, look for form‐encoded field "data"
        raw = request.form.get('data', '')
        if raw:
            try:
                data = json.loads(raw)
            except Exception as e:
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
    print(f"Received data at {entry['timestamp']}:")
    print(json.dumps(data, indent=2))

    # Return ACK and close the connection immediately
    return "ACK", 200, {"Connection": "close"}


# ─── 2) Browser polls this for the full array ─────────────────────────────────
@app.route('/data', methods=['GET'])
def get_data():
    """
    Returns the entire list of received_data as JSON.
    """
    return jsonify(received_data)


# ─── 3) Dashboard & Config Page ──────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Renders a dashboard that:
      - shows all the BMS packets (latest first)
      - allows posting new IP/DNS/subnet/serverIP back to the ESP32
    """
    if request.method == 'POST':
        # Gather new configuration from the form and send it to the ESP32
        try:
            new_config = {
                'localIP':  request.form['localIP'],
                'gateway':  request.form['gateway'],
                'subnet':   request.form['subnet'],
                'serverIP': request.form['serverIP']
            }
            resp = requests.post(
                f"http://{ESP32_IP}/config",
                json=new_config,
                timeout=5
            )
            flash("Configuration updated!" if resp.ok else "Update failed")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for('index'))

    # Render the dashboard HTML
    return render_template_string('''
    <!DOCTYPE html>
    <html>
      <head>
        <title>BMS Monitor</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 20px; }
          .card { border: 1px solid #ddd; padding: 15px; margin: 10px; border-radius: 5px; }
          .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px,1fr)); gap: 20px; }
          .timestamp { color: #666; font-size: 0.9em; }
          .flash-messages { margin-bottom: 20px; }
          .flash { background: #eef; padding: 10px; border: 1px solid #99c; margin-bottom: 5px; }
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
                  <div>Pack Voltage:         ${entry.data.pack_voltage} V</div>
                  <div>Current:              ${entry.data.current} A</div>
                  <div>Remaining Capacity:   ${entry.data.capacity_remaining} Ah</div>
                  <div>SOC:                  ${entry.data.soc}%</div>
                  <div>SOH:                  ${entry.data.soh}%</div>
                  <div>Avg Cell Temp:        ${entry.data.avg_cell_temp} °C</div>
                  <div>Env Temp:             ${entry.data.env_temp} °C</div>
                  <div>Cycles:               ${entry.data.cycles}</div>
                  <div>Max Cell Voltage:     ${entry.data.max_cell_voltage} V</div>
                  <div>Min Cell Voltage:     ${entry.data.min_cell_voltage} V</div>
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

        <div id="data-container"></div>

        <hr>
        <h2>Network Configuration</h2>
        <form method="post" action="/">
          Local IP:   <input type="text" name="localIP"  value="{{ request.form.localIP or '' }}"><br>
          Gateway:    <input type="text" name="gateway"  value="{{ request.form.gateway or '' }}"><br>
          Subnet:     <input type="text" name="subnet"   value="{{ request.form.subnet or '' }}"><br>
          Server IP:  <input type="text" name="serverIP" value="{{ request.form.serverIP or '' }}"><br>
          <input type="submit" value="Save Configuration">
        </form>
      </body>
    </html>
    ''')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
