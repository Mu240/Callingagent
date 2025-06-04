from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import openai
import requests
import base64
import os
import io

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = '123456'
CORS(app)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))

# Debug environment variables
print(f"Loaded OPENAI_API_KEY: {OPENAI_API_KEY[:4]}...")  # Partial for security
print(f"Loaded ELEVENLABS_API_KEY: {ELEVENLABS_API_KEY[:4]}...")

openai.api_key = OPENAI_API_KEY

# Store conversation states for each session
conversation_states = {}

def get_conversation_state(session_id):
    if session_id not in conversation_states:
        conversation_states[session_id] = {
            "step": "greeting",
            "something_else_count": 0,
            "contact_requested": False,
            "contact_details": {"name": None, "email": None, "phone": None},
        }
    return conversation_states[session_id]

def reset_conversation_state(session_id):
    conversation_states[session_id] = {
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
            print(f"Audio generated successfully for text: '{text}'")
            return response.content  # Return raw bytes for flexibility
        else:
            print(f"ElevenLabs API error: Status {response.status_code}, Response: {response.text}")
            return None
    except Exception as e:
        print(f"Error in text_to_speech: {e}")
        return None

def query_openai(user_input, conversation_state):
    prompt = f"""
You are an AI assistant handling inquiries about federal tax debt. Respond naturally and politely to the user's query, staying within the context of tax debt or missed filings. If the query is unrelated, gently steer the conversation back to the tax debt question. Do not invent specific details about tax laws or financial advice unless explicitly provided. If the user asks for a callback or transfer, guide them to provide contact details.

**User Query**:
{user_input}

**Conversation State**:
Step: {conversation_state['step']}
Something Else Count: {conversation_state['something_else_count']}

Provide the response text only.
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

def process_user_input(user_input, session_id):
    conversation_state = get_conversation_state(session_id)
    
    # List of common greetings
    greetings = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
    
    # List of common goodbye phrases, including misspellings
    goodbyes = ['good bye', 'bye', 'thanks a lot', 'thank you', 'see you', 'thanks', 'thnask', 'thnx', 'thank', 'by']
    
    # Check for closing statements
    if any(phrase in user_input.lower() for phrase in goodbyes):
        response_text = "Thanks a lot! If you need any help, feel free to contact."
        reset_conversation_state(session_id)
    # Check for greetings
    elif any(greeting in user_input.lower() for greeting in greetings):
        conversation_state['step'] = 'tax_debt'
        response_text = ask_tax_debt_question()
    # Handle tax debt question flow
    else:
        if conversation_state['step'] == 'greeting':
            conversation_state['step'] = 'tax_debt'
            response_text = ask_tax_debt_question()
        elif conversation_state['step'] == 'tax_debt':
            if 'yes' in user_input.lower():
                if 'call me back' in user_input.lower():
                    conversation_state['contact_requested'] = True
                    conversation_state['step'] = 'collect_name'
                    response_text = "Sure, I can arrange for someone to call you back. Could you please tell me your name?"
                else:
                    conversation_state['contact_requested'] = True
                    conversation_state['step'] = 'collect_name'
                    response_text = "Thank you for letting me know. I'll transfer you to our team. Could you please provide your name?"
            elif 'no' in user_input.lower():
                if 'do not call' in user_input.lower() or 'dnc' in user_input.lower():
                    response_text = "Yes, I will add you to our Do Not Call list now, but are you sure you don't have a tax debt?"
                    conversation_state['step'] = 'confirm_no'
                else:
                    response_text = "Not a problem, but before I let you go, are you sure you don't have a tax debt?"
                    conversation_state['step'] = 'confirm_no'
            else:  # Something else
                conversation_state['something_else_count'] += 1
                if conversation_state['something_else_count'] >= 2:
                    response_text = "I'm sorry, I couldn't understand your response. Thank you for your time! Goodbye!"
                    reset_conversation_state(session_id)
                else:
                    response_text = repeat_tax_debt_question()
        elif conversation_state['step'] == 'confirm_no':
            if 'yes' in user_input.lower() or 'sure' in user_input.lower():
                response_text = "Thank you for confirming. If you have any future tax-related questions, feel free to reach out. Goodbye!"
                reset_conversation_state(session_id)
            elif 'no' in user_input.lower():
                conversation_state['contact_requested'] = True
                conversation_state['step'] = 'collect_name'
                response_text = "Thank you for clarifying. I'll transfer you to our team. Could you please provide your name?"
            else:
                response_text = "I'm sorry, I didn't understand. Are you sure you don't have a tax debt? Please say 'yes' or 'no.'"
        elif conversation_state['contact_requested']:
            if conversation_state['step'] == 'collect_name':
                conversation_state['contact_details']['name'] = user_input
                conversation_state['step'] = 'collect_email'
                response_text = "Thank you! Could you please provide your email address?"
            elif conversation_state['step'] == 'collect_email':
                conversation_state['contact_details']['email'] = user_input
                conversation_state['step'] = 'collect_phone'
                response_text = "Great, now could you provide your phone number?"
            elif conversation_state['step'] == 'collect_phone':
                conversation_state['contact_details']['phone'] = user_input
                conversation_state['step'] = 'contact_complete'
                response_text = f"Thank you, {conversation_state['contact_details']['name']}! One of our team members will contact you soon. Is there anything else I can help you with?"
                conversation_state['contact_requested'] = False
            elif conversation_state['step'] == 'contact_complete':
                response_text = "We've got your details, and someone will reach out soon. Is there anything else I can assist you with?"
        else:
            response_text = query_openai(user_input, conversation_state)

    # Sample user response handling
    if user_input.lower() == "no, i don't have any tax debt":
        response_text = "Not a problem, but before I let you go, are you sure you don't have a tax debt?"
        conversation_state['step'] = 'confirm_no'

    return response_text

# Optional endpoint to return raw MP3 file
@app.route('/process_text_mp3', methods=['POST'])
def process_text_mp3():
    try:
        # Get JSON data from the API request
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'No text provided in the request'}), 400

        user_input = data['text'].lower()
        session_id = data.get('session_id', request.remote_addr)

        print(f"Processing text input: '{user_input}' from session {session_id}")

        # Process the text input using the existing logic
        response_text = process_user_input(user_input, session_id)

        # Convert the response text to audio (MP3)
        audio_content = text_to_speech(response_text)

        if audio_content is None:
            return jsonify({
                'response': response_text,
                'error': 'Failed to generate audio response'
            }), 500

        # Return the raw MP3 file
        return send_file(
            io.BytesIO(audio_content),
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='response.mp3'
        )
    except Exception as e:
        print(f"Error processing text: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print(f"Starting Tax Debt Assistant API...")
    app.run(debug=True, host=HOST, port=PORT)
