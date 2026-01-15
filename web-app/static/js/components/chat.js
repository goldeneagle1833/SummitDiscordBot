/**
 * Chat interface for Rules Assistant
 */

const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const sendButton = document.getElementById("sendButton");
const chatLoading = document.getElementById("chatLoading");

// Simple markdown-like formatting
function formatResponse(text) {
  // Escape HTML first
  let formatted = escapeHtml(text);

  // Bold: **text** or __text__
  formatted = formatted.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  formatted = formatted.replace(/__(.+?)__/g, "<strong>$1</strong>");

  // Italic: *text* or _text_
  formatted = formatted.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  formatted = formatted.replace(/_([^_]+)_/g, "<em>$1</em>");

  // Rule citations: Rule X.X.X or rule X.X
  formatted = formatted.replace(
    /(Rule\s+\d+(?:\.\d+)*)/gi,
    '<span class="rule-citation">$1</span>'
  );

  // Bullet points: - item or • item
  formatted = formatted.replace(/^[-•]\s+(.+)$/gm, "<li>$1</li>");
  formatted = formatted.replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>");

  // Numbered lists: 1. item
  formatted = formatted.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");

  // Wrap consecutive <li> in <ul>
  formatted = formatted.replace(
    /(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g,
    "<ul>$1</ul>"
  );
  formatted = formatted.replace(/<\/ul>\s*<ul>/g, "");

  // Line breaks: double newline = paragraph, single = <br>
  formatted = formatted.replace(/\n\n/g, "</p><p>");
  formatted = formatted.replace(/\n/g, "<br>");

  // Wrap in paragraph
  formatted = "<p>" + formatted + "</p>";

  // Clean up empty paragraphs
  formatted = formatted.replace(/<p>\s*<\/p>/g, "");
  formatted = formatted.replace(/<p>\s*<ul>/g, "<ul>");
  formatted = formatted.replace(/<\/ul>\s*<\/p>/g, "</ul>");

  return formatted;
}

// Add message to chat
function addMessage(content, isUser = false, sources = null) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `chat-message ${isUser ? "user" : "assistant"}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  if (isUser) {
    contentDiv.innerHTML = `<strong>You:</strong> ${escapeHtml(content)}`;
  } else {
    contentDiv.innerHTML = `<strong>Rules Assistant:</strong>${formatResponse(
      content
    )}`;

    // Add sources if available
    if (sources && sources.length > 0) {
      const sourcesDiv = document.createElement("div");
      sourcesDiv.className = "message-sources";
      sourcesDiv.innerHTML = `<span class="sources-label">📚 Sources:</span> ${sources.join(
        ", "
      )}`;
      contentDiv.appendChild(sourcesDiv);
    }
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
      addMessage(data.answer, false, data.sources);
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
