import { askQuestion, resolveApiBaseUrl, warmupBackend } from "./api.js";

const MAX_QUERY_LENGTH = 500;
const state = {
  isLoading: false,
  hasMessages: false,
  apiBaseUrl: resolveApiBaseUrl(),
  loadingMessage: null,
  currentAnswerSlot: null,
};

const elements = {
  form: document.querySelector("#chat-form"),
  input: document.querySelector("#query-input"),
  askButton: document.querySelector("#ask-button"),
  chatHistory: document.querySelector("#chat-history"),
  exampleButtons: [...document.querySelectorAll(".example-chip")],
};

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitCurrentQuestion();
});

elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitCurrentQuestion();
  }
});

elements.exampleButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const question = button.dataset.question || "";
    elements.input.value = question;
    submitCurrentQuestion();
  });
});

async function submitCurrentQuestion() {
  const query = elements.input.value.trim();
  if (!query || state.isLoading) {
    return;
  }

  if (query.length > MAX_QUERY_LENGTH) {
    showChatHistory();
    appendAssistantError(`Questions must be ${MAX_QUERY_LENGTH} characters or fewer.`);
    return;
  }

  showChatHistory();
  beginExchange(query);
  setLoading(true);

  try {
    const payload = await askQuestion(query, { apiBaseUrl: state.apiBaseUrl });
    hideLoadingBubble();
    appendAssistantPayload(payload);
    elements.input.value = "";
  } catch (error) {
    hideLoadingBubble();
    appendAssistantError(error.message);
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  state.isLoading = isLoading;
  elements.askButton.disabled = isLoading;
  elements.exampleButtons.forEach((button) => {
    button.disabled = isLoading;
  });

  if (isLoading) {
    elements.askButton.querySelector(".ask-label").textContent = "Asking";
    showLoadingBubble();
  } else {
    elements.askButton.querySelector(".ask-label").textContent = "Ask";
  }
}

function showChatHistory() {
  if (state.hasMessages) {
    return;
  }
  state.hasMessages = true;
  elements.chatHistory.hidden = false;
}

function beginExchange(query) {
  const exchange = createElement("article", "exchange");
  exchange.dataset.testid = "exchange";

  const questionBlock = createElement("div", "exchange-question");
  questionBlock.append(
    createElement("p", "exchange-label", "Your question"),
    createElement("p", "exchange-query", query),
  );

  const answerBlock = createElement("div", "exchange-answer");
  exchange.append(questionBlock, answerBlock);
  elements.chatHistory.append(exchange);
  state.currentAnswerSlot = answerBlock;
  exchange.scrollIntoView({ block: "end", behavior: "smooth" });
  return answerBlock;
}

function appendToAnswerSlot(node) {
  const slot = state.currentAnswerSlot || elements.chatHistory;
  slot.append(node);
  node.scrollIntoView({ block: "end", behavior: "smooth" });
}

function showLoadingBubble() {
  hideLoadingBubble();

  const card = createElement("div", "loading-card");
  const inner = createElement("div", "card-inner");
  const row = createElement("div", "loading-row");

  const icon = createElement("span", "material-symbols-outlined spin-icon");
  icon.textContent = "sync";
  row.append(icon, document.createTextNode("Analyzing scheme data..."));
  inner.append(row);
  card.append(inner);

  appendToAnswerSlot(card);
  state.loadingMessage = card;
}

function hideLoadingBubble() {
  if (state.loadingMessage) {
    state.loadingMessage.remove();
    state.loadingMessage = null;
  }
}

function appendAssistantPayload(payload) {
  if (!payload || typeof payload.type !== "string") {
    appendAssistantError("The assistant returned an unexpected response.");
    return;
  }

  if (payload.type === "answer") {
    appendAssistantCard(renderResponseCard(payload));
    return;
  }

  if (payload.type === "refusal") {
    appendAssistantCard(renderRefusalCard(payload));
    return;
  }

  appendAssistantError("The assistant returned an unsupported response type.");
}

function appendAssistantError(message) {
  showChatHistory();

  if (!state.currentAnswerSlot) {
    const exchange = createElement("article", "exchange exchange--error-only");
    const answerBlock = createElement("div", "exchange-answer");
    exchange.append(answerBlock);
    elements.chatHistory.append(exchange);
    state.currentAnswerSlot = answerBlock;
  }

  const card = createElement("div", "error-card");
  const inner = createElement("div", "card-inner");
  inner.append(
    createElement("p", "card-title", "Request failed"),
    createElement("p", "card-body", message || "The request failed. Please try again."),
  );
  card.append(inner);
  appendAssistantCard(card);
}

function appendAssistantCard(card) {
  appendToAnswerSlot(card);
  state.currentAnswerSlot = null;
}

function renderResponseCard(payload) {
  const card = createElement("div", "response-card");
  card.dataset.testid = "response-card";

  const inner = createElement("div", "card-inner");
  const badge = createElement("div", "card-badge");
  const verifiedIcon = createElement("span", "material-symbols-outlined");
  verifiedIcon.textContent = "verified";
  badge.append(verifiedIcon, document.createTextNode("Answer from corpus"));

  const answerText = payload.answer || "No answer was returned.";
  const body = createElement("div", "card-body readable-prose");
  body.append(formatReadableText(answerText));
  inner.append(badge, body);

  const lastUpdated = String(payload.last_updated || payload.lastUpdated || "").trim();
  const updated = createElement("p", "meta-line last-updated");
  updated.dataset.testid = "last-updated";
  const calendarIcon = createElement("span", "material-symbols-outlined");
  calendarIcon.textContent = "calendar_month";
  calendarIcon.setAttribute("aria-hidden", "true");
  updated.append(
    calendarIcon,
    document.createTextNode(
      `Last updated from sources: ${lastUpdated || "Unknown"}`,
    ),
  );
  inner.append(updated);

  const footer = createElement("div", "card-footer");

  if (payload.source_url) {
    const source = createElement("a", "source-link");
    source.href = payload.source_url;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    const linkIcon = createElement("span", "material-symbols-outlined");
    linkIcon.textContent = "link";
    source.append(linkIcon, document.createTextNode(`Source: ${payload.source_url}`));
    footer.append(source);
  }

  if (footer.childNodes.length > 0) {
    inner.append(footer);
  }

  card.append(inner);
  return card;
}

function renderRefusalCard(payload) {
  const card = createElement("div", "refusal-card");
  card.dataset.testid = "refusal-card";

  const inner = createElement("div", "card-inner");
  const header = createElement("div", "refusal-header");

  const iconWrap = createElement("div", "refusal-icon-wrap");
  const securityIcon = createElement("span", "material-symbols-outlined");
  securityIcon.textContent = "security";
  iconWrap.append(securityIcon);

  const textBlock = createElement("div");
  textBlock.append(
    createElement("p", "card-title", "Regulatory compliance notice"),
  );
  const refusalBody = createElement("div", "card-body readable-prose");
  refusalBody.append(
    formatReadableText(
      payload.message || "This question is outside the assistant's allowed scope.",
    ),
  );
  textBlock.append(refusalBody);

  header.append(iconWrap, textBlock);
  inner.append(header);

  if (payload.educational_url) {
    const footer = createElement("div", "card-footer");
    const link = createElement("a", "");
    link.href = payload.educational_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const openIcon = createElement("span", "material-symbols-outlined");
    openIcon.textContent = "open_in_new";
    link.append(openIcon, document.createTextNode("Learn more at AMFI"));
    footer.append(link);
    inner.append(footer);
  }

  card.append(inner);
  return card;
}

function formatReadableText(text) {
  const paragraphs = String(text)
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (paragraphs.length === 0) {
    return document.createTextNode("");
  }

  const fragment = document.createDocumentFragment();
  paragraphs.forEach((paragraph, index) => {
    const element = createElement("p", "readable-paragraph", paragraph);
    if (index > 0) {
      element.classList.add("readable-paragraph--spaced");
    }
    fragment.append(element);
  });
  return fragment;
}

function createElement(tagName, className = "", text = "") {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text) {
    element.textContent = text;
  }
  return element;
}

warmupBackend({ apiBaseUrl: state.apiBaseUrl });
