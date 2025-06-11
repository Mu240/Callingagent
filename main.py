from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import os
import uuid
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
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", '123456')
CORS(app)

# Configuration
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
        logger.info("New logs table created")
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

# Validate MySQL configuration
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
            "last_input": None,
            "specific_repeat_count": {"who are you": 0, "what did you say": 0, "something_different": 0, "not_the_person": 0},
            "input_counts": {}
        }
        logger.info(
            f"Initialized new conversation state for uuid={session_uuid}, step={conversation_states[session_uuid]['step']}")
    return conversation_states[session_uuid]

def reset_conversation_state(session_uuid):
    conversation_states[session_uuid] = {
        "step": "greeting",
        "repeat_count": 0,
        "last_prompt": "greeting",
        "last_input": None,
        "specific_repeat_count": {"who are you": 0, "what did you say": 0, "something_different": 0, "not_the_person": 0},
        "input_counts": {}
    }
    logger.info(f"Reset conversation state for uuid={session_uuid}")

# Input mappings for user input variations
input_mappings = {
    "greeting": ["hi", "hello", "start", "begin"],
    "who are you": ["who are you", "who is this", "who's calling", "who are u"],
    "what did you say": ["what did you say", "repeat", "say again", "what was that", "huh"],
    "never_owed": ["i have never owed", "never owed", "no debt", "don’t owe", "never had debt", "owe"],
    "how_did_u_get_number": ["number", "how did u get my number", "where did you get my number",
                             "how’d you get my phone", "who gave you my number", "where’s my number from"],
    "on_disability": ["disable", "i am on disability", "on disability", "i’m disabled", "disability benefits"],
    "social": ["social", "social security", "i am on social security", "on social security", "social benefits"],
    "not_the_person": ["not the person", "i am not the person", "wrong person", "not me", "wrong number"],
    "not_sure": ["not sure", "i dont know", "don’t know", "unsure", "maybe", "know"],
    "this_is_business": ["business", "this is a business", "business line", "company phone", "not personal"],
    "what_is_this_about": ["what is this about", "what’s this for", "why are you calling", "what do you want"],
    "are_you_computer": ["real person", "computer", "are you a computer", "are you a real person", "is this a bot",
                         "are you ai", "robot"],
    "do_not_call": ["call", "put me on your do not call list", "do not call", "don’t call me", "stop calling",
                    "no calls"],
    "both":["both", "federal and state", "state and federal", "both taxes"],

    "yes": ["yes", "yeah", "yep", "sure", "okay", "ok", "yup", "aye", "affirmative", "certainly", "of course", "definitely", "absolutely", "indeed", "sure thing", "you bet", "for sure", "by all means", "without a doubt", "I agree", "that’s right", "right on", "roger that", "true", "uh-huh", "totally", "okie-dokie", "for real"],
    "no": ["no", "nope", "not really", "nah", "no way", "nay", "negative", "not at all", "absolutely not", "never", "not quite", "I don’t think so", "I’m afraid not", "regrettably not", "unfortunately not", "by no means", "out of the question", "nothing doing", "not happening", "no can do", "certainly not", "over my dead body", "count me out", "I’ll pass", "no siree", "not in a million years"],

    "federal": ["federal", "fed", "irs", "federal tax", "federal debt"],
    "state": ["state", "state tax", "local tax", "not federal", "state debt"],
    "something_else": []
}

# List of common words to remove
STOP_WORDS = {
    "the", "a", "an", "like", "u", "were", "was", "is", "are", "and",
    "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
    "i", "you", "he", "she", "it", "we", "they", "that", "this", "what",
    "when", "where", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "only","put","me","your",
    "own", "same", "so", "than", "too", "very", "s", "t", "can", "will",
    "just", "don", "should", "now", "do", "not",
    "it's", "you're", "he's", "she's", "we're", "they're", "i'm", "that's",
    "what's", "who's", "where's", "when's", "why's", "how's", "don't",
    "won't", "can't", "shouldn't", "wouldn't", "couldn't", "i've", "you've",
    "they've", "we've"
}

# Prompts for responses
PROMPTS = {
    "greeting": "Hi, my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "end_call": "Thank you for your time, unfortunately we are not able to help you at this time.",
    "transfer": "Please wait and the next available live agent will answer the call.",
    "never_owed": "We can only help you if the tax debt is federal, but thank you for your time. Before I go, are you sure you don’t have a federal tax debt or unfiled tax returns?",
    "how_did_u_get_number": "Not sure, but do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "on_disability": "We can help you. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "social": "We can help you. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "not_the_person": "I understand. Please feel free to call us in the future if you have any unfiled past tax returns or unresolved tax issues.",
    "not_sure": "If you'd like to check, I can transfer you to a live agent now. Would you like to see if you have any unresolved tax issues?",
    "this_is_business": "Certainly, and sorry for the call. But before I go, do you personally have any missed tax filings or owe more than five thousand dollars in federal taxes?",
    "what_is_this_about": "We help people with federal tax debts or past unfiled taxes.",
    "are_you_computer": "I am an AI Virtual Assistant. Do you personally have any missed tax filings or owe more than five thousand dollars in federal taxes?",
    "do_not_call": "I would be happy to do that, but before I go, do you personally have any missed tax filings or owe more than five thousand dollars in federal taxes?",
    "something_different": "I am sorry, I don’t understand what you said, but my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "yes": "Ok, let me transfer you to a live agent. Is your tax debt federal or state?",
    "state": "We can only help you if a federal tax debt or unfiled back tax returns. Thank you for your time. Before I go, are you sure it is a state tax debt, not a federal tax debt?",
    "federal": "Please wait and the next available live agent will answer the call.",
    "both": "Please wait and the next available live agent will answer the call.",
    "no": "We can only help you if the tax debt is federal, but thank you for your time. Before I go, are you sure you don’t have a federal tax debt or unfiled tax returns?",
    "something_else": "I am sorry I did not understand. Let me repeat, do you personally have any tax filings you missed or do you owe more than five thousand dollars in federal taxes?"
}

# Mapping of response texts to audio filenames
AUDIO_MAP = {text: f"{key}.mp3" for key, text in PROMPTS.items()}

# Update AUDIO_MAP with existing audio files
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
    logger.error(f"No pre-recorded audio found for text: '{text}'")
    return None

# Map user input to a key
def map_user_input(user_input_lower):
    words = user_input_lower.split()
    filtered_words = [word for word in words if word not in STOP_WORDS or word in ["state", "federal"]]

    if not filtered_words:
        return "something_else"

    filtered_input = " ".join(filtered_words)

    if "federal" in filtered_words:
        return "federal"
    if "state" in filtered_words:
        return "state"

    for key, phrases in input_mappings.items():
        for phrase in phrases:
            phrase_words = phrase.split()
            filtered_phrase_words = [word for word in phrase_words if
                                     word not in STOP_WORDS or word in ["state", "federal"]]
            filtered_phrase = " ".join(filtered_phrase_words)

            if filtered_input == filtered_phrase:
                return key

            if filtered_phrase and filtered_phrase in filtered_input:
                return key

    for word in filtered_words:
        for key, phrases in input_mappings.items():
            for phrase in phrases:
                phrase_words = phrase.split()
                if word in phrase_words:
                    return key

    return "something_else"

# Process user input with interrupt logic for input_mappings
def process_user_input(user_input, session_uuid, phone_number):
    if not user_input or not session_uuid or not phone_number:
        logger.error("Empty input, uuid, or phone number")
        return PROMPTS["something_different"], 0, 0

    conversation_state = get_conversation_state(session_uuid)
    user_input_lower = user_input.lower().strip()
    mapped_input = map_user_input(user_input_lower)

    # Track all input responses
    conversation_state['input_counts'][mapped_input] = conversation_state['input_counts'].get(mapped_input, 0) + 1
    # Track specific inputs in specific_repeat_count
    if mapped_input in conversation_state['specific_repeat_count']:
        conversation_state['specific_repeat_count'][mapped_input] += 1
    # End call if any input (except "federal") is repeated twice
    if mapped_input != "federal" and conversation_state['input_counts'][mapped_input] >= 2:
        logger.info(f"Ending call for uuid={session_uuid} due to repeated input '{mapped_input}'")
        reset_conversation_state(session_uuid)
        return PROMPTS["end_call"], 1, 0
    conversation_state['last_input'] = mapped_input

    if user_input_lower in ["", "silence"]:
        conversation_state['repeat_count'] += 1
        if conversation_state['repeat_count'] >= 2:
            logger.info(f"Ending call for uuid={session_uuid} due to repeated silence")
            reset_conversation_state(session_uuid)
            return PROMPTS["end_call"], 1, 0
        return PROMPTS[conversation_state['last_prompt']], 0, 0

    if mapped_input == "greeting":
        conversation_state['last_prompt'] = "greeting"
        conversation_state['step'] = "greeting"
        return PROMPTS["greeting"], 0, 0

    elif mapped_input == "who are you":
        conversation_state['last_prompt'] = "who are you"
        return PROMPTS["who are you"], 0, 0

    elif mapped_input == "what did you say":
        conversation_state['last_prompt'] = conversation_state['last_prompt']
        return PROMPTS[conversation_state['last_prompt']], 0, 0

    elif mapped_input == "never_owed":
        reset_conversation_state(session_uuid)
        conversation_state['last_prompt'] = "never_owed"
        return PROMPTS["never_owed"], 0, 0

    elif mapped_input == "how_did_u_get_number":
        conversation_state['last_prompt'] = "how_did_u_get_number"
        return PROMPTS["how_did_u_get_number"], 0, 0

    elif mapped_input == "on_disability":
        conversation_state['last_prompt'] = "on_disability"
        return PROMPTS["on_disability"], 0, 0

    elif mapped_input == "social":
        conversation_state['last_prompt'] = "social"
        return PROMPTS["social"], 0, 0

    elif mapped_input == "not_the_person":
        conversation_state['last_prompt'] = "not_the_person"
        return PROMPTS["not_the_person"], 0, 0

    elif mapped_input == "not_sure":
        conversation_state['step'] = "offer_transfer"
        conversation_state['last_prompt'] = "not_sure"
        return PROMPTS["not_sure"], 0, 0

    elif mapped_input == "this_is_business":
        conversation_state['last_prompt'] = "this_is_business"
        return PROMPTS["this_is_business"], 0, 0

    elif mapped_input == "what_is_this_about":
        conversation_state["last_prompt"] = "what_is_this_different"
        return PROMPTS["what_is_this_different"], 0, 0

    elif mapped_input == "are_you_computer":
        conversation_state['last_prompt'] = "are_you_computer"
        return PROMPTS["are_you_computer"], 0, 0

    elif mapped_input == "do_not_call":
        conversation_state['last_prompt'] = "do_not_call"
        return PROMPTS["do_not_call"], 0, 0

    elif mapped_input == "federal" or "both":
        conversation_state['last_prompt'] = "federal"
        logger.info(f"Triggering transfer for uuid={session_uuid}")
        return PROMPTS["federal"], 0, 1

    elif mapped_input == "state":
        conversation_state['step'] = "confirm_state"
        conversation_state['last_prompt'] = "state"
        return PROMPTS["state"], 0, 0

    if conversation_state['step'] == "greeting":
        if mapped_input == "yes":
            conversation_state['step'] = "tax_type"
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Transitioned to step 'tax_type' for uuid={session_uuid}")
            return PROMPTS["yes"], 0, 0
        elif mapped_input == "no":
            conversation_state['step'] = "confirm_no"
            conversation_state['last_prompt'] = "no"
            return PROMPTS["no"], 0, 0
        else:
            conversation_state['last_prompt'] = "something_different"
            return PROMPTS["something_different"], 0, 0

    elif conversation_state['step'] == "offer_transfer":
        if mapped_input == "yes":
            conversation_state['step'] = "tax_type"
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Transitioned to step 'tax_type' for uuid={session_uuid}")
            return PROMPTS["yes"], 0, 0
        elif mapped_input == "no":
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        else:
            conversation_state['last_prompt'] = "something_else"
            return PROMPTS["something_else"], 0, 0

    elif conversation_state['step'] == "tax_type":
        if mapped_input == "yes":
            conversation_state['step'] = "tax_type"
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Repeating tax_type prompt for uuid={session_uuid}")
            return PROMPTS["yes"], 0, 0
        elif mapped_input == "no":
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        else:
            conversation_state['last_prompt'] = "something_else"
            return PROMPTS["something_else"], 0, 0

    elif conversation_state['step'] == "confirm_no":
        if mapped_input == "yes":  # User confirms no federal tax debt
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        elif mapped_input == "no":  # User indicates they might have federal tax debt
            conversation_state['step'] = "tax_type"
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Transitioned to step 'tax_type' for uuid={session_uuid}")
            return PROMPTS["yes"], 0, 0
        elif mapped_input == "":  # Handle silence
            conversation_state['repeat_count'] += 1
            if conversation_state['repeat_count'] >= 2:
                logger.info(f"Ending call for uuid={session_uuid} due to repeated silence")
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            return PROMPTS[conversation_state['last_prompt']], 0, 0
        else:  # Handle unrecognized input
            conversation_state['last_prompt'] = "something_else"
            return PROMPTS["something_else"], 0, 0

    elif conversation_state['step'] == "confirm_state":
        if mapped_input == "yes":
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        elif mapped_input == "no":
            if conversation_state['input_counts'].get('federal', 0) >= 1:
                logger.info(f"Ending call for uuid={session_uuid} due to repeated 'federal' input after 'state'")
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "federal"
            logger.info(f"Triggering transfer for uuid={session_uuid}")
            return PROMPTS["federal"], 0, 1
        else:
            conversation_state['last_prompt'] = "something_else"
            return PROMPTS["something_else"], 0, 0

    conversation_state['last_prompt'] = "something_else"
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
        if not data or 'text' not in data or 'uuid' not in data or 'number' not in data:
            logger.error("Missing text, uuid, or number in the request")
            return jsonify({'error': 'Missing text, uuid, or number in the request'}), 400

        user_input = data['text'].strip()
        session_uuid = data['uuid']
        phone_number = data['number']

        if not user_input or not session_uuid or not phone_number:
            logger.error("Empty text, uuid, or phone number provided")
            save_log_to_db(
                uuid=session_uuid,
                request_text=user_input or "Empty input",
                number=phone_number,
                end=0,
                transfer=0
            )
            return jsonify({'error': 'Empty text, uuid, or number provided'}), 400

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

# Retrieve logs
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
