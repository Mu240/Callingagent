# Tax Debt AI Assistant API

## Overview

This is a Flask-based web application designed to provide an interactive AI assistant for handling federal tax debt inquiries. It processes user text input via a REST API, uses OpenAI's GPT-4 for natural language responses, and converts responses to audio using the ElevenLabs API. The application manages a conversation flow to assess tax debt over $5,000 or missed filings, collects contact details for follow-ups, and returns responses as text and MP3 audio.

## Features

- **Text Input Processing**: Accepts user text input via a POST endpoint for tax debt inquiries.
- **Text-to-Speech**: Converts AI responses to audio via the ElevenLabs API.
- **Conversation Flow**: Guides users through states (greeting, tax debt, contact collection) based on responses like "yes," "no," or other inputs.
- **Contact Collection**: Gathers name, email, and phone for follow-up when tax debt is confirmed.
- **Environment Variables**: Securely stores API keys, host, and port in a `.env` file.
- **CORS Support**: Enables cross-origin requests for web compatibility.

## Prerequisites

- Python 3.8+
- Internet access for OpenAI and ElevenLabs API calls
- A valid `.env` file with API keys and configuration
- A `requirements.txt` file with dependencies

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
flask-cors
python-dotenv
openai
requests
```

### Step 4: Verify the `.env` File

Ensure the `.env` file exists in the project root with:

```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
HOST=0.0.0.0
PORT=5000
```

Replace `your_openai_api_key` and `your_elevenlabs_api_key` with your actual API keys. Adjust `HOST` and `PORT` as needed.

### Step 5: Run the Program

Start the Flask application:

```bash
python app.py
```

The app runs on the specified `HOST` and `PORT` (e.g., `http://localhost:5000`).

### Step 6: Deactivate the Virtual Environment (Optional)

When finished:

```bash
deactivate
```

## How the Program Works

1. **API Endpoint**:
   - The `/process_text_mp3` endpoint accepts POST requests with JSON containing `text` (user input) and an optional `session_id`.
   - Processes input and returns an MP3 audio file of the AI response.

2. **Conversation Flow**:
   - Starts with: "Do you have a federal tax debt over five thousand dollars or any missed filings? Please respond with 'yes,' 'no,' or something else."
   - Handles responses:
     - **"Yes"**: Requests contact details (name, email, phone) for team follow-up.
     - **"No"**: Confirms with "Not a problem, but before I let you go, are you sure you don’t have a tax debt?"
     - **Unclear Response**: Repeats the question (up to twice) before ending with "Thank you for your time! Goodbye!"
     - **Closing Phrases** (e.g., "goodbye," "thank you"): Ends and resets the conversation.
   - Uses OpenAI’s GPT-4 for general responses outside the fixed flow.

3. **Audio Processing**:
   - Converts AI response text to MP3 audio via the ElevenLabs API.
   - Returns the audio as a downloadable file.

4. **State Management**:
   - Tracks conversation state (e.g., `greeting`, `tax_debt`, `collect_name`) and contact details per session ID.
   - Resets state after conversation ends (e.g., on "goodbye").

## Usage

1. **Access the API**:
   - Send a POST request to `http://<HOST>:<PORT>/process_text_mp3` (e.g., `http://localhost:5000/process_text_mp3`).

2. **Input Format**:
   - Send a JSON payload with:
     - `text`: The user’s response (e.g., "yes", "no", "hello").
     - `session_id`: Optional, defaults to the client’s IP address.
   - Example:
     ```json
     {
       "text": "yes",
       "session_id": "user123"
     }
     ```

3. **Output Response**:
   - On success: Returns an MP3 file (`response.mp3`) containing the AI’s spoken response.
   - On error: Returns a JSON object with an `error` field and a status code (e.g., 400, 500).
   - Example success response: A downloadable MP3 file.
   - Example error response:
     ```json
     {
       "response": "I am sorry, I didn't understand. Let me repeat: Do you have a federal tax debt over five thousand dollars or any missed tax filings? Please respond with 'yes,' 'no,' or something else.",
       "error": "Failed to generate audio response"
     }
     ```

4. **Example Interaction**:
   - **Input**:
     ```json
     {
       "text": "hello"
     }
     ```
   - **Output**: MP3 file with the assistant saying: "Do you have a federal tax debt over five thousand dollars or any missed filings? Please respond with 'yes,' 'no,' or something else."
   - **Input**:
     ```json
     {
       "text": "yes"
     }
     ```
   - **Output**: MP3 file with the assistant saying: "Thank you for letting me know. I'll transfer you to our team. Could you please provide your name?"
   - **Input**:
     ```json
     {
       "text": "no, i don't have any tax debt"
     }
     ```
   - **Output**: MP3 file with the assistant saying: "Not a problem, but before I let you go, are you sure you don’t have a tax debt?"
   - **Input**:
     ```json
     {
       "text": "goodbye"
     }
     ```
   - **Output**: MP3 file with the assistant saying: "Thank you for your time! Goodbye!"

## Environment Variables

The `.env` file configures:

- `OPENAI_API_KEY`: OpenAI API key for GPT-4.
- `ELEVENLABS_API_KEY`: ElevenLabs API key for text-to-speech.
- `HOST`: Server host (e.g., `0.0.0.0`).
- `PORT`: Server port (e.g., `5000`).

**Note**: Keep the `.env` file secure and exclude it from version control (e.g., via `.gitignore`).

## Security Notes

- **API Keys**: Store in `.env`, never in code.
- **HTTPS**: Use HTTPS in production for secure data transmission.
- **Session Data**: Contact details and states are stored in memory, reset after each session.

## Limitations

- Internet connection needed for OpenAI and ElevenLabs APIs.
- No persistent storage for contact details.
- Audio quality depends on the ElevenLabs API response.

## Troubleshooting

- **API Errors**: Check `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` in `.env`.
- **Server Issues**: Confirm `PORT` is free and `HOST` is correct.
- **Audio Issues**: Verify ElevenLabs API key and network connectivity.
