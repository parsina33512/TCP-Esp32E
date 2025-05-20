from flask import Flask, request

app = Flask(__name__)

# Endpoint to receive data from ESP32
default_route = '/data'

@app.route(default_route, methods=['GET', 'POST'])
def receive_data():
    # Read either query params or JSON body
    if request.method == 'GET':
        data = request.args.to_dict()
    else:  # POST
        data = request.get_json(silent=True) or request.form.to_dict()

    print(f"Received from ESP32: {data}")
    return {'status': 'ok', 'received': data}, 200

if __name__ == '__main__':
    # Host 0.0.0.0 makes it listen on all interfaces
    app.run(host='0.0.0.0', port=5000)