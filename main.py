from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit
import openai
import requests
import base64
import json
import wave
import vosk
import os
import subprocess
import tempfile
from flask_cors import CORS
from dotenv import load_dotenv
import uuid

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = '123456'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "replace_it_with_your_path")

openai.api_key = OPENAI_API_KEY

# Initialize Vosk model
if not os.path.exists(VOSK_MODEL_PATH):
    print(f"Please download a Vosk model and extract it to {VOSK_MODEL_PATH}")
    print("You can download models from https://alphacephei.com/vosk/models")
    exit(1)

vosk_model = vosk.Model(VOSK_MODEL_PATH)

# Store recognizers and conversation states for each session
session_recognizers = {}
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

def get_recognizer(session_id):
    if session_id not in session_recognizers:
        session_recognizers[session_id] = vosk.KaldiRecognizer(vosk_model, 16000)
    return session_recognizers[session_id]

# Tax debt prompt
TAX_DEBT_PROMPT = """
Do you have a federal tax debt over five thousand dollars or any missed filings?
Please respond with 'yes,' 'no,' or something else.
"""

def convert_webm_to_pcm(webm_data):
    try:
        # Ensure webm_data is bytes
        if not isinstance(webm_data, bytes):
            print("Error: webm_data is not bytes")
            return None

        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_webm:
            temp_webm.write(webm_data)
            temp_webm.flush()  # Ensure data is written
            os.fsync(temp_webm.fileno())  # Force write to disk
            temp_webm_path = temp_webm.name

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav_path = temp_wav.name

        # FFmpeg command to convert WebM (Opus) to PCM WAV
        ffmpeg_cmd = [
            'ffmpeg', '-y',  # Overwrite output file
            '-i', temp_webm_path,  # Input file
            '-ar', '16000',  # Sample rate
            '-ac', '1',  # Mono channel
            '-c:a', 'pcm_s16le',  # PCM signed 16-bit little-endian
            '-f', 'wav',  # Output format
            '-vn',  # No video
            temp_wav_path  # Output file
        ]

        # Run FFmpeg with detailed error capture
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=15  # Increased timeout
        )

        if result.returncode == 0:
            # Verify WAV file format
            with wave.open(temp_wav_path, 'rb') as wav_file:
                if wav_file.getnchannels() != 1 or wav_file.getframerate() != 16000 or wav_file.getsampwidth() != 2:
                    print(f"Warning: WAV file format mismatch - Channels: {wav_file.getnchannels()}, Sample Rate: {wav_file.getframerate()}, Sample Width: {wav_file.getsampwidth()}")
                    return None
                frames = wav_file.readframes(wav_file.getnframes())
            print(f"Successfully converted audio: {len(frames)} bytes")
            return frames
        else:
            print(f"FFmpeg error: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print("FFmpeg conversion timed out")
        return None
    except Exception as e:
        print(f"Error converting audio: {e}")
        return None
    finally:
        # Clean up temporary files
        try:
            if 'temp_webm_path' in locals() and os.path.exists(temp_webm_path):
                os.unlink(temp_webm_path)
            if 'temp_wav_path' in locals() and os.path.exists(temp_wav_path):
                os.unlink(temp_wav_path)
        except Exception as e:
            print(f"Error cleaning up temp files: {e}")

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
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        return base64.b64encode(response.content).decode('utf-8')
    return ""

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

    # Check for closing statements
    if any(phrase in user_input.lower() for phrase in ['good bye', 'bye', 'thanks a lot', 'thank you', 'see you']):
        response_text = "Thank you for your time! Goodbye!"
        reset_conversation_state(session_id)
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

@app.route('/')
def index():
    greeting_text = TAX_DEBT_PROMPT
    greeting_audio = text_to_speech(greeting_text)

    html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Tax Debt Assistant with Vosk</title>
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
        #transcript {{
            display: none;
        }}
        audio {{
            margin-top: 20px;
        }}
        .debug {{
            display: none;
        }}
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
</head>
<body>
    <div class="container">
        <h1>Tax Debt AI Assistant (Vosk + WebSocket)</h1>
        <p>Welcome! I'm here to assist you with questions about federal tax debt. Click 'Start Talking' to begin.</p>
        <button id="startBtn" onclick="startRecognition()">Start Talking</button>
        <button id="stopBtn" onclick="stopRecognition()" disabled>Stop Talking</button>
        <div id="status">Click 'Start Talking' to begin</div>
        <div id="transcript">Recognized speech will appear here...</div>
        <div id="debug" class="debug">Debug info will appear here...</div>
        <audio id="responseAudio" autoplay></audio>
    </div>

    <script>
        const socket = io();
        let mediaRecorder;
        let isRecording = false;
        let isSpeaking = false;
        let stream;
        let audioChunks = [];

        const status = document.getElementById('status');
        const transcript = document.getElementById('transcript');
        const debug = document.getElementById('debug');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const audio = document.getElementById('responseAudio');

        socket.on('connect', function() {{
            console.log('Connected to server');
            debug.innerText = 'Connected to server';
        }});

        socket.on('transcription', function(data) {{
            console.log('Transcription received:', data);
            debug.innerText = `Transcription: Final=${{data.final}}, Text="${{data.text}}"`;

            if (data.text) {{
                transcript.innerText = data.text;
            }}

            if (data.final && data.text.trim()) {{
                processTranscription(data.text);
            }}
        }});

        socket.on('response', function(data) {{
            console.log('Response received:', data.response);
            status.innerText = 'Speaking...';
            isSpeaking = true;
            audio.src = 'data:audio/mp3;base64,' + data.audio;
            audio.play();

            if (data.response.includes('Goodbye') || data.response.includes('Thank you for your time')) {{
                setTimeout(() => {{
                    stopRecognition();
                }}, 3000);
            }}
        }});

        audio.onended = function() {{
            isSpeaking = false;
            if (isRecording) {{
                status.innerText = 'Listening...';
                startListening();
            }}
        }};

        function processTranscription(text) {{
            if (text.trim()) {{
                stopListening();
                status.innerText = 'Processing...';
                socket.emit('process_speech', {{'text': text}});
            }}
        }}

        function startListening() {{
            if (!isSpeaking && isRecording && stream) {{
                try {{
                    audioChunks = []; // Reset chunks
                    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
                    mediaRecorder = new MediaRecorder(stream, {{ mimeType }});

                    mediaRecorder.ondataavailable = function(event) {{
                        if (event.data.size > 0) {{
                            console.log('Audio data available:', event.data.size, 'bytes');
                            debug.innerText = `Audio chunk: ${{event.data.size}} bytes`;
                            audioChunks.push(event.data);
                        }}
                    }};

                    mediaRecorder.onstop = function() {{
                        if (audioChunks.length > 0) {{
                            const audioBlob = new Blob(audioChunks, {{ type: mimeType }});
                            console.log('Audio blob created:', audioBlob.size, 'bytes');
                            debug.innerText = `Audio blob: ${{audioBlob.size}} bytes`;

                            // Log first few bytes for debugging
                            audioBlob.arrayBuffer().then(buffer => {{
                                const byteArray = new Uint8Array(buffer.slice(0, 10));
                                console.log('First 10 bytes:', byteArray);
                                debug.innerText += `\nFirst 10 bytes: ${{byteArray}}`;

                                const reader = new FileReader();
                                reader.onload = function() {{
                                    socket.emit('audio_data', reader.result);
                                }};
                                reader.readAsArrayBuffer(audioBlob);
                            }});
                        }}
                    }};

                    mediaRecorder.start(1000); // Increased to 1s for more complete chunks
                    status.innerText = 'Listening...';

                    setTimeout(() => {{
                        if (mediaRecorder && mediaRecorder.state === 'recording') {{
                            mediaRecorder.stop();
                        }}
                    }}, 10000); // 10s recording window

                }} catch (error) {{
                    console.error('Error starting MediaRecorder:', error);
                    debug.innerText = 'Error: ' + error.message;
                }}
            }}
        }}

        function stopListening() {{
            if (mediaRecorder && mediaRecorder.state === 'recording') {{
                mediaRecorder.stop();
            }}
        }}

        async function startRecognition() {{
            if (!isRecording) {{
                try {{
                    stream = await navigator.mediaDevices.getUserMedia({{ 
                        audio: {{
                            sampleRate: 16000,
                            channelCount: 1,
                            echoCancellation: true,
                            noiseSuppression: true
                        }}
                    }});

                    isRecording = true;
                    startBtn.disabled = true;
                    stopBtn.disabled = false;

                    isSpeaking = true;
                    status.innerText = 'Speaking...';
                    audio.src = 'data:audio/mp3;base64,{greeting_audio}';
                    audio.play();

                }} catch (error) {{
                    console.error('Error accessing microphone:', error);
                    status.innerText = 'Error: Could not access microphone';
                    debug.innerText = 'Microphone error: ' + error.message;
                }}
            }}
        }}

        function stopRecognition() {{
            if (isRecording) {{
                isRecording = false;
                isSpeaking = false;

                stopListening();

                if (stream) {{
                    stream.getTracks().forEach(track => track.stop());
                    stream = null;
                }}

                startBtn.disabled = false;
                stopBtn.disabled = true;
                status.innerText = "Click 'Start Talking' to begin";
                transcript.innerText = "Recognized speech will appear here...";
                debug.innerText = "Debug info will appear here...";
            }}
        }}
    </script>
</body>
</html>
    """
    return html_template

@socketio.on('audio_data')
def handle_audio_data(audio_data):
    try:
        session_id = request.sid
        print(f"Received audio data: {len(audio_data)} bytes from session {session_id}")

        # Ensure audio_data is bytes
        if isinstance(audio_data, str):
            print("Audio data is string, attempting to decode...")
            audio_data = base64.b64decode(audio_data.split(',')[1] if ',' in audio_data else audio_data)

        # Convert WebM audio to PCM format
        pcm_data = convert_webm_to_pcm(audio_data)

        if pcm_data:
            rec = get_recognizer(session_id)

            # Process audio with Vosk
            if rec.AcceptWaveform(pcm_data):
                result = json.loads(rec.Result())
                print(f"Final result: {result}")
                if result.get('text'):
                    emit('transcription', {'text': result['text'], 'final': True})
            else:
                partial_result = json.loads(rec.PartialResult())
                print(f"Partial result: {partial_result}")
                if partial_result.get('partial'):
                    emit('transcription', {'text': partial_result['partial'], 'final': False})
        else:
            print("Failed to convert audio data")
            emit('transcription', {'text': 'Audio conversion failed', 'final': False})

    except Exception as e:
        print(f"Error processing audio: {e}")
        emit('transcription', {'text': f'Error: {str(e)}', 'final': False})

@socketio.on('process_speech')
def handle_process_speech(data):
    user_input = data['text'].lower()
    session_id = request.sid

    print(f"Processing speech: '{user_input}' from session {session_id}")

    response_text = process_user_input(user_input, session_id)
    audio_base64 = text_to_speech(response_text)

    emit('response', {'response': response_text, 'audio': audio_base64})

@app.route('/process', methods=['POST'])
def process():
    user_input = request.json.get('text', '').lower()
    session_id = request.remote_addr

    response_text = process_user_input(user_input, session_id)
    audio_base64 = text_to_speech(response_text)

    return jsonify({'response': response_text, 'audio': audio_base64})

if __name__ == '__main__':
    print(f"Starting Tax Debt Assistant with Vosk and WebSocket...")
    print(f"Vosk model path: {VOSK_MODEL_PATH}")
    print("Make sure FFmpeg is installed and available in PATH for audio conversion")
    socketio.run(app, debug=True, host=HOST, port=PORT)
