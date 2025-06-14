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
            "specific_repeat_count": {"who_are_you": 0, "what_did_you_say": 0, "something_different": 0, "not_the_person": 0},
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
        "specific_repeat_count": {"who_are_you": 0, "what_did_you_say": 0, "something_different": 0, "not_the_person": 0},
        "input_counts": {}
    }
    logger.info(f"Reset conversation state for uuid={session_uuid}")

# Input mappings for user input variations
input_mappings = {
    "greeting": ["hi", "hello", "start", "begin"],
    "who_are_you": ["who are you", "who is this", "who's calling", "who are u"],
    "what_did_you_say": ["what did you say", "repeat", "say again", "what was that", "huh"],
    "never_owed": ["i have never owed", "never owed", "no debt", "don’t owe", "never had debt", "owe"],
    "how_did_u_get_number": ["number", "how did u get my number", "where did you get my number",
                             "how’d you get my phone", "who gave you my number", "where’s my number from"],
    "on_disability": ["disable", "i am on disability", "on disability", "i’m disabled", "disability benefits"],
    "social": ["social", "social security", "i am on social security", "on social security", "social benefits"],
    "not_sure": ["not sure", "i dont know", "don’t know", "unsure", "maybe", "know","i’m not sure", "i’m not sher", "i’m not sho", "ahm not sure", "m’not sure","i’m nah shur", "um not sher", "a’m not shuh", "i’m not shoer", "i’m notchur","ahnah sher", "i have no idea", "i’ve no idea", "i got no idea","i ain’t got no idea", "i havena idea", "i got no idear", "i dun have no idea","i ain’t got a clue", "i g’nno idea", "i h’no idea", "i’nno idea", "no clue","nuh clue", "‘no clue", "no’ clue", "noo clue", "nuh-kloo", "nuh cloo","nuhkluh", "n’ clue", "nuhclue", "kno clue", "beats me", "b’s me", "bees me","beats meh", "beats’m", "b’tz me", "beat’sme", "b’tzmeh", "b’z meh","beatsmee", "b'me", "not certain", "not surrin", "not suttin", "noss’rn","not sur’n", "notsh’n", "naht surrin", "naa sur’n", "nod certain","n’t certain", "notsuh’n", "i’m unsure", "i’m unshur", "um unsure","i’m unsher", "ahm unshurr", "am uhnsure", "i’m ‘nshur", "i’m unshuh","um’nshur", "i’m uhnsur", "i’m shurn’t", "i’m in the dark", "i’m’n the dark","iminna dark", "i’m in th’ dark", "i’m’n duh dark", "um’n the dark","i’m ‘n thuh dark", "ah’m inna dark", "imin dark", "i’m in’dark","m’in the dark", "i haven’t looked into it", "haven’t looked inna it","i hav’n’t looked intuh it", "i ain’t looked into it", "haven’ looked’n’tuh it","i haven’t looked’nit", "i have’ looked in tuh it", "i haven’t lookedin it","i h’nt looked ‘t it", "ahven’t looked’n’tuhit", "i ain’t done that yet","i don’t have that information", "i don’ have that info", "i don’t got that info","i d’n have that ‘nfo", "i don’ have tha’ information", "i d’n’t have that info","i dun have dat info", "i don’ got no info", "i don’t have ‘formation","i d’no that info", "i don’t have it on me", "i haven’t the faintest idea","i haven’t the faintest idear", "i haven’t th’ faintest idea","i haven’t got the faintest idea", "i ain’t got the faintest idea","i havn’t the faintest ideuh", "i haven’t the faint’st idear","i haven’ the faintest idear", "i h’ven’t the faintest idea","i haven’t the faint’est idear", "i haven’t the foggiest", "i’m not aware","i’m not ‘ware", "i’m nah aware", "i’m not a-wurr", "i’m not uh-where","i’m naht aware", "um not ‘ware", "i’m not awair", "i’m not aweh","i’m not aw’r", "m’not aware", "i can’t say", "i can’ say", "i cain’t say","i ken’ say", "i can say", "i can’ tell", "i can’ really say", "i can’ say f’sure", "i c’n’t say", "i c’n say", "i cain say", "it’s unclear to me", "it’s un-clear t’me", "it’s unclear ta me","it’s unclear tuh meh", "s’unclear to me", "iss unclear t’meh","it’s uh-clear tuh me", "it’s unclear d’me", "it unclear to me","it’s un-clear tuh meh", "izz unclear t’me", "don’t have a clue","don’t havva clue", "don’ have a clue", "don’ got a clue", "don’t got no clue","don’ have uh clue", "don’ hav a kloo", "d’n’ have a clue", "don’t got clue","don’t ‘ave a clue", "don’ have nuh clue", "i’m not informed","i’m not ‘nformed", "i’m nah informed", "um not informed","i’m not in-fawmd", "i’m notnformed", "i’m not’nformed", "i’m not up on it","i’m not told", "i’m not been told", "i’m not in the know","your guess is as good as mine", "yer guess is good as mine","yo’ guess is good as mine", "your guess’s good’z mine","yer guess good’s mine", "yuh guess is good as mine", "y’guess’s good as mine","guess good as mine", "yer guess’z good’n mine", "yo guess as good’s mine","ya guess’s good as mine", "haven’t got a clue", "ain’t got a clue","haven’t gotta clue", "hav’na clue", "haven’ got nuh clue", "i haven’t a clue","haven’ got n’ clue", "havn’t got a kloo", "haven’t got no clue","ain’ got a clue", "i’m not positive", "i’m not pawz’tiv", "i’m not pahzuhdiv","i’m not pos’dihv", "i’m not real sure", "i’m not sure ‘bout that","i’m not 100%", "um not positive", "i’m not pos’tive", "i’m not p’sitive","i’ll have to find out", "i’ll hafta find out", "i’ll have da find out","i’ll haf’tuh find out", "i’ll have tuh find out", "i’ll have t’find out","i’ll ‘av ta find out", "ah’ll haft find out", "i’ll ‘ave to find out","i’ll ‘aveta find out", "i’ll ‘ave tuh fine out", "i haven’t been told","i haven’t bin told", "i ain’t been told", "i haven’ been told","i haven’t been tole", "i h’n’t been told", "i haven’t been tol’","i hav’nt bin told", "i haven’t heard", "i h’ven’t been told","i ain’t heard nothin’", "i’m not familiar with that", "i’m not fam’liar with that","i’m not f’milyuh with that", "i’m not familiar wit dat","i’m not ‘miliar with that", "i’m not fuhmilyuh wit that","i’m not femilyer with that", "i’m not familiar wif dat","i’m not familar wit that", "i’m not f’miluh with that","um not familiar with that", "i’m drawing a blank", "i’m drawin’ a blank","i’m draw’n a blank", "i’m draw’na blank", "i’m dron’uh blank","i’m draw’n blank", "i’m drawin’ blank", "i’m drahn a blank", "um drawin’ a blank", "i’m dro’in a blank", "m’drawin’ a blank","that’s beyond me", "that’s b’yawn me", "that’s b’yund me", "thas b’yond me","das b’yawn’d me", "thass bee-yawn me", "that’s b’yond meh","thaz beyond me", "dat’s beyond me", "that’s b’yan’ me", "that’s be’on me","i’m stumped", "i’m stumpt", "i’m stum’d", "um stumped", "i’m stuhmpt","i’mstumped", "i’m all stumped", "i’m totally stumped", "i’m just stumped","i’m stuhmp’d", "m’stumped", "i dunno", "dunno", "i ‘unno", "i ono","ionno", "idano", "ahno", "ina’no", "i dono", "ahdunno", "i’no", "anow","ahno’", "i d’know", "iono", "ain’t know", "d’nno", "dno", "ainno","idn’t know"],
    "this_is_business": ["business", "this is a business", "business line", "company phone", "not personal"],
    "what_is_this_about": ["what is this about", "what’s this for", "why are you calling", "what do you want"],
    "are_you_computer": ["real person", "computer", "are you a computer", "are you a real person", "is this a bot",
                         "are you ai", "robot"],
    "do_not_call": ["put","list","put me on your do not call list", "do not call", "don’t call me", "stop calling",
                    "no calls"],
    "not_a_problem": ["call","do not call me anymore", "do not call me again", "stop calling me"],
    "yes": ["yes", "yeah", "yep", "sure", "okay", "ok", "yup", "aye", "affirmative", "certainly", "of course", "definitely", "absolutely", "indeed", "sure thing", "you bet", "for sure", "by all means", "without a doubt", "I agree", "that’s right", "right on", "roger that", "true", "uh-huh", "totally", "okie-dokie", "for real", "probably", "I guess so", "seems like it", "looks that way", "sounds about right", "could be", "I’d say so", "I suppose", "I figure", "most likely", "I reckon", "I believe so", "I assume so", "it seems so", "I would think so", "I’d imagine", "I’d expect so", "as far as I know", "from what I can tell", "it appears that way", "I presume so", "to the best of my knowledge", "evidently", "apparently so", "that seems to be the case", "I do", "no doubt", "yep, absolutely", "you know it", "yep, for sure", "sure enough", "I do indeed", "I certainly do", "most certainly", "I can confirm that","I think so"],
    "no": ["no", "nope", "not really", "nah", "no way", "nay", "negative", "not at all", "absolutely not", "never", "not quite", "I don’t think so", "I’m afraid not", "regrettably not", "unfortunately not", "by no means", "out of the question", "nothing doing", "not happening", "no can do", "certainly not", "over my dead body", "count me out", "I’ll pass", "no siree", "not in a million years"],
    "something_else": []
}

# List of common words to remove
STOP_WORDS = {}

# Prompts for responses
PROMPTS = {
    "greeting": "Hi, my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns? Please answer yes or know or I don’t know",
    "who_are_you": "Hi, my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "what_did_you_say": "Hi, my name is Michele with Tax Group. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "end_call": "Thank you for your time, unfortunately we are not able to help you at this time.",
    "transfer": "Please wait and the next available live agent will answer the call.",
    "never_owed": "We can only help you if you have a tax debt or unfiled tax returns. Thank you for your time. Before I go, are you sure you don’t have a tax debt or unfiled tax returns?",
    "how_did_u_get_number": "Not sure, but do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "on_disability": "We can help you. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "social": "We can help you. Do you have a tax debt of five thousand dollars or unfiled tax returns?",
    "not_sure": "If you’d like to check, I can transfer you to a live agent now. Would you like to see if you have any unresolved tax issues? please answer yes or no only.",
    "not_sure_tax_type": "Please wait and the next available live agent will answer the call.",
    "this_is_business": "Certainly, and sorry for the call. But before I go, do you personally have any missed tax filings or owe more than five thousand dollars in taxes?",
    "what_is_this_about": "We help people with tax debts or past unfiled taxes.",
    "are_you_computer": "I am an AI Virtual Assistant. Do you personally have any missed tax filings or owe more than five thousand dollars in taxes?",
    "do_not_call": "I would be happy to do that, but before I go, do you personally have any missed tax filings or owe more than five thousand dollars in taxes?",
    "not_a_problem": "Not a problem I will put you on our Do Not call list but before I go do you personally have any missed tax filings or owe more than Five Thousand dollars in taxes?",
    "something_different": "I am sorry I did not understand, Do you personally have any tax filing you have missed or do you owe more than five thousand dollars in taxes? Please answer yes, no or I don’t know only.",
    "yes": "Ok let me transfer you to a live agent.",
    "no": "We can only help you if you have a tax debt or unfiled tax returns. Thank you for your time. Before I go, let me ask you one more time, do you owe more than five thousand in back taxes or have any unfiled back taxes? Please answer yes, no or I dont know.",
    "something_else": "I am sorry I did not understand, Do you personally have any tax filing you have missed or do you owe more than five thousand dollars in taxes? Please answer yes, no or I don’t know only."
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
    filtered_words = [word for word in words if word not in STOP_WORDS]

    if not filtered_words:
        return "something_else"

    filtered_input = " ".join(filtered_words)

    # Check for exact phrase matches first
    for key, phrases in input_mappings.items():
        for phrase in phrases:
            if user_input_lower == phrase:  # Exact match before filtering
                return key

    # Check for filtered input matches
    for key, phrases in input_mappings.items():
        for phrase in phrases:
            phrase_words = phrase.split()
            filtered_phrase_words = [word for word in phrase_words if word not in STOP_WORDS]
            filtered_phrase = " ".join(filtered_phrase_words)

            if filtered_input == filtered_phrase:
                return key

            if filtered_phrase and filtered_phrase in filtered_input:
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
    # End call if any input (except "yes" and "not_sure") is repeated twice
    if mapped_input not in ["yes", "not_sure"] and conversation_state['input_counts'][mapped_input] >= 2:
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

    # Handle specific inputs explicitly
    if mapped_input == "greeting":
        conversation_state['last_prompt'] = "greeting"
        conversation_state['step'] = "greeting"
        return PROMPTS["greeting"], 0, 0
    elif mapped_input == "who_are_you":
        conversation_state['last_prompt'] = "who_are_you"
        return PROMPTS["who_are_you"], 0, 0
    elif mapped_input == "what_did_you_say":
        conversation_state['last_prompt'] = "what_did_you_say"
        return PROMPTS["what_did_you_say"], 0, 0
    elif mapped_input == "never_owed":
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
    elif mapped_input == "not_sure":
        if conversation_state['step'] == "tax_type":
            conversation_state['last_prompt'] = "not_sure_tax_type"
            logger.info(f"Triggering transfer for uuid={session_uuid} due to 'not_sure' in tax_type step")
            return PROMPTS["not_sure_tax_type"], 0, 1
        else:
            conversation_state['step'] = "offer_transfer"
            conversation_state['last_prompt'] = "not_sure"
            return PROMPTS["not_sure"], 0, 0
    elif mapped_input == "this_is_business":
        conversation_state['last_prompt'] = "this_is_business"
        return PROMPTS["this_is_business"], 0, 0
    elif mapped_input == "what_is_this_about":
        conversation_state["last_prompt"] = "what_is_this_about"
        return PROMPTS["what_is_this_about"], 0, 0
    elif mapped_input == "are_you_computer":
        conversation_state['last_prompt'] = "are_you_computer"
        return PROMPTS["are_you_computer"], 0, 0
    elif mapped_input == "do_not_call":
        conversation_state['last_prompt'] = "do_not_call"
        return PROMPTS["do_not_call"], 0, 0
    elif mapped_input == "not_a_problem":
        conversation_state['last_prompt'] = "not_a_problem"
        return PROMPTS["not_a_problem"], 0, 0

    # Handle conversation steps
    if conversation_state['step'] == "greeting":
        if mapped_input == "yes":
            conversation_state['step'] = "tax_type"
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Transitioned to step 'tax_type' for uuid={session_uuid}")
            return PROMPTS["yes"], 0, 1
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
            return PROMPTS["yes"], 0, 1
        elif mapped_input == "no":
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        else:
            conversation_state['last_prompt'] = "something_else"
            return PROMPTS["something_else"], 0, 0

    elif conversation_state['step'] == "tax_type":
        if mapped_input == "yes":
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Triggering transfer for uuid={session_uuid} due to 'yes' in tax_type step")
            return PROMPTS["yes"], 0, 1
        elif mapped_input == "no":
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        else:
            conversation_state['last_prompt'] = "something_else"
            return PROMPTS["something_else"], 0, 0

    elif conversation_state['step'] == "confirm_no":
        if mapped_input == "yes":
            reset_conversation_state(session_uuid)
            conversation_state['last_prompt'] = "end_call"
            return PROMPTS["end_call"], 1, 0
        elif mapped_input == "no":
            conversation_state['step'] = "tax_type"
            conversation_state['last_prompt'] = "yes"
            logger.info(f"Transitioned to step 'tax_type' for uuid={session_uuid}")
            return PROMPTS["yes"], 0, 1
        elif mapped_input == "":
            conversation_state['repeat_count'] += 1
            if conversation_state['repeat_count'] >= 2:
                logger.info(f"Ending call for uuid={session_uuid} due to repeated silence")
                reset_conversation_state(session_uuid)
                return PROMPTS["end_call"], 1, 0
            return PROMPTS[conversation_state['last_prompt']], 0, 0
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
