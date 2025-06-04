# Tax Debt AI Assistant with Vosk and WebSocket

## Overview

This is a Flask-based web application integrated with SocketIO, designed to provide an interactive AI assistant for handling federal tax debt inquiries. It uses the Vosk speech recognition model for real-time speech-to-text, processes user input with OpenAI's GPT-4, and responds via text-to-speech using the ElevenLabs API. The application manages a conversation flow to assess tax debt over $5,000 or missed filings, collects contact details for follow-ups, and supports WebSocket for real-time audio and response handling.

## Features

- **Speech Recognition**: Uses the Vosk model for offline, server-side speech-to-text from browser-captured audio (WebM format).
- **Text-to-Speech**: Converts AI responses to audio via the ElevenLabs API.
- **WebSocket Support**: Real-time audio data transmission and response delivery using Flask-SocketIO.
- **Conversation Flow**: Guides users through states (greeting, tax debt, contact collection) based on responses like "yes," "no," or other inputs.
- **Contact Collection**: Gathers name, email, and phone for follow-up when tax debt is confirmed.
- **Environment Variables**: Securely stores API keys, host, port, and Vosk model path in a `.env` file.
- **CORS Support**: Enables cross-origin requests for web compatibility.

## Prerequisites

- Python 3.8+
- A modern web browser (e.g., Google Chrome) with microphone access
- Internet access for OpenAI and ElevenLabs API calls
- FFmpeg installed and available in system PATH for audio conversion (WebM to PCM WAV)
- A valid `.env` file with API keys and configuration
- A `requirements.txt` file with dependencies
- Vosk model downloaded and extracted (e.g., `vosk-model-en-us-0.42-gigaspeech`)

## Setup and Installation

### Step 1: Clone the Repository

Clone or download the project to your local machine:

```bash
git clone <repository-url>
cd <repository-directory>
```

### Step 2: Set Up a Python Virtual Environment

Isolate dependencies to avoid conflicts:

1. **Create a Virtual Environment**:
   - On Windows:
     ```bash
     python -m venv venv
     ```
   - On macOS/Linux:
     ```bash
     python3 -m venv venv
     ```

2. **Activate the Virtual Environment**:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```
   Your terminal prompt should reflect the active environment (e.g., `(venv) $`).

### Step 3: Install Dependencies

With the virtual environment activated, install required packages:

```bash
pip install -r requirements.txt
```

The `requirements.txt` file should include:

```
flask
flask-socketio
python-dotenv
openai
requests
vosk
flask-cors
```

### Step 4: Install FFmpeg

FFmpeg is required to convert WebM audio to PCM WAV for Vosk:
- **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html), extract, and add the `bin` folder to your system PATH.
- **macOS**: Install via Homebrew:
  ```bash
  brew install ffmpeg
  ```
- **Linux**: Install via package manager, e.g.:
  ```bash
  sudo apt-get install ffmpeg
  ```
Verify installation:
```bash
ffmpeg -version
```

### Step 5: Download Vosk Model

1. Download a Vosk model (e.g., `vosk-model-en-us-0.42-gigaspeech`) from [Vosk Models](https://alphacephei.com/vosk/models).
2. Extract the model to a directory (e.g., `D:/callagent/vosk-model-en-us-0.42-gigaspeech`).
3. Update the `VOSK_MODEL_PATH` in the `.env` file to match this location.

### Step 6: Verify the `.env` File

Ensure the `.env` file exists in the project root with:

```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
HOST=0.0.0.0
PORT=5000
VOSK_MODEL_PATH=replace_it_with_yours
```

Replace `your_openai_api_key` and `your_elevenlabs_api_key` with your actual API keys. Adjust `HOST`, `PORT`, and `VOSK_MODEL_PATH` as needed.

### Step 7: Run the Program

Start the Flask application with SocketIO:

```bash
python app.py
```

The app runs on the specified `HOST` and `PORT` (e.g., `http://localhost:5000`).

### Step 8: Deactivate the Virtual Environment (Optional)

When finished:

```bash
deactivate
```

## How the Program Works

1. **Web Interface**:
   - Access `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`) to load a web interface with "Start Talking" and "Stop Talking" buttons.
   - The interface captures audio via the browser, sends it over WebSocket, and plays AI responses.

2. **Conversation Flow**:
   - Starts with: "Do you have a federal tax debt over five thousand dollars or any missed filings? Please respond with 'yes,' 'no,' or something else."
   - Handles responses:
     - **"Yes"**: Requests contact details (name, email, phone) for team follow-up.
     - **"No"**: Confirms with "Are you sure you don’t have a tax debt?" and respects "do not call" requests.
     - **Unclear Response**: Repeats the question (up to twice) before ending with "Thank you for your time! Goodbye!"
     - **Closing Phrases** (e.g., "goodbye," "thank you"): Ends and resets the conversation.
   - Uses OpenAI’s GPT-4 for general responses outside the fixed flow.

3. **Audio Processing**:
   - Browser records audio as WebM (Opus codec) and sends it via WebSocket.
   - Server converts WebM to PCM WAV using FFmpeg for Vosk compatibility.
   - Vosk transcribes audio to text, sending partial and final results to the client.
   - Ascertains transcription accuracy and emits a final result when ready.
   - Responses are converted to audio via ElevenLabs and played back in the browser.

4. **State Management**:
   - Tracks conversation state (e.g., `greeting`, `tax_debt`, `collect_name`) and contact details per session ID.
   - Resets state after conversation ends (e.g., on "goodbye").

5. **WebSocket**:
   - Handles real-time audio data (`audio_data` event) and transcription results (`transcription` event).
   - Sends AI responses and audio (`response` event) back to the client.

## Usage

1. **Access the Application**: Open a browser (e.g., Chrome) and go to `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`).

2. **Interact with the Assistant**:
   - Click "Start Talking" to begin, granting microphone access.
   - Speak your response (e.g., "yes," "no," or other).
   - The assistant transcribes your speech, processes it, and responds with text and audio.
   - Click "Stop Talking" to end the session.

3. **Example Interaction**:
   - Assistant: "Do you have a federal tax debt over five thousand dollars or any missed filings?"
   - User: "Yes" → Assistant: "Thank you for letting me know. I’ll transfer you to our team. Could you please provide your name?"
   - User: "No" → Assistant: "Not a problem, but before I let you go, are you sure you don’t have a tax debt?"
   - User: "Goodbye" → Assistant: "Thank you for your time! Goodbye!"

## Environment Variables

The `.env` file configures:

- `OPENAI_API_KEY`: OpenAI API key for GPT-4.
- `ELEVENLABS_API_KEY`: ElevenLabs API key for text-to-speech.
- `HOST`: Server host (e.g., `0.0.0.0`).
- `PORT`: Server port (e.g., `5000`).
- `VOSK_MODEL_PATH`: Path to the Vosk model directory.

**Note**: Keep the `.env` file secure and exclude it from version control (e.g., via `.gitignore`).

## Browser Compatibility

- Requires a modern browser (e.g., Chrome) with `navigator.mediaDevices.getUserMedia` support for microphone access.
- Audio playback uses HTML5 `<audio>` for MP3 from ElevenLabs.

## Security Notes

- **API Keys**: Store in `.env`, never in code.
- **HTTPS**: Use HTTPS in production for secure data transmission.
- **Session Data**: Contact details and states are stored in memory, reset after each session.

## Limitations

- Vosk requires a downloaded model and FFmpeg for audio conversion.
- Internet connection needed for OpenAI and ElevenLabs APIs.
- Audio quality and transcription accuracy depend on microphone and noise levels.
- No persistent storage for contact details.

## Troubleshooting

- **API Errors**: Check `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` in `.env`.
- **Vosk Fails**: Verify `VOSK_MODEL_PATH` and model presence.
- **Audio Issues**: Ensure FFmpeg is in PATH, check microphone permissions.
- **Server Issues**: Confirm `PORT` is free and `HOST` is correct.
- **WebSocket**: Ensure browser supports SocketIO and no firewall blocks the connection.
