import socket
import threading
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import json

app = Flask(__name__)

# Thread-safe data storage
received_data = []
data_lock = threading.Lock()

# Configuration
TCP_HOST = "0.0.0.0"
TCP_PORT = 5000
HTTP_PORT = 8000

def tcp_server():
    """Persistent TCP server to handle raw socket connections"""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((TCP_HOST, TCP_PORT))
    server_sock.listen(5)  # Increased backlog for multiple connections
    print(f"⚡ TCP Server listening on {TCP_HOST}:{TCP_PORT}")

    while True:
        try:
            conn, addr = server_sock.accept()
            print(f"🔌 New connection from {addr}")
            client_thread = threading.Thread(
                target=handle_client_connection,
                args=(conn, addr),
                daemon=True
            )
            client_thread.start()
        except Exception as e:
            print(f"TCP server error: {e}")

def handle_client_connection(conn, addr):
    """Handle individual client connections"""
    with conn:
        while True:
            try:
                data = conn.recv(4096)  # Increased buffer size
                if not data:
                    break

                # Try to parse as JSON if possible
                try:
                    text = data.decode('utf-8').strip()
                    payload = json.loads(text)
                    data_type = "json"
                except (json.JSONDecodeError, UnicodeDecodeError):
                    text = data.decode('latin-1').strip()  # Fallback for non-UTF-8
                    payload = text
                    data_type = "raw"

                timestamp = datetime.now().isoformat()
                
                with data_lock:
                    received_data.append({
                        "timestamp": timestamp,
                        "source": f"tcp:{addr[0]}:{addr[1]}",
                        "type": data_type,
                        "data": payload
                    })
                
                print(f"📥 Received from {addr}: {text[:100]}...")  # Truncate long messages
                
                # Send acknowledgment
                conn.sendall(b"ACK\n")
                
            except ConnectionResetError:
                print(f"⚠️ Connection reset by {addr}")
                break
            except Exception as e:
                print(f"Error handling client {addr}: {e}")
                break

@app.route('/')
def dashboard():
    """Web dashboard showing all received data"""
    html = """
    <html>
      <head>
        <title>Device Data Monitor</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; }
          h1 { color: #333; }
          .data-item { 
            margin: 10px 0; padding: 10px; 
            border: 1px solid #ddd; border-radius: 4px;
            font-family: monospace;
          }
          .json { color: #0066cc; }
          .raw { color: #cc3300; }
          .meta { font-size: 0.8em; color: #666; }
        </style>
      </head>
      <body>
        <h1>Device Communication Dashboard</h1>
        <p><strong>TCP Endpoint:</strong> {tcp_host}:{tcp_port}</p>
        <p><strong>HTTP Endpoint:</strong> {http_host}:{http_port}</p>
        <hr>
        <h2>Received Data (Total: {count})</h2>
        <div id="data-container">
          {% for item in data %}
          <div class="data-item {{ item.type }}">
            <div class="meta">
              [{item.timestamp}] {item.source} ({item.type})
            </div>
            <pre>{{ item.data|tojson|safe }}</pre>
          </div>
          {% endfor %}
        </div>
      </body>
    </html>
    """
    
    with data_lock:
        return render_template_string(
            html,
            data=reversed(received_data),  # Show newest first
            count=len(received_data),
            tcp_host=TCP_HOST,
            tcp_port=TCP_PORT,
            http_host=request.host.split(':')[0],
            http_port=HTTP_PORT
        )

@app.route('/api/data', methods=['GET'])
def get_data():
    """JSON API endpoint for received data"""
    with data_lock:
        return jsonify({
            "count": len(received_data),
            "data": received_data
        })

@app.route('/api/update', methods=['POST'])
def update():
    """HTTP endpoint that works alongside the TCP server"""
    try:
        # Get client info
        client_ip = request.remote_addr
        client_port = request.environ.get('REMOTE_PORT')
        
        # Store the data
        timestamp = datetime.now().isoformat()
        
        if request.content_type == 'application/json':
            payload = request.get_json()
            data_type = "json"
        else:
            payload = request.get_data(as_text=True)
            data_type = "raw"
        
        with data_lock:
            received_data.append({
                "timestamp": timestamp,
                "source": f"http:{client_ip}:{client_port}",
                "type": data_type,
                "data": payload
            })
        
        print(f"📥 Received HTTP from {client_ip}: {str(payload)[:100]}...")
        return jsonify({"status": "success", "received": True})
    
    except Exception as e:
        print(f"HTTP error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

def start_servers():
    """Start both TCP and HTTP servers"""
    # Start TCP server in background thread
    tcp_thread = threading.Thread(target=tcp_server, daemon=True)
    tcp_thread.start()
    print(f"🚀 TCP server thread started on port {TCP_PORT}")
    
    # Start HTTP server
    print(f"🌐 HTTP server starting on port {HTTP_PORT}")
    app.run(host='0.0.0.0', port=HTTP_PORT)

if __name__ == "__main__":
    start_servers()