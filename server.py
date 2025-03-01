import os
import asyncio
import logging
import tempfile
import base64
from typing import Optional, List
from queue import Queue
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserConfig, SystemPrompt
from browser_use.browser.context import BrowserContextConfig, BrowserContext
from pydantic import SecretStr
from browser_use.controller.service import Controller
from groq import Groq
from asgiref.wsgi import WsgiToAsgi

# Set Windows event loop policy for asyncio compatibility
# if os.name == 'nt':  # Windows
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Global state for login handling and messages
original_agent: Optional[Agent] = None
login_domain = ""
awaiting_continue = False
awaiting_credentials = False
is_task = True  # Flag to distinguish task inputs from login/continue/exit commands
agent_messages = Queue()  # Use a Queue to store agent messages

# Initialize the language model
def get_llm():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('GEMINI_API_KEY is not set.')
    return ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp', api_key=SecretStr(api_key))

try:
    llm = get_llm()
except ValueError as e:
    logger.critical(f"Failed to initialize LLM: {e}")
    exit(1)

# Initialize Groq client
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise ValueError("GROQ_API_KEY is not set.")
groq_client = Groq(api_key=groq_api_key)

class CustomSystemPrompt(SystemPrompt):
    def important_rules(self) -> str:
        return """
1. INPUT FIELD DETECTION:
   - Carefully analyze the current webpage for any input fields (e.g., text inputs, password fields, select boxes) that require user-provided information, such as usernames, email addresses, passwords, one-time passwords (OTPs), phone numbers, or other personal details.
   - Look for indicators of input fields, including:
     - HTML input types: `text`, `email`, `password`, `tel`, `number`.
     - Attributes: `type`, `name`, `id`, `placeholder`, `aria-label`, `aria-describedby`, `title`, `role`, or `class` containing keywords like "username", "email", "password", "otp", "phone", "login", "signin", "register", "authentication", "verify", or "code".
     - Labels or surrounding text suggesting user input is required (e.g., "Enter your email", "Password", "Phone Number", "Verification Code").
     - Fields marked as required (`required` attribute) or visually highlighted as mandatory.
   - Detect multi-step forms (e.g., login pages with separate email/username and password fields, or OTP verification after login).
   - If an input field requiring user information is detected, immediately call the "Handle Login" action with the current domain (e.g., "Handle Login" with domain "example.com") and pause execution to wait for user input or credentials.

2. LOGIN HANDLING:
   - When calling "Handle Login", pause the agent and wait for user instructions via the chat interface. The user can either:
     - Provide credentials manually (e.g., "email password" for automatic login).
     - Manually log in and type 'continue' to resume.
     - Type 'exit' to stop the agent.
   - Do not attempt to guess, generate, or autofill credentials unless explicitly provided by the user.
   - If the page requires multiple inputs (e.g., username and password), ensure the "Handle Login" action is called once for the domain, and the user provides all necessary credentials in the format specified.

3. ERROR HANDLING AND CONTEXT:
   - If unsure whether an input field requires user information, err on the side of caution and call "Handle Login" to prompt the user.
   - Ignore non-sensitive input fields like search bars, comments, or optional form fields unless they clearly relate to authentication or personal data.
   - Use the browser context (e.g., URLs, DOM structure, and previous actions) to determine if the input field is part of a login, registration, or verification process.

4. PERFORMANCE AND PRECISION:
   - Avoid unnecessary calls to "Handle Login" for non-authentication fields (e.g., address, preferences, or non-required fields).
   - Prioritize accuracy over speed, ensuring you only pause for fields that genuinely require user intervention for security or access.
   - If multiple input fields are detected on the same page, analyze their relationship (e.g., grouped in a form with a "Login" or "Submit" button) and call "Handle Login" once, providing the domain.

5. EXAMPLES:
   - For a login page with fields labeled "Email" and "Password", call "Handle Login" with the domain and pause for user input.
   - For an OTP field labeled "Verification Code" after login, call "Handle Login" and wait for credentials or 'continue'.
   - For a phone number field in a registration form, call "Handle Login" if it’s part of authentication, but skip if it’s optional or unrelated to login.
"""
    def additional_context(self) -> str:
        return """
- Use the browser’s DOM structure, ARIA attributes, and surrounding text to identify input fields.
- Leverage the history of actions and page states to determine if the current page is part of an authentication flow.
- Ensure all sensitive data (e.g., usernames, passwords, OTPs) is handled securely by pausing and deferring to user input via the chat interface.
"""

# Initialize controller
controller = Controller()

def send_agent_message(message: str):
    """Add a message to the queue for polling by the frontend."""
    agent_messages.put(message)
    logger.info(f"Queued agent message: {message}")

def encode_gif_to_base64(gif_path: str) -> str:
    """Encode a GIF file to base64 for sending as a message."""
    try:
        with open(gif_path, "rb") as gif_file:
            base64_encoded = base64.b64encode(gif_file.read()).decode('utf-8')
            return f"data:image/gif;base64,{base64_encoded}"
    except Exception as e:
        logger.error(f"Failed to encode GIF: {str(e)}")
        return ""

@controller.action('Handle Login')
async def handle_login_action(domain: str, reason: str, browser: BrowserContext):
    global original_agent, login_domain, awaiting_continue, awaiting_credentials, is_task
    logger.info(f"Login detected for {domain}. Pausing task.")
    
    if not original_agent:
        logger.error("Original agent not set. Cannot pause task.")
        return
    
    login_domain = domain
    original_agent.pause()  # Use Agent.pause() from browser-use
    awaiting_continue = True
    awaiting_credentials = False
    is_task = False  # Expecting login-related input, not a task
    logger.info(f"Task paused for {domain}. Awaiting user login choice.")
    
    # Send message to the chat interface via queue (polled by frontend)
    send_agent_message(f"Agent has been paused. Would you like to provide your credentials to the agent? Type 'yes', 'no', or 'exit' in the chat.")

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/run_task', methods=['POST'])
async def run_task():
    global original_agent, awaiting_continue, login_domain, awaiting_credentials, is_task
    try:
        task = request.form.get('task')
        audio_data = request.form.get('audioData')
        headless = request.form.get('headless') == 'true'
        use_vision = request.form.get('vision') == 'true'

        logger.info(f"Task: {task}, Audio: {'Yes' if audio_data else 'No'}, Headless: {headless}, Vision: {use_vision}")

        # Handle exit command at any time
        if task and task.lower() == "exit":
            if original_agent:
                logger.info("Stopping active agent due to 'exit' command.")
                original_agent.stop()  # Use Agent.stop() from browser-use to terminate the agent
                await cleanup_agent()  # Clean up the agent and browser
                send_agent_message("Agent stopped and exited. No task is active.")
                is_task = True  # Reset to expect tasks for the next input
                return '', 204
            else:
                send_agent_message("No active agent to exit.")
                return '', 400

        # Handle login/continue responses (not a task)
        if not is_task:
            if awaiting_continue and task and task.lower() == "yes":
                awaiting_continue = False
                awaiting_credentials = True
                is_task = False
                send_agent_message(f"Please provide your email/username and password for {login_domain} in the format: 'email password'.")
                return '', 204
            elif awaiting_continue and task and task.lower() == "no":
                awaiting_continue = False
                is_task = False
                send_agent_message("Please manually log in and type 'continue' or 'exit' in the chat to resume or stop.")
                return '', 204
            elif awaiting_credentials and task and " " in task:
                awaiting_credentials = False
                awaiting_continue = False
                is_task = False
                email, password = task.split(" ", 1)
                email_placeholder = f"{login_domain}_email"
                password_placeholder = f"{login_domain}_password"
                original_agent.sensitive_data = {
                    email_placeholder: email,  # Plain string
                    password_placeholder: password,  # Plain string
                }
                login_task = (
                    f"1. Input <secret>{email_placeholder}</secret> into the email input field. "
                    f"2. Input <secret>{password_placeholder}</secret> into the password field. "
                    "3. Attempt to login"
                )
                original_agent.add_new_task(login_task)
                original_agent.resume()  # Resume the agent to run the login task
                send_agent_message("Credentials received. Attempting to log in automatically...")
                return '', 204
            elif awaiting_continue and task and task.lower() == "continue":
                if original_agent:
                    logger.info("Resuming paused agent after manual login.")
                    original_agent.resume()  # Use Agent.resume() from browser-use
                    awaiting_continue = False
                    login_domain = ""
                    is_task = False
                    send_agent_message("Agent resumed. Continuing task...")
                    return '', 204
                else:
                    send_agent_message("No paused agent to resume.")
                    return '', 400
            else:
                send_agent_message("Invalid response. Please type 'yes', 'no', 'continue', or 'exit', or provide credentials as 'email password'.")
                return '', 400

        # Handle audio transcription if provided
        if audio_data:
            try:
                with tempfile.NamedTemporaryFile(suffix=".m4a", delete=True) as temp_audio_file:
                    audio_bytes = base64.b64decode(audio_data.split(',')[1])
                    temp_audio_file.write(audio_bytes)
                    temp_audio_file.flush()
                    temp_audio_file.seek(0)  # Rewind to read from the start
                    transcription_response = await asyncio.to_thread(
                        groq_client.audio.transcriptions.create,
                        file=(temp_audio_file.name, temp_audio_file.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json"
                    )
                    send_agent_message("transcribed text: " + transcription_response.text)
                    task = transcription_response.text if transcription_response and hasattr(transcription_response, 'text') else None
                    if task is None:
                        logger.error("Transcription failed: No text returned from Groq API")
                        send_agent_message("Error: Failed to transcribe audio. Please check your audio input and try again.")
                        return '', 400
            except base64.binascii.Error as e:
                logger.error(f"Invalid audio data format: {str(e)}")
                send_agent_message("Error: Invalid audio data format. Ensure the audio is in m4a format.")
                return '', 400
            except Exception as e:
                logger.error(f"Transcription failed: {str(e)}")
                send_agent_message(f"Error transcribing audio: {str(e)}")
                return '', 500

        if not task:
            send_agent_message("Error: No task or audio provided.")
            return '', 400

        # Normal task processing (initialize and run a new agent)
        try:
            browser_config = BrowserConfig(
                headless=False if os.name == 'nt' else headless,  # Disable headless on Windows for debugging
                disable_security=True
            )
            browser = Browser(config=browser_config)
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            send_agent_message(f"Error initializing browser: {str(e)}")
            return '', 500

        browser_context = BrowserContext(browser=browser, config=BrowserContextConfig())
        original_agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            browser_context=browser_context,
            controller=controller,
            save_conversation_path=os.path.join(os.getcwd(), 'output.txt'),
            generate_gif=True,
            system_prompt_class=CustomSystemPrompt,
        )

        try:
            # Run the agent in the background and send updates via polling
            async def run_agent():
                try:
                    history = await original_agent.run()
                    final_result = history.final_result() or "No result returned."
                    urls = "\nURLs visited:\n" + "\n".join(history.urls())
                    result = f"Final Result:\n{final_result}\n{urls}"
                    if audio_data:
                        result += f"\n[Agent] Transcribed: {task}"
                    send_agent_message(result)
                    
                    # Check if the task completed successfully and GIF exists
                    if history.is_done():
                        gif_path = os.path.join(os.getcwd(), "agent_history.gif")
                        if os.path.exists(gif_path):
                            gif_base64 = encode_gif_to_base64(gif_path)
                            send_agent_message(gif_base64)  # Send base64-encoded GIF as a message
                        else:
                            logger.warning("agent_history.gif not found after task completion.")
                            send_agent_message("Task completed, but GIF generation failed or not found.")
                except Exception as e:
                    logger.error(f"Agent run failed: {str(e)}")
                    send_agent_message(f"Error processing task: {str(e)}")

            # Run the agent in the background
            asyncio.create_task(run_agent())
            
            # Return immediately with no content to keep the frontend responsive
            is_task = True  # Reset to expect tasks for the next input
            return '', 204
        except Exception as e:
            logger.error(f"Error in task setup: {str(e)}")
            send_agent_message(f"Error setting up task: {str(e)}")
            await cleanup_agent()
            return '', 500
        finally:
            # Cleanup in a separate task to avoid blocking
            async def cleanup():
                await cleanup_agent()
            asyncio.create_task(cleanup())

    except Exception as e:
        logger.error(f"Error in run_task: {str(e)}")
        send_agent_message(f"Internal Server Error: {str(e)}")
        return '', 500

@app.route('/get_agent_messages', methods=['GET'])
def get_agent_messages():
    """Poll for new agent messages and return them."""
    messages = []
    while not agent_messages.empty():
        messages.append(agent_messages.get())
    if messages:
        return jsonify({'messages': messages})
    return jsonify({'messages': []})

async def cleanup_agent():
    """Clean up the agent and browser resources."""
    global original_agent
    if original_agent:
        try:
            if not original_agent.injected_browser_context:
                await original_agent.browser_context.close()
            if not original_agent.injected_browser and original_agent.browser:
                await original_agent.browser.close()
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
        original_agent = None
        awaiting_continue = False
        awaiting_credentials = False
        is_task = True

# Wrap Flask app with ASGI adapter
asgi_app = WsgiToAsgi(app)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(asgi_app, host="127.0.0.1", port=5000, log_level="info")