# Tax Debt AI Assistant API

## Overview
A Flask-based REST API designed to assist with federal tax debt inquiries. It processes user text input, generates responses using OpenAI's GPT-4, converts them to MP3 audio via ElevenLabs, and manages a structured conversation flow. The API logs interactions to a MySQL database and supports CORS for cross-origin requests.

## Features
- **Text Input Processing**: Accepts user text via POST to `/process_text_mp3`.
- **Text-to-Speech**: Converts responses to MP3 using ElevenLabs API.
- **Conversation Flow**: Manages stages: greeting, tax debt inquiry, and contact collection.
- **Contact Collection**: Captures name, email, and phone for follow-up.
- **MySQL Logging**: Stores request/response data in a database.
- **Environment Variables**: Secures sensitive configurations in `.env`.
- **CORS Support**: Enables cross-origin API access.

## Prerequisites
- Python 3.8+
- MySQL server
- Internet access for OpenAI and ElevenLabs APIs
- `.env` file with required configurations
- `requirements.txt` with dependencies

## Setup and Installation

### Step 1: Clone the Repository
```bash
git clone <repository-url>
cd <repository-directory>
```

### Step 2: Set Up Virtual Environment
1. Create:
   - Windows: `python -m venv venv`
   - macOS/Linux: `python3 -m venv venv`
2. Activate:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure `.env`
Create a `.env` file in the project root:
```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000/
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_mysql_database
MYSQL_PORT=
```
Replace placeholders with actual values.

### Step 5: Run the Application
```bash
python app.py
```
Access at `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`).

### Step 6: Deactivate Virtual Environment
```bash
deactivate
```

## How It Works
1. **API Endpoints**:
   - `/process_text_mp3` (POST): Processes text input, returns JSON with text response and MP3 audio URL.
   - `/static/audio/<filename>`: Serves generated MP3 files.
   - `/get_logs` (GET): Retrieves interaction logs with formatted timestamps.

2. **Conversation Flow**:
   - **Greeting**: Responds to greetings (e.g., "hi") and asks about tax debt over $5,000 or missed filings.
   - **Tax Debt Question**:
     - "Yes": Initiates contact collection (name, email, phone).
     - "No": Confirms with "Are you sure you don’t have a tax debt?"
     - Other: Repeats question (up to twice), then ends.
     - Goodbyes (e.g., "bye"): Ends with "Thank you for your time! Goodbye!"
   - Uses GPT-4 for unhandled inputs, staying within tax debt context.

3. **Audio Processing**:
   - Generates MP3 files using ElevenLabs, stored in `static/audio/`.
   - Returns audio URLs (e.g., `http://localhost:5000/static/audio/<filename>.mp3`).

4. **State Management**:
   - Tracks session state (greeting, tax_debt, collect_name, etc.) using a UUID.
   - Resets state after goodbye or contact collection completion.

5. **Logging**:
   - Logs requests, responses, and errors to `logs/app.log` and MySQL `logs` table.
   - Includes timestamps formatted as `HH:MM DD/MM/YYYY`.

## Usage
1. **API Request**:
   - POST to `http://<HOST>:<PORT>/process_text_mp3`.
   - JSON payload:
     ```json
     {
       "text": "yes",
       "uuid": "user123",
       "number": "123-456-7890"
     }
     ```

2. **Response Format**:
   - Success:
     ```json
     {
       "response": "Thank you for letting me know. I'll transfer you to our team. Could you please provide your name?",
       "audio_url": "http://localhost:5000/static/audio/abc123.mp3"
     }
     ```
   - Error:
     ```json
     {
       "error": "Missing text, uuid, or number in the request"
     }
     ```

3. **Example Interaction**:
   - **Input**: `{"text": "hello", "uuid": "user123", "number": "123-456-7890"}`
     - **Output**: Asks about tax debt.
   - **Input**: `{"text": "yes", "uuid": "user123", "number": "123-456-7890"}`
     - **Output**: Requests name.
   - **Input**: `{"text": "John Doe", "uuid": "user123", "number": "123-456-7890"}`
     - **Output**: Requests email.
   - **Input**: `{"text": "bye", "uuid": "user123", "number": "123-456-7890"}`
     - **Output**: Goodbye message.

## Environment Variables
- `OPENAI_API_KEY`: For GPT-4 access.
- `ELEVENLABS_API_KEY`: For text-to-speech.
- `HOST`, `PORT`, `BASE_URL`: Server configuration.
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT`: MySQL settings.

**Note**: Keep `.env` secure and exclude from version control.

## Security Notes
- **API Keys**: Store in `.env`, not in code.
- **HTTPS**: Recommended for production.
- **Session Data**: In-memory, cleared after session ends.
- **Logging**: Includes sensitive data (e.g., phone numbers) in MySQL and logs.

## Limitations
- Requires internet for API calls.
- No persistent contact storage beyond session.
- Audio quality depends on ElevenLabs.
- MySQL required for logging.

## Troubleshooting
- **API Errors**: Check `OPENAI_API_KEY` and `ELEVENLABS_API_KEY`.
- **MySQL Issues**: Verify `MYSQL_*` variables and server status.
- **Server Issues**: Ensure `PORT` is free and `HOST` is valid.
- **Audio Issues**: Validate ElevenLabs API key and network connectivity.
