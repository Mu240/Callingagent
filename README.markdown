# Tax Debt AI Assistant

## Overview

This is a Flask-based web application that provides an interactive AI assistant for handling inquiries about federal tax debt. The application uses speech recognition to accept user input, processes it using OpenAI's GPT-4 model, and responds with text-to-speech output via the ElevenLabs API. It guides users through a conversation flow to determine if they have a federal tax debt over $5,000 or missed filings, collects contact details if needed, and supports a Do Not Call list option.

## Features

- **Speech Recognition**: Utilizes browser-based Web Speech API for real-time speech-to-text input.
- **Text-to-Speech**: Converts AI responses to audio using the ElevenLabs API.
- **Conversation Flow**: Manages a stateful conversation to handle user responses, including "yes," "no," or unclear inputs.
- **Contact Collection**: Collects user name, email, and phone number for follow-up calls when requested.
- **Environment Variables**: Securely stores API keys, host, and port in a `.env` file.
- **CORS Support**: Allows cross-origin requests for web compatibility.

## Prerequisites

- Python 3.8+
- A modern web browser (e.g., Google Chrome) with Web Speech API support
- Internet access for API calls to OpenAI and ElevenLabs
- A valid `.env` file with API keys and server configuration
- A `requirements.txt` file with necessary dependencies

## Setup and Installation

### Step 1: Clone the Repository

Clone or download the project to your local machine:

```bash
git clone <repository-url>
cd <repository-directory>
```

### Step 2: Set Up a Python Virtual Environment

A virtual environment isolates the project’s dependencies to avoid conflicts with other Python projects.

1. **Create a Virtual Environment**: On Windows:

   ```bash
   python -m venv venv
   ```

   On macOS/Linux:

   ```bash
   python3 -m venv venv
   ```

2. **Activate the Virtual Environment**: On Windows:

   ```bash
   venv\Scripts\activate
   ```

   On macOS/Linux:

   ```bash
   source venv/bin/activate
   ```

   Once activated, your terminal prompt should change to indicate the virtual environment is active (e.g `(venv) $`.

### Step 3: Install Dependencies

With the virtual environment activated, install the required packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

The `requirements.txt` file includes:

```
flask
python-dotenv
openai
requests
flask-cors
```

### Step 4: Verify the `.env` File

Ensure the `.env` file exists in the project root and contains the following:

```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
HOST=0.0.0.0
PORT=5000
```

Replace `your_openai_api_key` and `your_elevenlabs_api_key` with your actual API keys from OpenAI and ElevenLabs. The `HOST` and `PORT` values can be customized (default values are `0.0.0.0` and `5000`).

### Step 5: Run the Program

Start the Flask application:

```bash
python app.py
```

The application will run on the specified `HOST` and `PORT` (e.g., `http://0.0.0.0:5000` or `http://localhost:5000` if accessed locally).

### Step 6: Deactivate the Virtual Environment (Optional)

When done, deactivate the virtual environment:

```bash
deactivate
```

## How the Program Works

1. **Web Interface**:

   - Upon accessing `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`), a simple web interface loads with "Start Talking" and "Stop Talking" buttons.
   - The interface uses the Web Speech API to capture user speech and display the assistant’s responses.

2. **Conversation Flow**:

   - The assistant starts by asking, "Do you have a federal tax debt over five thousand dollars or any missed filings?" via text-to-speech.
   - User responses are captured via speech recognition and sent to the `/process` endpoint.
   - Responses are processed as follows:
     - **"Yes"**: Prompts for contact details (name, email, phone) for a follow-up call.
     - **"No"**: Confirms if the user is sure, potentially adding them to a Do Not Call list if requested.
     - **Unclear Response**: Repeats the question up to two times before ending the conversation.
     - **Closing Phrases** (e.g., "goodbye," "thank you"): Ends the conversation and resets the state.
   - The assistant uses OpenAI’s GPT-4 for general responses and ElevenLabs for text-to-speech conversion.

3. **State Management**:

   - The application maintains a conversation state (`greeting`, `tax_debt`, `confirm_no`, etc.) to track the user’s progress.
   - Contact details are stored temporarily in memory (reset after the conversation ends).

4. **Audio Output**:

   - Responses are converted to audio using the ElevenLabs API and played back via the browser’s audio player.

## Usage

1. **Access the Application**: Open a web browser (e.g., Google Chrome) and navigate to `http://<HOST>:<PORT>` (e.g., `http://localhost:5000`).

2. **Interact with the Assistant**:

   - Click "Start Talking" to initiate the conversation. Grant microphone access when prompted.
   - Speak your response to the assistant’s question (e.g., "yes," "no," or other phrases).
   - The assistant responds with audio and text, guiding you through the conversation based on your input.
   - Click "Stop Talking" to end the session.

3. **Example Interaction**:

   - Assistant: "Do you have a federal tax debt over five thousand dollars or any missed filings?"
   - User: "Yes" → Assistant: "Thank you for letting me know. I’ll transfer you to our team. Could you please provide your name?"
   - User: "No" → Assistant: "Not a problem, but before I let you go, are you sure you don’t have a tax debt?"
   - User: "Goodbye" → Assistant: "Thank you for your time! Goodbye!"

## Environment Variables

The application uses a `.env` file to manage sensitive and configurable settings:

- `OPENAI_API_KEY`: Your OpenAI API key for GPT-4 access.
- `ELEVENLABS_API_KEY`: Your ElevenLabs API key for text-to-speech.
- `HOST`: The host address (e.g., `0.0.0.0` for external access).
- `PORT`: The port number (e.g., `5000`).

**Note**: Do not commit the `.env` file to version control. Ensure it’s listed in `.gitignore` to keep sensitive information secure.

## Browser Compatibility

The application relies on the Web Speech API for speech recognition, which is supported by modern browsers like Google Chrome. If the browser does not support `webkitSpeechRecognition`, an alert will notify the user.

## Security Notes

- **API Keys**: Store API keys in the `.env` file and avoid hardcoding them in the source code.
- **HTTPS**: For production, deploy the application behind an HTTPS server to secure audio and user data transmission.
- **Do Not Call List**: The application respects "do not call" requests by prompting for confirmation.

## Limitations

- The Web Speech API may not work in all browsers (e.g., older versions or non-Chromium browsers).
- The ElevenLabs API requires a valid API key and internet access for text-to-speech functionality.
- The application assumes a stable internet connection for API calls to OpenAI and ElevenLabs.
- Contact details are stored in memory and reset after each conversation (no persistent storage).

## Troubleshooting

- **API Errors**: Verify that `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` are valid in the `.env` file.
- **Speech Recognition Fails**: Ensure browser compatibility and microphone permissions.
- **Server Not Starting**: Check if the specified `PORT` is free and `HOST` is correctly configured.
- **Virtual Environment Issues**: Ensure the virtual environment is activated before running `pip install` or `python app.py`.

