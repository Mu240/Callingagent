from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
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
    datefmt='%H:%M %d/%m/%Y'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = '123456'
CORS(app)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
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
        cursor.execute("DROP TABLE IF EXISTS logs")
        logger.info("Existing logs table dropped")

        create_table_query = """
        CREATE TABLE logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            uuid VARCHAR(36),
            request_text TEXT,
            number VARCHAR(20),
            response_text TEXT,
            audio_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end TINYINT DEFAULT 0,
            transfer TINYINT DEFAULT 0
        )
        """
        cursor.execute(create_table_query)
        connection.commit()
        logger.info("New logs table created with timestamp, end, and transfer columns")
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
def save_log_to_db(uuid=None, request_text=None, number=None, response_text=None, audio_link=None, end=0, transfer=0):
    connection = get_db_connection()
    if not connection:
        logger.error("No database connection for logging")
        return

    try:
        cursor = connection.cursor()
        query = """
        INSERT INTO logs (uuid, request_text, number, response_text, audio_link, created_at, end, transfer)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s)
        """
        values = (uuid, request_text, number, response_text, audio_link, end, transfer)
        cursor.execute(query, values)
        connection.commit()
        cursor.execute("SELECT created_at FROM logs WHERE id = LAST_INSERT_ID()")
        created_at = cursor.fetchone()[0]
        formatted_time = format_timestamp(created_at)
        logger.info(
            f"Log saved: uuid={uuid}, request_text='{request_text}', created_at={formatted_time}, end={end}, transfer={transfer}")
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

# Validate API keys and MySQL configuration
if not OPENAI_API_KEY:
    logger.error("Missing OPENAI_API_KEY")
    raise ValueError("OPENAI_API_KEY not set")

if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
    logger.error("Missing MySQL configuration variables")
    raise ValueError("MySQL configuration (HOST, USER, PASSWORD, DATABASE) not set")

# Conversation state management
conversation_states = {}


def get_conversation_state(session_uuid):
    if session_uuid not in conversation_states:
        conversation_states[session_uuid] = {
            "step": "greeting",
            "repeat_count": 0,
            "last_prompt": "greeting",
            "specific_repeat_count": {"who are you": 0, "what did you say": 0, "something else": 0}
        }
    return conversation_states[session_uuid]


def reset_conversation_state(session_uuid):
    conversation_states[session_uuid] = {
        "step": "greeting",
        "repeat_count": 0,
        "last_prompt": "greeting",
        "specific_repeat_count": {"who are you": 0, "what did you say": 0, "something else": 0}
    }


# Prompts from PDF
PROMPTS = {
    "greeting": "Hi, my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "end_call": "Thank you for your time, unfortunately we are no able to help you at this time.",
    "transfer": "Please wait and the next available live agent will answer the call.",
    "never_owed": "Thank you for your time. It looks like we're unable to assist you at this time, but please feel free to call us in the future if you have any past tax filings that need to be completed or unresolved tax issues.",
    "how_did_u_get_number": "not sure but Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "on_disability": "We can help you. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "not_the_person": "I understand. Please feel free to call us in the future if you have any unfiled past tax returns or unresolved tax issues.",
    "not_sure": "If you'd like to check, I can transfer you to a live agent now. Would you like to see if you have any unresolved tax issues?",
    "this_is_business": "Certainly, and sorry for the call. But before I go, do you personally have any missed tax filings or owe more than Five Thousand dollars in federal taxes?",
    "what_is_this_about": "We help people with federal tax debts or past unfilled taxes. Do you have a tax debt of $5,000 or unfiled tax returns?",
    "are_you_computer": "I am an AI Virtual Assistant, do you personally have any missed tax filings or owe more than Five Thousand dollars in federal taxes?",
    "do_not_call": "I would be happy to do that, but before I go do you personally have any missed tax filings or owe more than Five Thousand dollars in federal taxes?",
    "something_different": "I am sorry, I don't understand what you said but my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "yes": "Ok let me transfer you to a live agent. Is your Tax Debt federal or State?",
    "state": "We can only help you if a Federal tax debt or unfiled back tax returns. Thank you for your time. Before I go, are you sure it is a State Tax debt not a federal Tax debt?",
    "no": "We can only help you if the tax debt is federal, but thank you for your time. Before I go, are you sure it is a state tax debt, not a federal tax debt?",
    "something_else": "I am sorry I did not understand, Let me repeat, do you personally have any tax filing you missed or do you owe more than five thousand dollars in federal taxes?"
}

# Mapping of response texts to pre-recorded audio filenames
AUDIO_MAP = {text: f"{key}.mp3" for key, text in PROMPTS.items()}

# Dynamically update AUDIO_MAP with existing audio files
for filename in os.listdir(AUDIO_STORAGE_PATH):
    if filename.endswith(".mp3"):
        base_name = filename.replace(".mp3", "").lower()
        for key, text in PROMPTS.items():
            if base_name == key.lower():
                AUDIO_MAP[text] = filename
                break


def text_to_speech(text):
    audio_filename = AUDIO_MAP.get(text)
    if audio_filename and os.path.exists(os.path.join(AUDIO_STORAGE_PATH, audio_filename)):
        audio_url = f"{BASE_URL}{AUDIO_STORAGE_PATH}{audio_filename}"
        logger.info(f"Using pre-recorded audio: {audio_url} for text: '{text}'")
        return audio_url
    else:
        logger.error(f"No pre-recorded audio found for text: '{text}'")
        return None


# Process user input with improved logic
def process_user_input(user_input, session_uuid, phone_number):
    if not session_uuid or not phone_number:
        logger.error("Empty uuid or phone number")
        return "I'm sorry, I need your session ID and phone number to proceed. Please try again.", 0, 0

    conversation_state = get_conversation_state(session_uuid)

    # Check if this is the first call (no user input, just uuid and phone number)
    if not user_input or user_input.strip() == "":
        conversation_state['step'] = 'tax_debt'
        conversation_state['last_prompt'] = 'greeting'
        return PROMPTS["greeting"], 0, 0

    user_input_lower = user_input.lower().strip()

    # Handle no response or silence
    if user_input_lower in ["", "silence"]:
        conversation_state['repeat_count'] += 1
        if conversation_state['repeat_count'] >= 3:
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0
        return PROMPTS[conversation_state['last_prompt']], 0, 0  # Repeat last prompt

    # Handle goodbye-like responses
    goodbyes = ['good bye', 'bye', 'thanks a lot', 'thank you', 'see you', 'thnx', 'thank', 'by']
    if any(phrase in user_input_lower for phrase in goodbyes):
        reset_conversation_state(session_uuid)
        return PROMPTS["end_call"], 1, 0

    # Keyword and synonym mapping for better matching
    input_mappings = {
        "greeting": ["hi", "hello", "start", "begin"],
        "who are you": ["who are you", "who is this", "who's calling", "who are u"],
        "what did you say": ["what did you say", "repeat", "say again", "what was that", "huh"],
        "never_owed": ["i have never owed", "never owed", "no debt", "don’t owe", "never had debt"],
        "how_did_u_get_number": ["how did u get my number", "where did you get my number", "how’d you get my phone",
                                 "who gave you my number", "where’s my number from"],
        "on_disability": ["i am on disability", "on disability", "i’m disabled", "disability benefits"],
        "not_the_person": ["i am not the person", "wrong person", "not me", "wrong number"],
        "not_sure": ["not sure", "i dont know", "don’t know", "unsure", "maybe"],
        "this_is_business": ["this is a business", "business line", "company phone", "not personal"],
        "what_is_this_about": ["what is this about", "what’s this for", "why are you calling", "what do you want"],
        "are_you_computer": ["are you a computer", "are you a real person", "is this a bot", "are you ai", "robot"],
        "do_not_call": ["put me on your do not call list", "do not call", "don’t call me", "stop calling", "no calls"],
        "yes": ["yes", "yeah", "yep", "sure", "okay", "ok"],
        "no": ["no", "nope", "not really", "nah", "no way"],
        "federal": ["federal", "fed", "irs", "federal tax", "federal debt"],
        "state": ["state", "state tax", "local tax", "not federal", "state debt"],
        "something_else": []  # Fallback for unmatched inputs
    }

    # Function to find the best matching prompt key
    def find_best_match(input_text, mappings):
        for key, phrases in mappings.items():
            if key == "something_else":  # Skip fallback initially
                continue
            for phrase in phrases:
                if phrase in input_text:
                    return key
        return "something_else"  # Default if no match

    # Determine the best prompt key based on user input
    matched_key = find_best_match(user_input_lower, input_mappings)

    # Step: tax_debt
    if conversation_state['step'] == 'tax_debt':
        if matched_key == "who are you":
            conversation_state['specific_repeat_count']['who are you'] += 1
            if conversation_state['specific_repeat_count']['who are you'] >= 2:
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            conversation_state['last_prompt'] = 'who are you'
            return PROMPTS["who are you"], 0, 0

        elif matched_key == "what did you say":
            conversation_state['specific_repeat_count']['what did you say'] += 1
            if conversation_state['specific_repeat_count']['what did you say'] >= 2:
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            conversation_state['last_prompt'] = 'what did you say'
            return PROMPTS[conversation_state['last_prompt']], 0, 0  # Repeat last prompt

        elif matched_key == "never_owed":
            reset_conversation_state(session_uuid)
            return PROMPTS["never_owed"], 1, 0

        elif matched_key == "how_did_u_get_number":
            conversation_state['last_prompt'] = 'how_did_u_get_number'
            return PROMPTS["how_did_u_get_number"], 0, 0

        elif matched_key == "on_disability":
            conversation_state['last_prompt'] = 'on_disability'
            return PROMPTS["on_disability"], 0, 0

        elif matched_key == "not_the_person":
            reset_conversation_state(session_uuid)
            return PROMPTS["not_the_person"], 1, 0

        elif matched_key == "not_sure":
            conversation_state['step'] = 'offer_transfer'
            conversation_state['last_prompt'] = 'not_sure'
            return PROMPTS["not_sure"], 0, 1

        elif matched_key == "this_is_business":
            conversation_state['last_prompt'] = 'this_is_business'
            return PROMPTS["this_is_business"], 0, 0

        elif matched_key == "what_is_this_about":
            conversation_state['last_prompt'] = 'what_is_this_about'
            return PROMPTS["what_is_this_about"], 0, 0

        elif matched_key == "are_you_computer":
            conversation_state['last_prompt'] = 'are_you_computer'
            return PROMPTS["are_you_computer"], 0, 0

        elif matched_key == "do_not_call":
            conversation_state['last_prompt'] = 'do_not_call'
            return PROMPTS["do_not_call"], 0, 0

        elif matched_key == "yes":
            conversation_state['step'] = 'tax_type'
            conversation_state['last_prompt'] = 'yes'
            return PROMPTS["yes"], 0, 1

        elif matched_key == "no":
            conversation_state['step'] = 'confirm_no'
            conversation_state['last_prompt'] = 'no'
            return PROMPTS["no"], 1, 0

        else:  # matched_key == "something_else"
            conversation_state['specific_repeat_count']['something else'] += 1
            if conversation_state['specific_repeat_count']['something else'] >= 3:
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            conversation_state['last_prompt'] = 'something_else'
            return PROMPTS["something_else"], 0, 0

    # Step: offer_transfer
    elif conversation_state['step'] == 'offer_transfer':
        if matched_key == "yes":
            conversation_state['step'] = 'tax_type'
            conversation_state['last_prompt'] = 'yes'
            return PROMPTS["yes"], 0, 1
        else:
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0

    # Step: tax_type
    elif conversation_state['step'] == 'tax_type':
        if matched_key == "federal":
            reset_conversation_state(session_uuid)
            return PROMPTS["transfer"], 0, 1
        elif matched_key == "state":
            conversation_state['step'] = 'confirm_state'
            conversation_state['last_prompt'] = 'state'
            return PROMPTS["state"], 1, 0
        else:
            conversation_state['specific_repeat_count']['something else'] += 1
            if conversation_state['specific_repeat_count']['something else'] >= 3:
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            conversation_state['last_prompt'] = 'something_else'
            return PROMPTS["something_else"], 0, 0

    # Step: confirm_no
    elif conversation_state['step'] == 'confirm_no':
        if matched_key == "yes":
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0
        elif matched_key == "no":
            conversation_state['step'] = 'tax_type'
            conversation_state['last_prompt'] = 'yes'
            return PROMPTS["yes"], 0, 1
        else:
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0

    # Step: confirm_state
    elif conversation_state['step'] == 'confirm_state':
        if matched_key == "yes":
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0
        elif matched_key == "no":
            conversation_state['step'] = 'tax_type'
            conversation_state['last_prompt'] = 'yes'
            return PROMPTS["yes"], 0, 1
        else:
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0

    # Fallback: If no match, repeat the last prompt or end after too many attempts
    conversation_state['specific_repeat_count']['something else'] += 1
    if conversation_state['specific_repeat_count']['something else'] >= 3:
        reset_conversation_state(session_uuid)
        return PROMPTS["end_call"], 1, 0
    conversation_state['last_prompt'] = 'something_else'
    return PROMPTS["something_else"], 0, 0


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


# Process text and generate MP3
@app.route('/process_text_mp3', methods=['POST'])
def process_text_mp3():
    try:
        data = request.get_json()
        if not data or 'uuid' not in data or 'number' not in data:
            logger.error("Missing uuid or number in the request")
            return jsonify({'error': 'Missing uuid or number in the request'}), 400

        user_input = data.get('text', '').strip()
        session_uuid = data['uuid']
        phone_number = data['number']

        if not session_uuid or not phone_number:
            logger.error("Empty uuid or number provided")
            save_log_to_db(
                uuid=session_uuid,
                request_text=user_input or "Empty input",
                number=phone_number,
                end=0,
                transfer=0
            )
            return jsonify({'error': 'Empty uuid or number provided'}), 400

        logger.info(f"Processing text input: '{user_input}' from session {session_uuid} with number {phone_number}")
        response_text, end, transfer = process_user_input(user_input, session_uuid, phone_number)
        audio_url = text_to_speech(response_text)

        save_log_to_db(
            uuid=session_uuid,
            request_text=user_input,
            number=phone_number,
            response_text=response_text,
            audio_link=audio_url,
            end=end,
            transfer=transfer
        )

        if audio_url is None:
            logger.error("Failed to generate audio response")
            return jsonify({
                'response': response_text,
                'end': end,
                'transfer': transfer,
                'error': 'Failed to generate audio response'
            }), 500

        logger.info(
            f"Response generated: '{response_text}' with audio_url: {audio_url}, end: {end}, transfer: {transfer}")
        return jsonify({
            'response': response_text,
            'audio_url': audio_url,
            'end': end,
            'transfer': transfer
        })
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        save_log_to_db(
            uuid=session_uuid if 'session_uuid' in locals() else None,
            request_text=user_input if 'user_input' in locals() else None,
            number=phone_number if 'phone_number' in locals() else None,
            response_text=None,
            audio_link=None,
            end=0,
            transfer=0
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
@app.route('/get_logs', methods=['GET'])
def get_logs():
    connection = get_db_connection()
    if not connection:
        logger.error("No database connection for retrieving logs")
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT id, uuid, request_text, number, response_text, audio_link, created_at, end, transfer FROM logs ORDER BY created_at DESC"
        cursor.execute(query)
        logs = cursor.fetchall()
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
