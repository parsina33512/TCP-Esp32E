from flask import Flask, request, jsonify, render_template
from datetime import datetime
import json
import os
import threading
from werkzeug.serving import make_server

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Configuration
CONFIG_FILE = 'device_config.json'
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
class DeviceConfig:
    def __init__(self):
        self.lock = threading.Lock()
        self.config = {
            "localIP": "192.168.100.57",  # ESP32's new IP
            "gateway": "192.168.100.1",
            "subnet": "255.255.255.0",
            "serverIP": "192.168.100.65",  # Your PC's wired IP
            "serverPort": 5000,
            "modbusInterval": 500,
            "networkInterval": 2000
        }
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with self.lock:
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)

    def save_config(self, new_config):
        with self.lock:
            self.config.update(new_config)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)

device_config = DeviceConfig()

def log_data(data_type, data):
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{data_type}_{date_str}.jsonl"
    filepath = os.path.join(DATA_DIR, filename)
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "data": data
    }
    
    with open(filepath, 'a') as f:
        f.write(json.dumps(entry) + '\n')

@app.route('/')
def dashboard():
    return render_template('dashboard.html', config=device_config.config)

@app.route('/api/update', methods=['POST'])
def handle_update():
    try:
        data = request.get_json() if request.is_json else request.get_data(as_text=True)
        log_data('sensor', data)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/config', methods=['GET', 'POST'])
def handle_device_config():
    if request.method == 'GET':
        return jsonify(device_config.config)
    else:
        try:
            new_config = request.get_json()
            device_config.save_config(new_config)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/logs')
def get_logs():
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    data_type = request.args.get('type', 'sensor')
    filename = f"{data_type}_{date_str}.jsonl"
    filepath = os.path.join(DATA_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "Log not found"}), 404
    
    entries = []
    with open(filepath, 'r') as f:
        for line in f:
            entries.append(json.loads(line))
    
    return jsonify(entries)

class FlaskServer(threading.Thread):
    def __init__(self):
        super().__init__()
        self.server = make_server('0.0.0.0', 5000, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

if __name__ == '__main__':
    server = FlaskServer()
    server.start()
    print("Server started on http://0.0.0.0:5000")
    
    try:
        while True:
            cmd = input("Enter 'stop' to shutdown: ")
            if cmd.lower() == 'stop':
                server.shutdown()
                break
    except KeyboardInterrupt:
        server.shutdown()