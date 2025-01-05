import eventlet
eventlet.monkey_patch()  # Ensure this is the first line of code

from flask import Flask
from flask_socketio import SocketIO, emit
from pymongo import MongoClient

app = Flask(__name__)

socketio = SocketIO(app, cors_allowed_origins="*")

client = MongoClient("mongodb+srv://isa:admin@cluster0.v0xnx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # Replace with your MongoDB URI
db = client['test']
collection = db['Device']

@app.route('/')
def index():
    return "WebSocket Server is Running"

@socketio.on('data')
def handle_device_data(data):
    device_name = data.get('deviceName')
    device = collection.find_one({"deviceName": device_name})

    if device:
        emit('response', {'success': True, 'message': 'Device Connected!'})
        print('connected!')
    else:
        emit('response', {'success': False, 'message': 'Device Not Found'})
        print('not found!')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
