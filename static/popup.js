document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');
    const themeToggle = document.getElementById('theme-toggle');
    const micBtn = document.getElementById('mic-btn'); // 🎤 Microphone Button

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;

    // Function to append a message to the chat interface
    function appendMessage(sender, message) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender);
        messageElement.textContent = message;
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight; // Auto-scroll to the latest message
    }

    // Function to send user input to /generate and process the instruction
    async function sendMessage() {
        const userPrompt = chatInput.value.trim();
        if (!userPrompt) return;

        appendMessage('user', userPrompt);
        chatInput.value = '';

        try {
            const generateResponse = await fetch('http://127.0.0.1:5000/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ link: window.location.href, prompt: userPrompt }),
            });

            if (!generateResponse.ok) {
                appendMessage('assistant', "Error: Failed to get a response from IBM API.");
                return;
            }

            const generateData = await generateResponse.json();
            const generatedInstruction = generateData.instruction || "Sorry, I couldn't generate an instruction.";

            appendMessage('assistant', `Instruction: ${generatedInstruction}`);

            const geminiResponse = await fetch('http://127.0.0.1:5000/run-gemini', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instruction: generatedInstruction }),
            });

            if (!geminiResponse.ok) {
                appendMessage('assistant', "Error: Failed to execute the task.");
                return;
            }

            const geminiData = await geminiResponse.json();
            const taskStatus = geminiData.status || "Execution failed.";

            appendMessage('assistant', `Execution Status: ${taskStatus}`);

        } catch (error) {
            appendMessage('assistant', "Error: Unable to connect to the server.");
            console.error("Fetch error:", error);
        }
    }

    // Function to toggle voice recording 🎤
    async function toggleRecording() {
        if (!navigator.mediaDevices) {
            appendMessage('assistant', "Error: Your browser does not support audio recording.");
            return;
        }

        if (isRecording) {
            // Stop Recording
            mediaRecorder.stop();
            micBtn.innerHTML = "🎤"; // Reset icon
            isRecording = false;
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const formData = new FormData();
                formData.append('audio', audioBlob, 'recording.webm');

                appendMessage('user', "🎙️ Processing your voice input...");

                try {
                    const response = await fetch('http://127.0.0.1:5000/start-recognition', {
                        method: 'POST',
                        body: formData
                    });

                    if (!response.ok) {
                        appendMessage('assistant', "Error: Speech recognition failed.");
                        return;
                    }

                    const data = await response.json();

                    if (data.error) {
                        appendMessage('assistant', `Error: ${data.error}`);
                        return;
                    }

                    appendMessage('assistant', `Transcription: ${data.transcription}`);
                    appendMessage('assistant', `Instruction: ${data.instruction}`);
                    appendMessage('assistant', `Execution Status: ${data.status}`);

                } catch (error) {
                    appendMessage('assistant', "Error: Unable to process voice input.");
                    console.error(error);
                }

                audioChunks = [];
            };

            mediaRecorder.start();
            micBtn.innerHTML = "⏹️"; // Change button to stop icon
            isRecording = true;

        } catch (error) {
            console.error(error);
            appendMessage('assistant', "Error: Failed to access the microphone.");
        }
    }

    // Send button click event listener
    sendBtn.addEventListener('click', sendMessage);

    // Enter key press event listener
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendMessage();
        }
    });

    // Clear button click event listener
    clearBtn.addEventListener('click', () => {
        chatMessages.innerHTML = '';
    });

    // Theme toggle button click event listener
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-theme');
    });

    // Mic button click event listener 🎤
    micBtn.addEventListener('click', toggleRecording);
});
