from flask import Flask, request, jsonify
import openai
import requests
import base64
from datetime import datetime
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")  # Default to 0.0.0.0 if not specified
PORT = int(os.getenv("PORT", 5000))  # Default to 5000 if not specified
openai.api_key = OPENAI_API_KEY

# Tax debt prompt
TAX_DEBT_PROMPT = """
Do you have a federal tax debt over five thousand dollars or any missed filings?
Please respond with 'yes,' 'no,' or something else.
"""

# Conversation state
conversation_state = {
    "step": "greeting",
    "something_else_count": 0,  # Track unclear responses
    "contact_requested": False,
    "contact_details": {"name": None, "email": None, "phone": None},
}

# Helper function to generate the initial tax debt question
def ask_tax_debt_question():
    return TAX_DEBT_PROMPT

# Helper function to repeat the tax debt question for unclear responses
def repeat_tax_debt_question():
    return "I am sorry, I didn’t understand. Let me repeat: Do you have a federal tax debt over five thousand dollars or any missed tax filings? Please respond with 'yes,' 'no,' or something else."

# Helper function for text-to-speech using ElevenLabs API
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
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        return base64.b64encode(response.content).decode('utf-8')
    return ""

# Helper function to query OpenAI for general responses
def query_openai(user_input):
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

@app.route('/')
def index():
    greeting_text = TAX_DEBT_PROMPT
    greeting_audio = text_to_speech(greeting_text)
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Tax Debt Assistant</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background-color: #f4f7fa;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            color: #333;
        }}
        .container {{
            background: #fff;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            max-width: 600px;
            width: 100%;
            text-align: center;
        }}
        h1 {{
            font-size: 28px;
            margin-bottom: 20px;
            color: #2c3e50;
        }}
        button {{
            padding: 12px 24px;
            font-size: 16px;
            margin: 10px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s, transform 0.2s;
        }}
        #startBtn {{
            background-color: #3498db;
            color: white;
        }}
        #startBtn:hover {{
            background-color: #2980b9;
            transform: scale(1.05);
        }}
        #stopBtn {{
            background-color: #e74c3c;
            color: white;
        }}
        #stopBtn:hover {{
            background-color: #c0392b;
            transform: scale(1.05);
        }}
        #stopBtn:disabled, #startBtn:disabled {{
            background-color: #ccc;
            cursor: not-allowed;
        }}
        #status {{
            margin-top: 20px;
            font-size: 18px;
            color: #555;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
        }}
        audio {{
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Tax Debt AI Assistant</h1>
        <p>Welcome! I'm here to assist you with questions about federal tax debt. Click 'Start Talking' to begin.</p>
        <button id="startBtn" onclick="startRecognition()">Start Talking</button>
        <button id="stopBtn" onclick="stopRecognition()" disabled>Stop Talking</button>
        <div id="status">Click 'Start Talking' to begin</div>
        <audio id="responseAudio" autoplay></audio>
    </div>
    <script>
        let recognition;
        let isRecognizing = false;
        let isSpeaking = false;

        if ('webkitSpeechRecognition' in window) {{
            recognition = new webkitSpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'en-US';
        }} else {{
            alert('Speech recognition not supported in this browser.');
        }}

        const audio = document.getElementById('responseAudio');
        const status = document.getElementById('status');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');

        function startListening() {{
            if (isRecognizing && !isSpeaking) {{
                recognition.start();
                status.innerText = 'Listening...';
            }}
        }}

        audio.onended = function() {{
            isSpeaking = false;
            startListening();
        }};

        recognition.onresult = function(event) {{
            let finalTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {{
                if (event.results[i].isFinal) {{
                    finalTranscript += event.results[i][0].transcript;
                }}
            }}
            if (finalTranscript) {{
                recognition.stop();
                isSpeaking = true;
                status.innerText = 'Speaking...';
                fetch('/process', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ text: finalTranscript }})
                }})
                .then(response => response.json())
                .then(data => {{
                    status.innerText = 'Speaking...';
                    audio.src = 'data:audio/mp3;base64,' + data.audio;
                    audio.play();
                    if (data.response.includes('Goodbye') || data.response.includes('Thank you for your time')) {{
                        stopRecognition();
                    }}
                }})
                .catch(error => {{
                    status.innerText = 'Error processing response';
                    isSpeaking = false;
                    startListening();
                }});
            }}
        }};

        recognition.onerror = function(event) {{
            if (event.error !== 'no-speech' && isRecognizing) {{
                status.innerText = 'Error: ' + event.error;
                startListening();
            }}
        }};

        recognition.onend = function() {{
            if (isRecognizing && !isSpeaking) {{
                startListening();
            }}
        }};

        function startRecognition() {{
            if (!isRecognizing) {{
                isRecognizing = true;
                startBtn.disabled = true;
                stopBtn.disabled = false;
                isSpeaking = true;
                status.innerText = 'Speaking...';
                audio.src = 'data:audio/mp3;base64,{greeting_audio}';
                audio.play();
            }}
        }}

        function stopRecognition() {{
            if (isRecognizing) {{
                isRecognizing = false;
                isSpeaking = false;
                recognition.stop();
                startBtn.disabled = false;
                stopBtn.disabled = true;
                status.innerText = "Click 'Start Talking' to begin";
            }}
        }}
    </script>
</body>
</html>
    """

@app.route('/process', methods=['POST'])
def process():
    user_input = request.json.get('text', '').lower()
    global conversation_state

    # Check for closing statements
    if any(phrase in user_input for phrase in ['good bye', 'bye', 'thanks a lot', 'thank you', 'see you']):
        response_text = "Thank you for your time! Goodbye!"
        # Reset conversation state
        conversation_state.update({
            "step": "greeting",
            "something_else_count": 0,
            "contact_requested": False,
            "contact_details": {"name": None, "email": None, "phone": None}
        })
    # Handle tax debt question flow
    else:
        if conversation_state['step'] == 'greeting':
            conversation_state['step'] = 'tax_debt'
            response_text = ask_tax_debt_question()
        elif conversation_state['step'] == 'tax_debt':
            if 'yes' in user_input:
                if 'call me back' in user_input:
                    conversation_state['contact_requested'] = True
                    conversation_state['step'] = 'collect_name'
                    response_text = "Sure, I can arrange for someone to call you back. Could you please tell me your name?"
                else:
                    conversation_state['contact_requested'] = True
                    conversation_state['step'] = 'collect_name'
                    response_text = "Thank you for letting me know. I’ll transfer you to our team. Could you please provide your name?"
            elif 'no' in user_input:
                if 'do not call' in user_input or 'dnc' in user_input:
                    response_text = "Yes, I will add you to our Do Not Call list now, but are you sure you don’t have a tax debt?"
                    conversation_state['step'] = 'confirm_no'
                else:
                    response_text = "Not a problem, but before I let you go, are you sure you don’t have a tax debt?"
                    conversation_state['step'] = 'confirm_no'
            else:  # Something else
                conversation_state['something_else_count'] += 1
                if conversation_state['something_else_count'] >= 2:
                    response_text = "I’m sorry, I couldn’t understand your response. Thank you for your time! Goodbye!"
                    conversation_state.update({
                        "step": "greeting",
                        "something_else_count": 0,
                        "contact_requested": False,
                        "contact_details": {"name": None, "email": None, "phone": None}
                    })
                else:
                    response_text = repeat_tax_debt_question()
        elif conversation_state['step'] == 'confirm_no':
            if 'yes' in user_input or 'sure' in user_input:
                response_text = "Thank you for confirming. If you have any future tax-related questions, feel free to reach out. Goodbye!"
                conversation_state.update({
                    "step": "greeting",
                    "something_else_count": 0,
                    "contact_requested": False,
                    "contact_details": {"name": None, "email": None, "phone": None}
                })
            elif 'no' in user_input:
                conversation_state['contact_requested'] = True
                conversation_state['step'] = 'collect_name'
                response_text = "Thank you for clarifying. I’ll transfer you to our team. Could you please provide your name?"
            else:
                response_text = "I’m sorry, I didn’t understand. Are you sure you don’t have a tax debt? Please say 'yes' or 'no.'"
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
                response_text = "We’ve got your details, and someone will reach out soon. Is there anything else I can assist you with?"
        else:
            response_text = query_openai(user_input)

    # Sample user response handling
    if user_input == "no, i don’t have any tax debt":
        response_text = "Not a problem, but before I let you go, are you sure you don’t have a tax debt?"
        conversation_state['step'] = 'confirm_no'

    audio_base64 = text_to_speech(response_text)
    return jsonify({'response': response_text, 'audio': audio_base64})

if __name__ == '__main__':
    app.run(debug=True, host=HOST, port=PORT)