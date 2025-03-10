import eventlet
eventlet.monkey_patch()
from flask import Flask, request, jsonify
import bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from flask_socketio import SocketIO
from pymongo import MongoClient
from bson import ObjectId
import base64
import random
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta

# Create Flask app and SocketIO instance
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)
app.config['JWT_SECRET_KEY'] = "a9f8b27c9d3e4f5b6c7d8e9f1029384756c7d8e9f1029384756a7b8c9d0e1f2"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 900  # 15 minutes
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 7 * 24 * 60 * 60  # 7 days
jwt = JWTManager(app)


client = MongoClient("mongodb+srv://isa:admin@cluster0.v0xnx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client['test']
collection = db['Device']
user_devices = db['UserDevices']
audios = db['audiorecordings']
users_collection = db["UserInfo"]
otptable = db['otp']

connected_devices = {}

@socketio.on('send_otp')
def sendOTP(data):
    try:
        email = data.get('email')
        if not email:
            print("Email not provided")
            socketio.emit('response', {'success': False, 'message': 'Email is required'})
            return

        # Generate a 6-digit OTP
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Save OTP in MongoDB with expiration time (5 mins)
        expiration_time = datetime.utcnow() + timedelta(minutes=5)
        otptable.update_one(
            {'email': email}, 
            {'$set': {'otp': otp, 'expires_at': expiration_time,'status':'pending'}}, 
            upsert=True
        )

        # Email setup
        msg = EmailMessage()
        msg['Subject'] = "OTP VERIFICATION"
        msg['From'] = "isaacradjaluddin@gmail.com"
        msg['To'] = email
        msg.set_content(f"YOUR OTP VERIFICATION CODE IS: {otp}")

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('isaacradjaluddin@gmail.com', 'oabm ksdh rpud dbri')
        server.send_message(msg)
        server.quit()

        print(f"Email sent to {email} with OTP: {otp}")
        socketio.emit('response', {'success': True, 'message': f'OTP sent successfully to {email}'})

    except Exception as e:
        print(f"Error sending email: {e}")
        socketio.emit('response', {'success': False, 'message': 'OTP failed to send'})

@socketio.on('verify_otp')
def verify(data):
    try:
        email = data.get('email')
        enteredOTP = data.get('enteredOTP')

        if not email or not enteredOTP:
            socketio.emit('response', {'success': False, 'message': 'Email and OTP are required'})
            return

        record = otptable.find_one({'email': email})

        if not record:
            socketio.emit('response', {'success': False, 'message': 'Invalid email or OTP'})
            print("Record not found")
            return

        stored_otp = record.get('otp')
        expires_at = record.get('expires_at')

        if stored_otp != enteredOTP:
            socketio.emit('response', {'success': False, 'message': 'Incorrect OTP'})
            print("INCORRECT OTP")
            return

        if expires_at and datetime.utcnow() > expires_at:
            socketio.emit('response', {'success': False, 'message': 'OTP has expired'})
            print("OTP HAS EXPIRED")
            return

        # Update OTP status to "verified"
        otptable.update_one(
            {'email': email},
            {'$set': {'status': 'verified'}}
        )

        socketio.emit('response', {'success': True, 'message': 'OTP verified successfully'})
        print("VERIFIED OTP")

    except Exception as e:
        print(f"Error verifying OTP: {e}")
        socketio.emit('response', {'success': False, 'message': 'An error occurred during OTP verification'})


@socketio.on('change_password')
def change_pass(data):
    try:
        email = data.get('email')
        newPassword = data.get('newPassword')
        print(email)
        print(newPassword)

        if not email or not newPassword:
            socketio.emit('response', {'success': False, 'message': 'Email and new password are required'})
            return

        record = otptable.find_one({'email': email})

        if not record:
            socketio.emit('response', {'success': False, 'message': 'Invalid email'})
            print("Record not found")
            return

        if record.get('status') != 'verified':
            socketio.emit('response', {'success': False, 'message': 'OTP verification required'})
            print("OTP NOT VERIFIED")
            return

        hashed_password = bcrypt.hashpw(newPassword.encode("utf-8"), bcrypt.gensalt())


        result = users_collection.update_one(
            {'email': email},
            {'$set': {'password': hashed_password}}
        )

        if result.modified_count > 0:
            socketio.emit('response', {'success': True, 'message': 'Password changed successfully'})
            print("PASSWORD UPDATED")
        else:
            socketio.emit('response', {'success': False, 'message': 'Failed to update password'})
            print("PASSWORD UPDATE FAILED")

    except Exception as e:
        print(f"Error changing password: {e}")
        socketio.emit('response', {'success': False, 'message': 'An error occurred while changing password'})



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


@socketio.on('disconnect_device')
def disconnect_device(data):
    device_id = data.get('deviceId')

    if not device_id:
        print("No device ID provided for disconnect.")
        return socketio.emit('device_disconnected_response', {
            'success': False,
            'message': 'Device ID is required'
        })

    # Find the device by its ID in the database
    device = collection.find_one({"_id": ObjectId(device_id)})

    if not device:
        print(f"Device with ID {device_id} not found.")
        return socketio.emit('device_disconnected_response', {
            'success': False,
            'message': 'Device not found'
        })

    user_devices.delete_one({"deviceId": device_id})
    print(f"Device {device_id} removed from UserDevices collection.")

    collection.update_one(
        {"_id": ObjectId(device_id)},
        {"$set": {"connection": "disconnected"}}
    )

    # Remove from connected devices if present
    device_name = device.get("device_name")
    sid_to_remove = None
    for sid, name in connected_devices.items():
        if name == device_name:
            sid_to_remove = sid
            break

    if sid_to_remove:
        connected_devices.pop(sid_to_remove, None)

    print(f"Device {device_name} disconnected successfully.")

    # Emit response to client
    socketio.emit('device_disconnected_response', {
        'success': True,
        'message': 'Device disconnected successfully',
        'deviceId': device_id
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
    page = data.get('page', 1)  
    selected_date = data.get('date')  # Get the selected date
    print(selected_date)
    if not user_id:
        socketio.emit('audio_recordings_response', {
            'success': False,
            'error': 'Missing user ID'  
        })
        return

    # Limit the number of recordings per page and calculate the offset
    limit = 10
    skip = (page - 1) * limit  

    # Ensure selected_date is provided and in valid format
    if selected_date:
        try:
            # Convert string date to datetime object for filtering
            date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
            start_of_day = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
            end_of_day = datetime(date_obj.year, date_obj.month, date_obj.day, 23, 59, 59)

            # Fetch user audio recordings for the selected date
            query = {
                "user_id": user_id,
                "timestamp": {"$gte": start_of_day, "$lte": end_of_day}
            }
        except ValueError:
            socketio.emit('audio_recordings_response', {
                'success': False,
                'error': 'Invalid date format'
            })
            return
    else:
        query = {"user_id": user_id}

    # Query the database
    user_audios = audios.find(query).sort("timestamp", -1).skip(skip).limit(limit)

    audio_details = []
    for audio in user_audios:
        audio_info = {
            'audio_id': str(audio['_id']),
            'predicted_class': audio['predicted_class'],
            'timestamp': str(audio['timestamp']),
            'audioUrl': audio['audio_url'],
            'mark': audio.get('mark', 'unmarked'),  # Provide default if mark is missing
        }
        audio_details.append(audio_info)

    # Emit the audio details to the front-end
    socketio.emit('audio_recordings_response', {
        'success': True,
        'recordings': audio_details,
        'page': page  
    })


@app.route("/login-user", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if "users_collection" not in globals():
        print("users_collection is not defined in global scope!")
        return jsonify({"status": "error", "data": "Server error"}), 500

    # Debugging statement
    print(f"Checking login for {email}")

    # Find the user in the database
    user = users_collection.find_one({"email": email})

    if not user:
        print("User not found")
        return jsonify({"status": "error", "data": "User not found"}), 404

    # Get the stored password from the database
    stored_password = user.get("password", "")

    if isinstance(stored_password, str):
        stored_password = stored_password.encode("utf-8")

    # Compare the passwords
    if not bcrypt.checkpw(password.encode("utf-8"), stored_password):
        print("Invalid password")
        return jsonify({"status": "error", "data": "Invalid password"}), 401

    # Create JWT token
    access_token = create_access_token(identity=str(user["_id"]))
    refresh_token = create_refresh_token(identity=str(user["_id"]))

    return jsonify({"status": "success", "access_token": access_token, "refresh_token": refresh_token}), 200

@app.route("/refresh-token", methods=["POST"])
@jwt_required(refresh=True)  # Requires a valid refresh token
def refresh_token():
    user_id = get_jwt_identity()

    # Generate a new access token
    new_access_token = create_access_token(identity=user_id)

    # Generate a new refresh token to reset its expiry
    new_refresh_token = create_refresh_token(identity=user_id)

    return jsonify({"access_token": new_access_token, "refresh_token": new_refresh_token}), 200

# Get User Data (Protected)
@app.route("/userdata", methods=["POST"])
@jwt_required()
def get_userdata():
    try:
        user_id = get_jwt_identity()

        if not user_id:
            print("No user ID found in token.")
            return jsonify({"status": "error", "data": "Invalid token"}), 401

        user = users_collection.find_one({"_id": ObjectId(user_id)})

        if not user:
            print("User not found")
            return jsonify({"status": "error", "data": "User not found"}), 404

        user_data = {
            "id": str(user["_id"]), 
            "name": user.get("name"),
            "email": user.get("email"),
            "profile_picture": user.get("profile_picture", "")  
        }

        return jsonify({"status": "ok", "data": user_data}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "data": "An error occurred"}), 500

@app.route("/register", methods=["POST"])
def register():
    """Register a new user"""
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    # Check if user already exists
    if users_collection.find_one({"email": email}):
        return jsonify({"status": "error", "data": "User Already Exists!"}), 400

    # Hash the password before storing
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    # Insert user into database
    user_id = users_collection.insert_one({
        "name": name,
        "email": email,
        "password": hashed_password
    }).inserted_id

    return jsonify({"status": "ok", "data": "User Created", "user_id": str(user_id)}), 201


@app.route('/update-profile', methods=['POST'])
def update_profile():
    data = request.json
    user_email = data.get("email")  # Ensure email is sent in request
    new_name = data.get("name")
    new_profile_picture = data.get("profile_picture")

    if not user_email:
        return jsonify({"status": "error", "message": "Email is required"}), 400

    users_collection.update_one(
        {"email": user_email}, 
        {"$set": {"name": new_name, "profile_picture": new_profile_picture}}
    )

    return jsonify({"status": "ok", "message": "Profile updated successfully!"})


@socketio.on("update_audio_status")
def update_audio_status(data):
    try:
        audio_id = data.get("audioId")
        mark = data.get("mark")

        if audio_id is None or mark is None:  # Allow mark to be 0
            socketio.emit("update_audio_response", {"success": False, "error": "Invalid data"})
            return

        try:
            audio_object_id = ObjectId(audio_id)
        except Exception:
            socketio.emit("update_audio_response", {"success": False, "error": "Invalid audio ID format"})
            return

        # Update the database record
        result = audios.update_one(
            {"_id": audio_object_id},
            {"$set": {"mark": mark}}
        )

        if result.matched_count == 0:
            socketio.emit("update_audio_response", {"success": False, "error": "Audio not found"})
        else:
            socketio.emit("update_audio_response", {"success": True, "audioId": audio_id, "mark": mark})

    except Exception as e:
        print(f"Error updating audio status: {e}")  # Log error for debugging
        socketio.emit("update_audio_response", {"success": False, "error": "Server error"})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
