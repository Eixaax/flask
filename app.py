import eventlet
eventlet.monkey_patch()
from flask import Flask, request
from flask_socketio import SocketIO
from pymongo import MongoClient
from bson import ObjectId
import base64
from datetime import datetime

# Create Flask app and SocketIO instance
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

client = MongoClient("mongodb+srv://isa:admin@cluster0.v0xnx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client['test']
collection = db['Device']
user_devices = db['UserDevices']
audios = db['audiorecordings']

connected_devices = {}

@socketio.on('connect')
def handle_connect():
    print("A device connected.")
    print("Connected devices:", connected_devices)

@socketio.on('register_device')
def register_device(data):
    device_name = data.get('deviceName')
    
    if device_name:
        # Add device to connected_devices dictionary with session id (sid) as key
        connected_devices[request.sid] = device_name
        
        # Check if the device already exists in the collection
        device = collection.find_one({"device_name": device_name})
        if not device:
            # Device doesn't exist, insert a new entry
            collection.insert_one({
                "device_name": device_name,
                "status": "online",
            })
            print(f"New device {device_name} added to the collection with status 'online'.")
        else:
            # Device exists, update its status to 'online'
            collection.update_one(
                {"device_name": device_name},
                {"$set": {"status": "online"}}
            )
            print(f"Device {device_name} status updated to 'online'.")

        print(f"Device {device_name} registered.")
        print("Connected devices:", connected_devices)

@socketio.on('device_status_update')
def handle_device_status_update(data):
    user_id = data.get('user_id')
    message = data.get('message')

    print(message)

    print(f"Received status update for user_id {user_id}: {message}")
    socketio.emit('status_notification', {'user_id': user_id, 'message': message})


@socketio.on('disconnect')
def handle_disconnect():
    device_name = connected_devices.pop(request.sid, None)
    
    if device_name:
        print(f"Device {device_name} disconnected.")
        
        collection.update_one(
            {"device_name": device_name},
            {"$set": {"status": "offline"}}
        )
        print(f"Device {device_name} status set to 'offline'.")

    else:
        print("Device disconnected unexpectedly.")

    # Print the updated list of connected devices
    print("Connected devices:", connected_devices)

@socketio.on('check_and_connect_device')
def handle_device_check_and_connect(data):
    device_name = data.get('deviceName')
    user_id = data.get('uid')

    print(f"Received device name: {device_name}")
    print(f"Received User: {user_id}")

    # Search for the device in the collection
    device = collection.find_one({"device_name": device_name})
    if device:
        device_id = str(device.get('_id'))
        current_connection_status = device.get('connection')

        if current_connection_status == "connected":
            # Emit a response indicating the device is already paired
            socketio.emit('response', {
                'success': False,
                'message': 'Device is already paired with another device',
                'status': 'online',
                'connection': 'connected',
                'deviceId': device_id
            })
            print(f"Device {device_name} is already paired with another device.")
            return

        # Update the device status to 'online' and connection to 'connected'
        collection.update_one(
            {"_id": ObjectId(device_id)},
            {"$set": {"status": "online", "connection": "connected"}}
        )
        print('Device updated and saved!')

        # Save the device ID in the UserDevices collection
        user_device = user_devices.find_one({"device_id": device_id})
        if not user_device:
            # If no entry exists, insert a new document
            user_devices.insert_one({
                "user_id": user_id,
                "deviceId": device_id
            })
            print(f"New user device entry created for user_id: {user_id}")
        else:
            print(f"User device entry already exists for user_id: {user_id}")

        # Emit a success response with the updated status and device ID
        socketio.emit('response', {
            'success': True,
            'message': 'Device Found',
            'status': 'online',
            'connection': 'connected',
            'deviceId': device_id
        })
    else:
        # Emit a failure response if the device is not found
        socketio.emit('response', {
            'success': False,
            'message': 'Device Not Found',
            'status': 'offline',
            'deviceId': None
        })


@socketio.on('fetch_user_devices')
def fetch_user_devices(data):
    user_id = data.get('uid')
    userdevices = user_devices.find({"user_id": user_id})
    devices = []

    for userdevice in userdevices:
        device_id = userdevice.get("deviceId")
        device = collection.find_one({"_id": ObjectId(device_id)})
        if device:
            devices.append({
                "deviceId": str(device["_id"]),  # Convert ObjectId to string
                "deviceName": device.get("device_name"),
                "status": device.get("status", "Unknown")
            })

    print(devices)  
    socketio.emit('user_devices_response', {"devices": devices})

@socketio.on('fetch_audio_recordings')
def handle_fetch_audio_recordings(data):
    user_id = data.get('uid')
    if not user_id:
        socketio.emit('audio_recordings_response', {
            'success': False,
            'error': 'Missing user ID'  
        })
        return
    
    user_audios = audios.find({"user_id": user_id}).limit(10)

    audio_details = []

    for audio in user_audios:
        audio_info = {
            'audio_id': str(audio['_id']),
            'predicted_class': audio['predicted_class'],
            'timestamp': str(audio['timestamp']),
            'audioUrl': audio['audio_data'],  # Add the audio URL here
        }
        audio_details.append(audio_info)

    # Emit the audio details to the front-end
    socketio.emit('audio_recordings_response', {
        'success': True,
        'recordings': audio_details
    })


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)


