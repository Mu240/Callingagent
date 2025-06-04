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

# Load environment variables from .env file
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
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = '123456'
CORS(app)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))
AUDIO_STORAGE_PATH = "static/audio/"  # Directory to store audio files
BASE_URL = os.getenv("BASE_URL", f"http://{HOST}:{PORT}/")  # Base URL for audio files
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))

# Create audio storage directory if it doesn't exist
os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)


# MySQL connection function
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
        logger.error(f"Error connecting to MySQL: {e}")
        save_log_to_db("ERROR", f"Error connecting to MySQL: {e}")
        return None


# Create logs table if it doesn't exist
def init_db():
    connection = get_db_connection()
    if connection is None:
        logger.error("Failed to initialize database - no connection")
        save_log_to_db("ERROR", "Failed to initialize database - no connection")
        return

    try:
        cursor = connection.cursor()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME,
            level VARCHAR(20),
            message TEXT,
            client_ip VARCHAR(45),
            method VARCHAR(10),
            url TEXT,
            headers TEXT,
            body TEXT
        )
        """
        cursor.execute(create_table_query)
        connection.commit()
        logger.info("Database initialized successfully")
        save_log_to_db("INFO", "Database initialized successfully")
    except Error as e:
        logger.error(f"Error initializing database: {e}")
        save_log_to_db("ERROR", f"Error initializing database: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# Function to save log to MySQL
def save_log_to_db(level, message, client_ip=None, method=None, url=None, headers=None, body=None):
    connection = get_db_connection()
    if connection is None:
        logger.error("Cannot save log to database - no connection")
        return

    try:
        cursor = connection.cursor()
        query = """
        INSERT INTO logs (timestamp, level, message, client_ip, method, url, headers, body)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            datetime.utcnow(),
            level,
            message,
            client_ip,
            method,
            url,
            str(headers) if headers else None,
            str(body) if body else None
        )
        cursor.execute(query, values)
        connection.commit()
        logger.info(f"Successfully saved log to database: {message}")
    except Error as e:
        logger.error(f"Error saving log to database: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# Debug environment variables
logger.info(f"Loaded OPENAI_API_KEY: {OPENAI_API_KEY[:4] if OPENAI_API_KEY else 'Not set'}...")
save_log_to_db("INFO", f"Loaded OPENAI_API_KEY: {OPENAI_API_KEY[:4] if OPENAI_API_KEY else 'Not set'}...")
logger.info(f"Loaded ELEVENLABS_API_KEY: {ELEVENLABS_API_KEY[:4] if ELEVENLABS_API_KEY else 'Not set'}...")
save_log_to_db("INFO", f"Loaded ELEVENLABS_API_KEY: {ELEVENLABS_API_KEY[:4] if ELEVENLABS_API_KEY else 'Not set'}...")

# Validate API keys
if not OPENAI_API_KEY or not ELEVENLABS_API_KEY:
    logger.error("OPENAI_API_KEY or ELEVENLABS_API_KEY not set in environment variables")
    save_log_to_db("ERROR", "OPENAI_API_KEY or ELEVENLABS_API_KEY not set in environment variables")
    raise ValueError("OPENAI_API_KEY or ELEVENLABS_API_KEY not set in environment variables")

# Validate MySQL configuration
if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
    logger.error("MySQL configuration variables not set in environment variables")
    save_log_to_db("ERROR", "MySQL configuration variables not set in environment variables")
    raise ValueError(
        "MySQL configuration variables (MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE) not set in environment variables")

openai.api_key = OPENAI_API_KEY


# Middleware to log all incoming requests
@app.before_request
def log_request():
    # Safely handle the request body based on content type
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
        "timestamp": datetime.utcnow().isoformat(),
        "client_ip": request.remote_addr,
        "method": request.method,
        "url": request.url,
        "headers": dict(request.headers),
        "body": body
    }
    logger.info(f"Incoming request: {log_data}")
    save_log_to_db(
        "INFO",
        f"Incoming request: {log_data}",
        client_ip=request.remote_addr,
        method=request.method,
        url=request.url,
        headers=dict(request.headers),
        body=body
    )


# Store conversation states for each session
conversation_states = {}


def get_conversation_state(session_uuid):
    if session_uuid not in conversation_states:
        conversation_states[session_uuid] = {
            "step": "greeting",
            "something_else_count": 0,
            "contact_requested": False,
            "contact_details": {"name": None, "email": None, "phone": None},
        }
    return conversation_states[session_uuid]


def reset_conversation_state(session_uuid):
    conversation_states[session_uuid] = {
        "step": "greeting",
        "something_else_count": 0,
        "contact_requested": False,
        "contact_details": {"name": None, "email": None, "phone": None},
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
            save_log_to_db("INFO", f"Audio generated successfully for text: '{text}'")
            # Generate unique filename using hash of text and timestamp
            unique_id = hashlib.md5(f"{text}_{uuid.uuid4()}".encode()).hexdigest()
            audio_filename = f"{unique_id}.mp3"
            audio_path = os.path.join(AUDIO_STORAGE_PATH, audio_filename)

            # Save audio file
            with open(audio_path, 'wb') as f:
                f.write(response.content)

            # Return URL to the audio file
            audio_url = f"{BASE_URL}{AUDIO_STORAGE_PATH}{audio_filename}"
            return audio_url
        else:
            logger.error(f"ElevenLabs API error: Status {response.status_code}, Response: {response.text}")
            save_log_to_db("ERROR", f"ElevenLabs API error: Status {response.status_code}, Response: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error in text_to_speech: {e}")
        save_log_to_db("ERROR", f"Error in text_to_speech: {e}")
        return None


def query_openai(user_input, conversation_state, phone_number):
    prompt = f"""
You are an AI assistant handling inquiries about federal tax debt. The user's phone number is {phone_number}. Respond naturally and politely to the user's query, staying within the context of tax debt or missed filings. If the query is unrelated, gently steer the conversation back to the tax debt question. Do not invent specific details about tax laws or financial advice unless explicitly provided. If the user asks for a callback or transfer, guide them to provide contact details, but use the provided phone number {phone_number} instead of asking for it again.

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
        logger.error(f"Error in query_openai: {e}")
        save_log_to_db("ERROR", f"Error in query_openai: {e}")
        return "I'm sorry, something went wrong. Please try again."


def process_user_input(user_input, session_uuid, phone_number):
    if not user_input or not session_uuid or not phone_number:
        logger.error("Empty input, uuid, or phone number in process_user_input")
        save_log_to_db("ERROR", "Empty input, uuid, or phone number in process_user_input")
        return "I'm sorry, I need your input, session ID, and phone number to proceed. Please try again."

    conversation_state = get_conversation_state(session_uuid)
    user_input_lower = user_input.lower().strip()

    # List of common greetings
    greetings = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']

    # List of common goodbye phrases
    goodbyes = ['good bye', 'bye', 'thanks a lot', 'thank you', 'see you', 'thanks', 'thnx', 'thank', 'by']

    # Check for closing statements
    if any(phrase in user_input_lower for phrase in goodbyes):
        response_text = "Thanks a lot! If you need any help, feel free to contact."
        reset_conversation_state(session_uuid)
        return response_text

    # Check for greetings
    if any(greeting in user_input_lower for greeting in greetings) and conversation_state['step'] == 'greeting':
        conversation_state['step'] = 'tax_debt'
        return ask_tax_debt_question()

    # Handle conversation flow
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
        else:  # Something else
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

    # Fallback to OpenAI for unhandled cases
    return query_openai(user_input, conversation_state, phone_number)


@app.route('/process_text_mp3', methods=['POST'])
def process_text_mp3():
    try:
        # Get JSON data from the API request
        data = request.get_json()
        if not data or 'text' not in data or 'uuid' not in data or 'number' not in data:
            logger.error("Missing text, uuid, or number in the request")
            save_log_to_db("ERROR", "Missing text, uuid, or number in the request")
            return jsonify({'error': 'Missing text, uuid, or number in the request'}), 400

        user_input = data['text'].strip()
        session_uuid = data['uuid']
        phone_number = data['number']

        if not user_input or not session_uuid or not phone_number:
            logger.error("Empty text, uuid, or number provided")
            save_log_to_db("ERROR", "Empty text, uuid, or number provided")
            return jsonify({'error': 'Empty text, uuid, or number provided'}), 400

        logger.info(f"Processing text input: '{user_input}' from session {session_uuid} with number {phone_number}")
        save_log_to_db("INFO",
                       f"Processing text input: '{user_input}' from session {session_uuid} with number {phone_number}")

        # Process the text input
        response_text = process_user_input(user_input, session_uuid, phone_number)

        # Convert the response text to audio and get URL
        audio_url = text_to_speech(response_text)

        if audio_url is None:
            logger.error("Failed to generate audio response")
            save_log_to_db("ERROR", "Failed to generate audio response")
            return jsonify({
                'response': response_text,
                'error': 'Failed to generate audio response'
            }), 500

        # Log successful response
        logger.info(f"Response generated: '{response_text}' with audio_url: {audio_url}")
        save_log_to_db("INFO", f"Response generated: '{response_text}' with audio_url: {audio_url}")

        # Return JSON with text and audio URL
        return jsonify({
            'response': response_text,
            'audio_url': audio_url
        })
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        save_log_to_db("ERROR", f"Error processing text: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/static/audio/<filename>')
def serve_audio(filename):
    audio_path = os.path.join(AUDIO_STORAGE_PATH, filename)
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found: {audio_path}")
        save_log_to_db("ERROR", f"Audio file not found: {audio_path}")
        return jsonify({'error': 'Audio file not found'}), 404
    logger.info(f"Serving audio file: {audio_path}")
    save_log_to_db("INFO", f"Serving audio file: {audio_path}")
    return send_file(audio_path, mimetype='audio/mpeg')


if __name__ == '__main__':
    # Initialize database
    init_db()
    logger.info(f"Starting Tax Debt Assistant API on {HOST}:{PORT}...")
    save_log_to_db("INFO", f"Starting Tax Debt Assistant API on {HOST}:{PORT}...")
    app.run(debug=True, host=HOST, port=PORT)
