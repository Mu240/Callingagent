# Tax Debt AI Assistant API

## Overview

A Flask-based web application providing an AI assistant for federal tax debt inquiries, processing text input via a REST API, leveraging OpenAI's GPT-4 for responses, and converting them to MP3 audio with ElevenLabs. It manages a conversation flow, collects contact details, logs interactions to MySQL, and serves audio responses.

## Features

- **Text Input Processing**: Handles user text via POST to `/process_text_mp3`.
- **Text-to-Speech**: Converts responses to MP3 using ElevenLabs API.
- **Conversation Flow**: Guides users through greeting, tax debt, and contact collection stages.
- **Contact Collection**: Captures name, email, and phone for follow-up.
- **MySQL Logging**: Stores request and response logs in a database.
- **Environment Variables**: Secures API keys, host, port, and MySQL config in `.env`.
- **CORS Support**: Enables cross-origin requests.

## Prerequisites

- Python 3.8+
- Internet access for OpenAI and ElevenLabs APIs
- MySQL server
- A `.env` file with API keys and configuration
- A `requirements.txt` file with dependencies

## Setup and Installation

### Step 1: Clone the Repository
```bash
git clone <repository-url>
cd <repository-directory>
```

### Step 2: Set Up a Python Virtual Environment
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
**Required Packages**:
```
flask
flask-cors
python-dotenv
openai
requests
mysql-connector-python
```

### Step 4: Verify the `.env` File
Ensure `.env` in the project root contains:
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

### Step 5: Run the Program
```bash
python app.py
```
Runs on `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`).

### Step 6: Deactivate Virtual Environment (Optional)
```bash
deactivate
```

## How the Program Works

1. **API Endpoint**:
   - `/process_text_mp3` (POST): Processes text input, returns text and audio URL.
   - `/static/audio/<filename>`: Serves generated MP3 files.

2. **Conversation Flow**:
   - **Greeting**: Asks about tax debt over $5,000 or missed filings.
   - **Responses**:
     - "Yes": Collects name, email, phone for team follow-up.
     - "No": Confirms with "Are you sure you don’t have a tax debt?"
     - Other: Repeats question (up to twice), then ends.
     - Goodbyes (e.g., "bye"): Ends with "Thank you for your time! Goodbye!"
   - Uses GPT-4 for unhandled queries.

3. **Audio Processing**:
   - Converts responses to MP3 via ElevenLabs, stores in `static/audio/`.
   - Returns a URL to the audio file.

4. **State Management**:
   - Tracks state (greeting, tax_debt, collect_name, etc.) per session UUID.
   - Resets after goodbye or completion.

5. **Logging**:
   - Logs requests, responses, and errors to `logs/app.log` and MySQL `logs` table.

## Usage

1. **Access the API**:
   - POST to `http://<HOST>:<PORT>/process_text_mp3`.

2. **Input Format**:
   - JSON payload:
     - `text`: User input (e.g., "yes").
     - `uuid`: Session identifier.
     - `number`: User phone number.
   - Example:
     ```json
     {
       "text": "yes",
       "uuid": "user123",
       "number": "123-456-7890"
     }
     ```

3. **Output Response**:
   - Success: JSON with `response` (text) and `audio_url` (MP3 URL).
   - Error: JSON with `error` field, status code (e.g., 400, 500).
   - Example Success:
     ```json
     {
       "response": "Thank you for letting me know. I'll transfer you to our team. Could you please provide your name?",
       "audio_url": "http://localhost:5000/static/audio/abc123.mp3"
     }
     ```
   - Example Error:
     ```json
     {
       "response": "I am sorry, I didn't understand. Let me repeat: Do you have a federal tax debt over five thousand dollars or any missed tax filings? Please respond with 'yes,' 'no,' or something else.",
       "error": "Failed to generate audio response"
     }
     ```

4. **Example Interaction**:
   - **Input**: `{"text": "hello", "uuid": "user123", "number": "123-456-7890"}`
   - **Output**: JSON with text and audio URL for tax debt question.
   - **Input**: `{"text": "yes", "uuid": "user123", "number": "123-456-7890"}`
   - **Output**: JSON with text and audio URL requesting name.
   - **Input**: `{"text": "goodbye", "uuid": "user123", "number": "123-456-7890"}`
   - **Output**: JSON with goodbye message and audio URL.

## Environment Variables

- `OPENAI_API_KEY`: OpenAI API key for GPT-4.
- `ELEVENLABS_API_KEY`: ElevenLabs API key for text-to-speech.
- `HOST`: Server host (e.g., `0.0.0.0`).
- `PORT`: Server port (e.g., `5000`).
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT`: MySQL configuration.

**Note**: Secure `.env` and exclude from version control.

## Security Notes

- **API Keys**: Store in `.env`, not code.
- **HTTPS**: Use in production for security.
- **Session Data**: Stored in memory, resets after session.
- **Logging**: Sensitive data (e.g., headers, body) logged to MySQL and file.

## Limitations

- Requires internet for APIs.
- No persistent contact storage.
- Audio quality relies on ElevenLabs.
- MySQL connection needed for logging.

## Troubleshooting

- **API Errors**: Verify `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`.
- **MySQL Issues**: Check `MYSQL_*` variables, server status.
- **Server Issues**: Ensure `PORT` is free, `HOST` is correct.
- **Audio Issues**: Confirm ElevenLabs API key, network.
