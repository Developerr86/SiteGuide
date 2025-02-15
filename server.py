from flask import Flask, request, jsonify, render_template, send_from_directory
import requests
import os
import asyncio
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_cloud_sdk_core import BaseService
from ibm_watson import SpeechToTextV1, NaturalLanguageUnderstandingV1
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser
from pydantic import SecretStr

app = Flask(__name__)

# Disable anonymized telemetry
os.environ["ANONYMIZED_TELEMETRY"] = "false"

load_dotenv()

# Load API keys from .env
IBM_API_KEY = os.getenv('IBM_API_KEY')
if not IBM_API_KEY:
    raise ValueError('IBM_API_KEY is not set')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY is not set')

IBM_STT_API_KEY = os.getenv('IBM_STT_API_KEY')
IBM_NLU_API_KEY = os.getenv('IBM_NLU_API_KEY')

# IBM Watson STT Setup
stt_authenticator = IAMAuthenticator(IBM_STT_API_KEY)
speech_to_text = SpeechToTextV1(authenticator=stt_authenticator)
speech_to_text.set_service_url("https://api.eu-de.speech-to-text.watson.cloud.ibm.com")

# IBM Watson NLU Setup
nlu_authenticator = IAMAuthenticator(IBM_NLU_API_KEY)
natural_language_understanding = NaturalLanguageUnderstandingV1(
    version="2019-07-12",
    authenticator=nlu_authenticator
)
natural_language_understanding.set_service_url("https://api.eu-de.natural-language-understanding.watson.cloud.ibm.com")

# Initialize the Gemini model
llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp', api_key=SecretStr(GEMINI_API_KEY))

# Instance a Browser
browser = Browser()

# Create the IAM authenticator using your API key
authenticator = IAMAuthenticator(IBM_API_KEY)
service = BaseService(authenticator=authenticator)
token = authenticator.token_manager.get_token()

# Define system prompt
system_prompt = "Please generate a detailed, well-constructed of strictly 1-2 sentence instruction based on the user's prompt for another LLM model to perform the user's task."


@app.route('/generate', methods=['POST'])
def generate_text():
    data = request.json
    user_prompt = data.get("prompt")

    body = {
        "input": f"Prompt: {user_prompt}\n{system_prompt}",
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 900,
            "min_new_tokens": 0,
            "repetition_penalty": 1
        },
        "model_id": "mistralai/mistral-large",
        "project_id": "b1cd01cc-ee57-4ed7-b2ae-fc008ecbbbf0"
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    response = requests.post("https://eu-gb.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29", headers=headers, json=body)

    try:
        response_data = response.json()
        generated_instruction = response_data.get("results", [{}])[0].get("generated_text", "").strip()
        print(f"Extracted Instruction: {generated_instruction}")
        return jsonify({"instruction": generated_instruction})
    except Exception as e:
        print(f"Error parsing response: {str(e)}")
        return jsonify({"error": "Failed to parse response"}), 500


# Run BrowserUse Agent with the instruction
async def do_task(instruction):
    try:
        agent = Agent(
            task=instruction,  # Pass the actual instruction
            llm=llm,
            save_conversation_path="logs/conversation.json",
            browser=browser
        )
        history = await agent.run(max_steps=20)
        print("Task completed successfully.")
        return "complete"
    except Exception as e:
        print(f"Error running agent: {e}")
        return "failed"


@app.route('/run-gemini', methods=['POST'])
def run_gemini():
    data = request.json
    instruction = data.get("instruction")

    if not instruction:
        print("Error: Instruction is missing")
        return jsonify({"error": "Instruction is required"}), 400

    print(f"Running instruction: {instruction}")

    try:
        result = asyncio.run(do_task(instruction))
        return jsonify({"status": result})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Failed to run task"}), 500


# Speech-to-Text Endpoint
@app.route('/start-recognition', methods=['POST'])
def start_recognition():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file uploaded'}), 400

        audio_file = request.files['audio']

        response = speech_to_text.recognize(
            audio=audio_file,
            content_type='audio/webm',
            model='en-US_BroadbandModel',
            interim_results=False
        ).get_result()

        if not response.get('results'):
            return jsonify({'error': 'No speech detected'}), 400

        full_transcript = ' '.join(
            result['alternatives'][0]['transcript'] for result in response['results']
        )

        print(f"🎤 Transcribed Speech: {full_transcript}")

        # Send transcribed text to IBM LLM API
        generate_response = requests.post(
            'http://127.0.0.1:5000/generate',
            json={"link": "N/A", "prompt": full_transcript},
            headers={'Content-Type': 'application/json'}
        )

        if generate_response.status_code == 200:
            generated_instruction = generate_response.json().get("instruction", "No instruction generated")
            print(f"📜 Generated Instruction: {generated_instruction}")

            # Send instruction to Gemini Agent
            gemini_response = requests.post(
                'http://127.0.0.1:5000/run-gemini',
                json={"instruction": generated_instruction},
                headers={'Content-Type': 'application/json'}
            )

            execution_status = gemini_response.json().get("status", "Execution failed")
            print(f"🚀 Execution Status: {execution_status}")

            return jsonify({
                "transcription": full_transcript,
                "instruction": generated_instruction,
                "status": execution_status
            })
        else:
            return jsonify({"error": "Failed to generate instruction"}), 500

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/')
def home():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
