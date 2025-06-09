# Tax Debt AI Assistant API

## Overview
A Flask-based REST API designed to assist with federal tax debt inquiries. It processes user text input, responds using predefined prompts, serves pre-recorded MP3 audio, and logs interactions to a MySQL database. The API includes CORS support for cross-origin requests and manages a structured conversation flow.

## Features
- **Text Input Processing**: Accepts user text via POST to `/process_text_mp3`.
- **Pre-recorded Audio**: Serves MP3 files from `static/audio/` based on response text.
- **Conversation Flow**: Handles stages: greeting, tax debt inquiry, tax type confirmation, and call resolution.
- **MySQL Logging**: Stores interaction data (requests, responses, timestamps) in a database.
- **Environment Variables**: Secures configurations in a `.env` file.
- **CORS Support**: Enables cross-origin API access.

## Prerequisites
- Python 3.8+
- MySQL server
- Pre-recorded MP3 files in `static/audio/`
- `.env` file with required configurations
- `requirements.txt` with dependencies (e.g., Flask, mysql-connector-python, python-dotenv)

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
HOST=0.0.0.0
PORT=5000
OPENAI_API_KEY=
BASE_URL=http://localhost:5000/
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_mysql_database
MYSQL_PORT=3306
```
Replace placeholders with actual values.

### Step 5: Prepare Audio Files
- Place pre-recorded MP3 files in `static/audio/`, named after prompt keys (e.g., `greeting.mp3`, `yes.mp3`).

### Step 6: Run the Application
```bash
python app.py
```
Access at `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`).

### Step 7: Deactivate Virtual Environment
```bash
deactivate
```

## How It Works
1. **API Endpoints**:
   - `/process_text_mp3` (POST): Processes text input, returns JSON with response text, audio URL, and flags (end, transfer).
   - `/static/audio/<filename>`: Serves pre-recorded MP3 files.
   - `/get_logs` (GET): Retrieves interaction logs with formatted timestamps.

2. **Conversation Flow**:
   - **Greeting**: Responds to initial input (e.g., "hello") with tax debt question.
   - **Tax Debt Question**:
     - "Yes": Asks if debt is federal or state, prepares for transfer.
     - "No": Confirms if no federal tax debt exists.
     - Specific inputs (e.g., "who are you", "do not call"): Handles with tailored responses.
     - Goodbyes (e.g., "bye"): Ends with a farewell message.
     - Unhandled inputs: Repeats question (up to twice), then ends.
   - **Tax Type**: Confirms if debt is federal (transfers) or state (ends call).
   - Uses predefined prompts for consistent responses.

3. **Audio Processing**:
   - Maps response text to pre-recorded MP3 files in `static/audio/`.
   - Returns audio URLs (e.g., `http://localhost:5000/static/audio/greeting.mp3`).

4. **State Management**:
   - Tracks session state (greeting, tax_debt, tax_type, etc.) using a UUID.
   - Resets state after call ends or transfer is initiated.

5. **Logging**:
   - Logs requests, responses, and errors to `logs/app.log` and MySQL `logs` table.
   - Includes timestamps formatted as `HH:MM DD/MM/YYYY`, with `end` and `transfer` flags.

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
       "response": "Ok let me transfer you to a live agent. Is your Tax Debt federal or State?. Please wait and the next available live agent will answer the call.",
       "audio_url": "http://localhost:5000/static/audio/yes.mp3",
       "end": 0,
       "transfer": 1
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
     - **Output**: Asks if debt is federal or state.
   - **Input**: `{"text": "federal", "uuid": "user123", "number": "123-456-7890"}`
     - **Output**: Prepares for transfer to live agent.
   - **Input**: `{"text": "bye", "uuid": "user123", "number": "123-456-7890"}`
     - **Output**: Ends with goodbye message.

## Environment Variables
- `HOST`, `PORT`, `BASE_URL`: Server configuration.
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_PORT`: MySQL settings.

**Note**: Keep `.env` secure and exclude from version control.

## Security Notes 
- **Session Data**: In-memory, cleared after session ends.
- **Logging**: Includes sensitive data (e.g., phone numbers) in MySQL and logs.
- **HTTPS**: Recommended for production.

## Limitations
- Requires pre-recorded MP3 files for all responses.
- No dynamic text-to-speech; relies on static audio.
- MySQL required for logging.
- No persistent storage for user data beyond session.

## Troubleshooting
- **API Errors**: Check `.env` for missing or incorrect variables.
- **MySQL Issues**: Verify `MYSQL_*` variables and server status.
- **Server Issues**: Ensure `PORT` is free and `HOST` is valid.
- **Audio Issues**: Confirm MP3 files exist in `static/audio/` and match prompt keys.
