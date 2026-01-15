/**
 * Chat interface for Rules Assistant
 */

const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const sendButton = document.getElementById("sendButton");
const chatLoading = document.getElementById("chatLoading");

// Add message to chat
function addMessage(content, isUser = false) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `chat-message ${isUser ? "user" : "assistant"}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  if (isUser) {
    contentDiv.innerHTML = `<strong>You:</strong> ${escapeHtml(content)}`;
  } else {
    contentDiv.innerHTML = `<strong>Rules Assistant:</strong> ${content}`;
  }

  messageDiv.appendChild(contentDiv);
  chatMessages.appendChild(messageDiv);

  // Scroll to bottom
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Send message
async function sendMessage() {
  const question = chatInput.value.trim();

  if (!question) return;

  // Disable input while processing
  chatInput.disabled = true;
  sendButton.disabled = true;
  chatLoading.style.display = "block";

  // Add user message
  addMessage(question, true);

  // Clear input
  chatInput.value = "";

  try {
    const response = await fetch("/api/rules-assistant", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });

    const data = await response.json();

    if (data.success) {
      // Format answer with sources
      let answer = data.answer;
      if (data.sources && data.sources.length > 0) {
        answer += "<br><br><em>Sources: " + data.sources.join(", ") + "</em>";
      }
      addMessage(answer, false);
    } else {
      addMessage(`❌ Error: ${data.error}`, false);
    }
  } catch (error) {
    console.error("Error:", error);
    addMessage("❌ Sorry, I encountered an error. Please try again.", false);
  } finally {
    // Re-enable input
    chatInput.disabled = false;
    sendButton.disabled = false;
    chatLoading.style.display = "none";
    chatInput.focus();
  }
}

// Event listeners
sendButton.addEventListener("click", sendMessage);

chatInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Focus input on load
chatInput.focus();
