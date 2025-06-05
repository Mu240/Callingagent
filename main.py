from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import openai
import requests
import os
import uuid
import hashlib
import logging
from datetime import datetime
import mysql.connector
from mysql.connector import Error

# Load environment variables
load_dotenv()

# Configure logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ],
    datefmt='%H:%M %d/%m/%Y'  # Updated logging timestamp format
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = '123456'
CORS(app)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4e3V7q8jL9kN"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))
AUDIO_STORAGE_PATH = "static/audio/"
BASE_URL = os.getenv("BASE_URL", f"http://{HOST}:{PORT}/")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))

# Create audio storage directory
os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)

# MySQL connection
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            port=MYSQL_PORT
        )
        return connection
    except Error as e:
        logger.error(f"Database connection error: {e}")
        return None

# Initialize database
def init_db():
    connection = get_db_connection()
    if not connection:
        logger.error("Failed to initialize database - no connection")
        return

    try:
        cursor = connection.cursor()
        # Drop existing logs table
        cursor.execute("DROP TABLE IF EXISTS logs")
        logger.info("Existing logs table dropped")

        # Create new logs table with timestamp
        create_table_query = """
        CREATE TABLE logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            uuid VARCHAR(36),
            request_text TEXT,
            number VARCHAR(20),
            response_text TEXT,
            audio_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_table_query)
        connection.commit()
        logger.info("New logs table created with timestamp column")
    except Error as e:
        logger.error(f"Database initialization error: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# Helper function to format timestamp
def format_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp.strftime('%H:%M %d/%m/%Y')
    return timestamp

# Save log to MySQL
def save_log_to_db(uuid=None, request_text=None, number=None, response_text=None, audio_link=None):
    connection = get_db_connection()
    if not connection:
        logger.error("No database connection for logging")
        return

    try:
        cursor = connection.cursor()
        query = """
        INSERT INTO logs (uuid, request_text, number, response_text, audio_link, created_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """
        values = (uuid, request_text, number, response_text, audio_link)
        cursor.execute(query, values)
        connection.commit()
        # Retrieve the inserted log to format the timestamp for logging
        cursor.execute("SELECT created_at FROM logs WHERE id = LAST_INSERT_ID()")
        created_at = cursor.fetchone()[0]
        formatted_time = format_timestamp(created_at)
        logger.info(f"Log saved: uuid={uuid}, request_text='{request_text}', created_at={formatted_time}")
    except Error as e:
        logger.error(f"Error saving log: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# Initialize database
init_db()

# Debug environment variables
logger.info(f"OPENAI_API_KEY: {OPENAI_API_KEY[:4] if OPENAI_API_KEY else 'Not set'}...")
logger.info(f"ELEVENLABS_API_KEY: {ELEVENLABS_API_KEY[:4] if ELEVENLABS_API_KEY else 'Not set'}...")

# Validate API keys
if not OPENAI_API_KEY or not ELEVENLABS_API_KEY:
    logger.error("Missing OPENAI_API_KEY or ELEVENLABS_API_KEY")
    raise ValueError("OPENAI_API_KEY or ELEVENLABS_API_KEY not set")

# Validate MySQL configuration
if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
    logger.error("Missing MySQL configuration variables")
    raise ValueError("MySQL configuration (HOST, USER, PASSWORD, DATABASE) not set")

openai.api_key = OPENAI_API_KEY

# Log incoming requests
@app.before_request
def log_request():
    body = None
    content_type = request.headers.get('Content-Type', '').lower()
    if 'application/json' in content_type:
        body = request.get_json(silent=True)
    elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
        body = dict(request.form) if request.form else None
    elif request.data:
        try:
            body = request.data.decode('utf-8', errors='ignore')
        except UnicodeDecodeError:
            body = "[Binary data]"
    log_data = {
        "timestamp": format_timestamp(datetime.utcnow()),
        "client_ip": request.remote_addr,
        "method": request.method,
        "url": request.url,
        "headers": dict(request.headers),
        "body": body
    }
    logger.info(f"Incoming request: {log_data}")

# Conversation state management
conversation_states = {}

def get_conversation_state(session_uuid):
    if session_uuid not in conversation_states:
        conversation_states[session_uuid] = {
            "step": "greeting",
            "something_else_count": 0,
            "contact_requested": False,
            "contact_details": {"name": None, "email": None, "phone": None}
        }
    return conversation_states[session_uuid]

def reset_conversation_state(session_uuid):
    conversation_states[session_uuid] = {
        "step": "greeting",
        "something_else_count": 0,
        "contact_requested": False,
        "contact_details": {"name": None, "email": None, "phone": None}
    }

# Tax debt prompt
TAX_DEBT_PROMPT = """
Do you have a federal tax debt over five thousand dollars or any missed filings?
Please respond with 'yes,' 'no,' or something else.
"""

def ask_tax_debt_question():
    return TAX_DEBT_PROMPT

def repeat_tax_debt_question():
    return "I am sorry, I didn't understand. Let me repeat: Do you have a federal tax debt over five thousand dollars or any missed tax filings? Please respond with 'yes,' 'no,' or something else."

# Text-to-speech
def text_to_speech(text):
    url = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            logger.info(f"Audio generated successfully for text: '{text}'")
            unique_id = hashlib.md5(f"{text}_{uuid.uuid4()}".encode()).hexdigest()
            audio_filename = f"{unique_id}.mp3"
            audio_path = os.path.join(AUDIO_STORAGE_PATH, audio_filename)

            with open(audio_path, 'wb') as f:
                f.write(response.content)

            audio_url = f"{BASE_URL}{AUDIO_STORAGE_PATH}{audio_filename}"
            return audio_url
        else:
            try:
                error_detail = response.json()
            except ValueError:
                error_detail = response.text
            logger.error(f"ElevenLabs API error: Status {response.status_code}, Response: {error_detail}")
            return None
    except Exception as e:
        logger.error(f"Error in text_to_speech: {e}")
        return None

# OpenAI query
def query_openai(user_input, conversation_state, phone_number):
    prompt = f"""
You are an AI assistant handling inquiries about federal tax debt. The user's phone number is {phone_number}. Respond naturally and politely, staying within the context of tax debt or missed filings. If the query is unrelated, gently steer back to the tax debt question. Do not invent specific tax law details unless provided. If the user requests a callback, use the provided phone number {phone_number}.

**User Query**:
{user_input}

**Conversation State**:
Step: {conversation_state['step']}
Something Else Count: {conversation_state['something_else_count']}

Provide the response text only.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "I'm sorry, something went wrong. Please try again."

# Process user input
def process_user_input(user_input, session_uuid, phone_number):
    if not user_input or not session_uuid or not phone_number:
        logger.error("Empty input, uuid, or phone number")
        return "I'm sorry, I need your input, session ID, and phone number to proceed. Please try again."

    conversation_state = get_conversation_state(session_uuid)
    user_input_lower = user_input.lower().strip()

    greetings = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
    goodbyes = ['good bye', 'bye', 'thanks a lot', 'thank you', 'see you', 'thnx', 'thank', 'by']

    if any(phrase in user_input_lower for phrase in goodbyes):
        response_text = "Thanks a lot! If you need any help, feel free to contact."
        reset_conversation_state(session_uuid)
        return response_text

    if any(greeting in user_input_lower for greeting in greetings) and conversation_state['step'] == 'greeting':
        conversation_state['step'] = 'tax_debt'
        return ask_tax_debt_question()

    if conversation_state['step'] == 'greeting':
        conversation_state['step'] = 'tax_debt'
        return ask_tax_debt_question()

    elif conversation_state['step'] == 'tax_debt':
        if 'yes' in user_input_lower:
            conversation_state['contact_requested'] = True
            conversation_state['step'] = 'collect_name'
            if 'call me back' in user_input_lower:
                return "Sure, I can arrange for someone to call you back. Could you please tell me your name?"
            return "Thank you for letting me know. I'll transfer you to our team. Could you please provide your name?"
        elif 'no' in user_input_lower:
            conversation_state['step'] = 'confirm_no'
            if 'do not call' in user_input_lower or 'dnc' in user_input_lower:
                return "Yes, I will add you to our Do Not Call list now, but are you sure you don't have a tax debt?"
            return "Not a problem, but before I let you go, are you sure you don't have a tax debt?"
        else:
            conversation_state['something_else_count'] += 1
            if conversation_state['something_else_count'] >= 2:
                response_text = "I'm sorry, I couldn't understand your response. Thank you for your time! Goodbye!"
                reset_conversation_state(session_uuid)
                return response_text
            return repeat_tax_debt_question()

    elif conversation_state['step'] == 'confirm_no':
        if 'yes' in user_input_lower or 'sure' in user_input_lower:
            response_text = "Thank you for confirming. If you have any future tax-related questions, feel free to reach out. Goodbye!"
            reset_conversation_state(session_uuid)
            return response_text
        elif 'no' in user_input_lower:
            conversation_state['contact_requested'] = True
            conversation_state['step'] = 'collect_name'
            return "Thank you for clarifying. I'll transfer you to our team. Could you please provide your name?"
        else:
            return "I'm sorry, I didn't understand. Are you sure you don't have a tax debt? Please say 'yes' or 'no.'"

    elif conversation_state['step'] in ['collect_name', 'collect_email', 'contact_complete']:
        if conversation_state['step'] == 'collect_name':
            if not user_input.strip():
                return "I'm sorry, I need your name to proceed. Could you please tell me your name?"
            conversation_state['contact_details']['name'] = user_input.strip()
            conversation_state['step'] = 'collect_email'
            return "Thank you! Could you please provide your email address?"
        elif conversation_state['step'] == 'collect_email':
            if not user_input.strip():
                return "I'm sorry, I need your email to proceed. Could you please provide your email address?"
            conversation_state['contact_details']['email'] = user_input.strip()
            conversation_state['step'] = 'contact_complete'
            conversation_state['contact_details']['phone'] = phone_number
            response_text = f"Thank you, {conversation_state['contact_details']['name']}! One of our team members will contact you soon at {phone_number}. Is there anything else I can help you with?"
            conversation_state['contact_requested'] = False
            return response_text
        elif conversation_state['step'] == 'contact_complete':
            return "We've got your details, and someone will reach out soon. Is there anything else I can assist you with?"

    return query_openai(user_input, conversation_state, phone_number)

# Process text and generate MP3
@app.route('/process_text_mp3', methods=['POST'])
def process_text_mp3():
    try:
        data = request.get_json()
        if not data or 'text' not in data or 'uuid' not in data or 'number' not in data:
            logger.error("Missing text, uuid, or number in the request")
            return jsonify({'error': 'Missing text, uuid, or number in the request'}), 400

        user_input = data['text'].strip()
        session_uuid = data['uuid']
        phone_number = data['number']

        if not user_input or not session_uuid or not phone_number:
            logger.error("Empty text, uuid, or number provided")
            save_log_to_db(
                uuid=session_uuid,
                request_text=user_input or "Empty input",
                number=phone_number
            )
            return jsonify({'error': 'Empty text, uuid, or number provided'}), 400

        logger.info(f"Processing text input: '{user_input}' from session {session_uuid} with number {phone_number}")
        save_log_to_db(
            uuid=session_uuid,
            request_text=user_input,
            number=phone_number
        )

        response_text = process_user_input(user_input, session_uuid, phone_number)
        audio_url = text_to_speech(response_text)

        if audio_url is None:
            logger.error("Failed to generate audio response")
            save_log_to_db(
                uuid=session_uuid,
                request_text=user_input,
                number=phone_number,
                response_text=response_text,
                audio_link=None
            )
            return jsonify({
                'response': response_text,
                'error': 'Failed to generate audio response'
            }), 500

        logger.info(f"Response generated: '{response_text}' with audio_url: {audio_url}")
        save_log_to_db(
            uuid=session_uuid,
            request_text=user_input,
            number=phone_number,
            response_text=response_text,
            audio_link=audio_url
        )

        return jsonify({
            'response': response_text,
            'audio_url': audio_url
        })
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        save_log_to_db(
            uuid=session_uuid if 'session_uuid' in locals() else None,
            request_text=user_input if 'user_input' in locals() else None,
            number=phone_number if 'phone_number' in locals() else None,
            response_text=None,
            audio_link=None
        )
        return jsonify({'error': str(e)}), 500

# Serve audio files
@app.route('/static/audio/<filename>')
def serve_audio(filename):
    audio_path = os.path.join(AUDIO_STORAGE_PATH, filename)
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found: {audio_path}")
        return jsonify({'error': 'Audio file not found'}), 404
    logger.info(f"Serving audio file: {audio_path}")
    return send_file(audio_path, mimetype='audio/mpeg')

# Optional: Route to retrieve logs with formatted timestamp
# Helper function to format timestamp
def format_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp.strftime('%H:%M %d/%m/%Y')
    return str(timestamp)  # Fallback for unexpected types

# Optional: Route to retrieve logs with formatted timestamp
@app.route('/get_logs', methods=['GET'])
def get_logs():
    connection = get_db_connection()
    if not connection:
        logger.error("No database connection for retrieving logs")
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT id, uuid, request_text, number, response_text, audio_link, created_at FROM logs ORDER BY created_at DESC"
        cursor.execute(query)
        logs = cursor.fetchall()
        # Format the created_at field for each log
        for log in logs:
            log['created_at'] = format_timestamp(log['created_at'])
        logger.info(f"Retrieved {len(logs)} logs")
        return jsonify(logs)
    except Error as e:
        logger.error(f"Error retrieving logs: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
if __name__ == '__main__':
    logger.info(f"Starting Tax Debt Assistant API on {HOST}:{PORT}...")
    app.run(debug=True, host=HOST, port=PORT)
