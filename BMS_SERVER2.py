from flask import Flask, request, render_template_string, jsonify, redirect, flash, url_for
from datetime import datetime
import json, os, requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ─── in-memory store of ALL packets you ever got ────────────────
received_data = []             # <--- UNCHANGED

ESP32_IP   = "169.254.185.250"  # send config / FW here
ESP32_PORT = 80

# ────────────────────────────────────────────────────────────────
#  1) ESP32 pushes BMS data  (now may contain "slaves":[…])
# ────────────────────────────────────────────────────────────────
@app.route('/update', methods=['POST'])
def update():
    data = request.get_json(silent=True)
    if data is None:           # legacy x-www-form-urlencoded body
        raw = request.form.get('data', '')
        if not raw:
            return "No data provided", 400
        try:
            data = json.loads(raw)
        except:
            return "Bad JSON", 400

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data":      data
    }
    received_data.append(entry)

    print(f"\n[ BMS DATA RECEIVED at {entry['timestamp']} ]")
    print(json.dumps(data, indent=2))
    return "ACK", 200, {"Connection":"close"}

# ─── 1.5) ESP32 pushes its own network config (unchanged) ───────
@app.route('/config', methods=['POST'])
def receive_config():
    data = request.get_json(silent=True)
    if data is None:
        raw = request.form.get('data','')
        if not raw:
            return "No data provided", 400
        try:
            data = json.loads(raw)
        except:
            return "Bad JSON", 400
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[ CONFIG RECEIVED at {ts} ]")
    print(json.dumps(data, indent=2))
    return "CONFIG-ACK", 200, {"Connection":"close"}

# ─── 2) historical JSON dump  (unchanged) ───────────────────────
@app.route('/data')
def get_data():
    return jsonify(received_data)

# ─── 3) dashboard & config page  (UNCHANGED back-end) ───────────
@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST':
        new_config = {k:request.form.get(k,'').strip() for k in
          ('localIP','gateway','subnet','serverIP','serverPort',
           'modbusInterval','networkInterval')}
        try:
            r=requests.post(f"http://{ESP32_IP}:{ESP32_PORT}/config",
                             json=new_config, timeout=5)
            flash("✅ Configuration sent" if r.ok
                  else f"⚠️ ESP32: {r.status_code} {r.text}")
        except Exception as e:
            flash(f"❌ {e}")
        return redirect(url_for('index'))

    esp_config = dict.fromkeys(('localIP','gateway','subnet','serverIP',
                                'serverPort','modbusInterval',
                                'networkInterval'),'')
    try:
        cfg=requests.get(f"http://{ESP32_IP}:{ESP32_PORT}/config",timeout=3)
        if cfg.ok:
            esp_config.update(cfg.json())
    except Exception as e:
        print(f"⚠️ Could not fetch ESP32 /config: {e}")

    return render_template_string(DASHBOARD_HTML,
        received_data=received_data,
        esp_config=esp_config,
        esp_url=f"{ESP32_IP}:{ESP32_PORT}"
    )

# ─── 4) firmware upload (unchanged) ─────────────────────────────
@app.route('/fw', methods=['GET'])
def fw_form():
    return render_template_string('''
      <!DOCTYPE html><html><body>
      <h1>Upload New Firmware (.bin)</h1>
      <form method=post enctype=multipart/form-data>
        <input type=file name=fw accept=".bin"><button>Flash ESP32</button>
      </form></body></html>''')

@app.route('/fw', methods=['POST'])
def fw_upload():
    file=request.files.get('fw')
    if not file:
        flash("❌ No firmware file"); return redirect(url_for('fw_form'))
    temp=os.path.join('/tmp',file.filename); file.save(temp)
    try:
        with open(temp,'rb') as fd:
            r=requests.post(f"http://{ESP32_IP}:{ESP32_PORT}/update",
                            data=fd, headers={"Content-Type":"application/octet-stream"},
                            timeout=60)
        flash(f"ESP32: {r.status_code} {r.text}")
    except Exception as e:
        flash(f"❌ {e}")
    finally:
        os.remove(temp)
    return redirect(url_for('fw_form'))


# ─── HTML template (only JS changed) ────────────────────────────
DASHBOARD_HTML = '''
<!DOCTYPE html><html><head><meta charset="utf-8">
<title>BMS Monitoring Dashboard</title>
<style>
 body{font-family:Arial;padding:20px}
 .card{border:1px solid #ddd;padding:15px;margin:10px;border-radius:5px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
 .timestamp{color:#666;font-size:.9em;margin-bottom:5px}
 .flash{background:#eef;padding:10px;border:1px solid #99c;margin-bottom:5px}
 form{margin-top:30px}form input{width:250px;margin-bottom:10px}
</style>
<script>
async function fetchData(){
  const resp = await fetch('/data'); const arr = await resp.json();
  const box  = document.getElementById('data-container'); box.innerHTML='';
  arr.slice().reverse().forEach(entry=>{
    const ts = entry.timestamp;
    const d  = entry.data;

    /* ── CASE A: new multi-slave payload ───────────────────── */
    if (d.slaves){
      d.slaves.forEach(s=>{
        const div=document.createElement('div'); div.className='card';
        div.innerHTML=`<div class="timestamp">${ts}</div>
          <h3>Slave ${s.id}</h3>
          <div class="grid">
            <div>Voltage:   ${s.V} V</div>
            <div>Current:   ${s.I} A</div>
            <div>Rem Cap:   ${s.RemAh} Ah</div>
            <div>Temp:      ${s.Temp} °C</div>
            <div>Warn:      ${s.Warn}</div>
            <div>Prot:      ${s.Prot}</div>
          </div>`;
        box.appendChild(div);
      });
    }
    /* ── CASE B: legacy single-slave packet ─────────────────── */
    else{
      const div=document.createElement('div'); div.className='card';
      div.innerHTML=`<div class="timestamp">${ts}</div>
        <h3>BMS Status</h3>
        <div class="grid">
          <div>Pack Voltage:       ${d.pack_voltage} V</div>
          <div>Current:            ${d.current} A</div>
          <div>Remaining Capacity: ${d.capacity_remaining} Ah</div>
          <div>SOC:                ${d.soc}%</div>
          <div>SOH:                ${d.soh}%</div>
          <div>Avg Cell Temp:      ${d.avg_cell_temp} °C</div>
          <div>Env Temp:           ${d.env_temp} °C</div>
          <div>Cycles:             ${d.cycles}</div>
          <div>Max Cell Voltage:   ${d.max_cell_voltage} V</div>
          <div>Min Cell Voltage:   ${d.min_cell_voltage} V</div>
          <div>Modbus Error:       ${d.modbusError ? "Yes":"No"}</div>
        </div>`;
      box.appendChild(div);
    }
  });
}
setInterval(fetchData,1000); window.onload=fetchData;
</script></head><body>

<h1>BMS Monitoring System</h1>

{% with messages = get_flashed_messages() %}
  {% if messages %}
    {% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}
  {% endif %}
{% endwith %}

<div id="data-container"></div><hr>

<h2>Network Configuration for ESP32</h2>
<p>(POSTs to <code>http://{{ esp_url }}/config</code>)</p>
<form method=post>
 {% for k,v in esp_config.items() %}
   {{k}}: <input name="{{k}}" value="{{v}}"><br>
 {% endfor %}
 <br><input type=submit value="Save Configuration">
</form>

</body></html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
