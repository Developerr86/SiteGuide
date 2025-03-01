$(document).ready(function() {
    let mediaRecorder;
    let audioChunks = [];
    let isProcessing = false; // Track if a request is in progress

    // Function to add a message to the chat (already defined in index.html for polling)
    // No need to redefine here, but kept for clarity in local scope if needed
    function addMessage(sender, message) {
        var messageClass = (sender === "user") ? "user-message" : "agent-message";
        var messageDiv = $("<div>").addClass("message " + messageClass).text(message);
        $("#chatMessages").append(messageDiv);
        $("#chatMessages").scrollTop($("#chatMessages")[0].scrollHeight);
    }

    // Function to add an image message (for GIF) - already defined in index.html
    function addImageMessage(sender, imageData) {
        var messageClass = (sender === "user") ? "user-message" : "agent-message";
        var messageDiv = $("<div>").addClass("message " + messageClass);
        var img = $("<img>").attr("src", imageData).css({
            "max-width": "100%",
            "max-height": "300px"  // Limit GIF size in chat
        });
        messageDiv.append(img);
        $("#chatMessages").append(messageDiv);
        $("#chatMessages").scrollTop($("#chatMessages")[0].scrollHeight);
    }

    // Function to encode audio data to base64
    function blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    // Function to send request asynchronously without waiting for response
    function sendRequest(url, data) {
        if (isProcessing) {
            addMessage("agent", "Please wait, processing previous request...");
            return;
        }

        isProcessing = true;
        $.ajax({
            type: "POST",
            url: url,
            data: data,
            async: true, // Ensure asynchronous
            success: function() {
                isProcessing = false;
                addMessage("agent", "Request sent successfully (updates via polling).");
            },
            error: function(xhr, status, error) {
                isProcessing = false;
                addMessage("agent", "Error sending request: " + (error || "Network error"));
            },
            complete: function() {
                isProcessing = false; // Ensure isProcessing is reset even on error
            }
        });
    }

    // Record button functionality
    $("#recordButton").click(function() {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
            $(this).text("Record");
        } else {
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(stream => {
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    mediaRecorder.ondataavailable = function(e) { audioChunks.push(e.data); };
                    mediaRecorder.onstop = async function() {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/m4a' });
                        const audioBase64 = await blobToBase64(audioBlob);
                        addMessage("user", "Recorded audio, sending to server...");
                        var headless = $('#headlessCheckbox').is(':checked');
                        var vision = $('#visionCheckbox').is(':checked');
                        sendRequest("/run_task", { audioData: audioBase64, headless: headless, vision: vision });
                    };
                    mediaRecorder.start();
                    $(this).text("Recording...");
                })
                .catch(err => addMessage("agent", "Error accessing microphone: " + err));
        }
    });

    // Send button functionality
    $("#sendButton").click(function() {
        var messageText = $("#messageInput").val().trim();
        if (messageText !== "") {
            addMessage("user", messageText);
            $("#messageInput").val("");
            var headless = $('#headlessCheckbox').is(':checked');
            var vision = $('#visionCheckbox').is(':checked');
            sendRequest("/run_task", { task: messageText, headless: headless, vision: vision });
        }
    });

    // Handle pressing Enter key in the input field
    $("#messageInput").keypress(function(event) {
        if (event.which == 13) {
            $("#sendButton").click();
            return false;
        }
    });
});