from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
from pymongo import MongoClient
from datetime import time
from openai import OpenAI


app = Flask(__name__)
CORS(app)

# MongoDB connection
client = MongoClient('mongodb+srv://sandesh:sandesh123@sandesh.kjyp0wb.mongodb.net/?retryWrites=true&w=majority&appName=sandesh')
db = client['tasks']
collection = db['users']

@app.route('/upload', methods=['POST'])
def upload_excel():
    if 'excel' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['excel']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        df = pd.read_excel(file)
        df.columns = [col.strip().lower() for col in df.columns]  # Lowercase for consistency

        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime('%H:%M')
            else:
                df[col] = df[col].apply(lambda x: x.strftime('%H:%M') if isinstance(x, time) else x)

        if 'student_id' in df.columns:
            df['student_id'] = df['student_id'].apply(lambda x: int(str(x).strip()) if str(x).isdigit() else str(x).strip())

        data = df.to_dict(orient='records')
        collection.delete_many({})
        collection.insert_many(data)

        return jsonify({"message": "Data inserted successfully", "rows": len(data)}), 200

    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@app.route('/users', methods=['GET'])
def get_users():
    users = list(collection.find({}, {'_id': 0}))
    return jsonify(users)

@app.route('/get_student_name')
def get_student_name():
    student_id = request.args.get('student_id')

    if not student_id:
        return jsonify({"error": "Missing student ID"}), 400

    try:
        student_id = int(student_id)
        students = list(db.users.find({'student_id': student_id}, {'_id': 0}))
        if students:
            return jsonify(students)
        else:
            return jsonify({"error": "Student not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        password = data.get('password')

        if not student_id or not password:
            return jsonify({"error": "Missing Student ID or Password"}), 400

        query = {
            "$or": [
                {"student_id": student_id, "password": password},
                {"student_id": int(student_id) if str(student_id).isdigit() else -1, "password": password}
            ]
        }

        user = collection.find_one(query, {'_id': 0, 'student_id': 1})

        if user:
            return jsonify({
                "message": "Login successful",
                "student_id": user["student_id"]
            }), 200
        else:
            return jsonify({"error": "Invalid Student ID or Password"}), 401

    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Dummy in-memory notifications (replace with MongoDB collection in production)
notifications_collection = db['notifications']

@app.route('/notifications', methods=['GET'])
def get_notifications():
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({"error": "Missing student_id"}), 400

    try:
        student_id = int(student_id)
        notifications = list(notifications_collection.find(
            {"student_id": student_id},
            {"_id": 0}
        ))

        # Optional: sort by timestamp descending
        notifications.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        return jsonify(notifications), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
openai_client = OpenAI(api_key="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")

@app.route('/AIchat', methods=['POST'])
def ai_chat():
    try:
        data = request.get_json()
        message = data.get("message", "").strip()
        student_id = data.get("student_id", "").strip()

        if not message or not student_id:
            return jsonify({"error": "Missing message or student_id"}), 400

        from datetime import datetime
        today_name = datetime.now().strftime('%A')

        # Decide filter mode
        message_lower = message.lower()
        if "today" in message_lower or "class today" in message_lower:
            # Filter only today's classes
            student_data = list(collection.find({
                "student_id": int(student_id),
                "weekday": today_name
            }, {"_id": 0}))
            context_intro = f"Today is {today_name}. The student's schedule for today is:"
        else:
            # Fetch all classes
            student_data = list(collection.find({
                "student_id": int(student_id)
            }, {"_id": 0}))
            context_intro = "This is the student's full course schedule:"

        # Build context
        if not student_data:
            context = f"No course data found for student ID {student_id}."
        else:
            context_lines = [
                f"{item['course']} on {item['weekday']} from {item['start_time']} to {item['end_time']} in {item['room_address']}"
                for item in student_data
            ]
            context = f"{context_intro}\n" + "\n".join(context_lines)

        # Send to OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": message}
            ]
        )

        reply = response.choices[0].message.content.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        print("OpenAI API call failed:", str(e))
        return jsonify({"error": str(e)}), 500




# Message storage collection
messages_collection = db['messages']

@app.route('/get_all_students', methods=['GET'])
def get_all_students():
    try:
        students = list(collection.find({}, {'_id': 0, 'student_id': 1, 'name': 1}))
        return jsonify(students), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        sender_id = data.get("sender_id")
        receiver_id = data.get("receiver_id")
        message = data.get("message")
        timestamp = data.get("timestamp")

        if not sender_id or not receiver_id or not message:
            return jsonify({"error": "Missing fields"}), 400

        messages_collection.insert_one({
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "message": message,
            "timestamp": timestamp
        })

        return jsonify({"status": "Message sent"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_messages', methods=['GET'])
def get_messages():
    sender_id = request.args.get('sender_id')
    receiver_id = request.args.get('receiver_id')

    if not sender_id or not receiver_id:
        return jsonify({"error": "Missing sender_id or receiver_id"}), 400

    try:
        messages = list(messages_collection.find({
            "$or": [
                {"sender_id": sender_id, "receiver_id": receiver_id},
                {"sender_id": receiver_id, "receiver_id": sender_id}
            ]
        }, {"_id": 0}))

        # Optional: sort by timestamp
        messages.sort(key=lambda msg: msg.get("timestamp", ""))

        return jsonify(messages), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/' + token, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    url = os.getenv('VERCEL_PROJECT_PRODUCTION_URL')
    bot.set_webhook(url= f"{url}/{token}", max_connections=50)
    return "!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
