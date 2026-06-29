const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:8000";

export function resolveApiBaseUrl(location = window.location) {
  const params = new URLSearchParams(location.search);
  const configured = params.get("apiBase") || window.__API_BASE_URL__;
  if (configured) {
    return String(configured).replace(/\/$/, "");
  }

  if (location.protocol.startsWith("http")) {
    const host = location.hostname;
    const isLocalHost = host === "localhost" || host === "127.0.0.1";
    if (isLocalHost && (location.port === "3000" || location.port === "" || location.port === "8000")) {
      return DEFAULT_BACKEND_ORIGIN;
    }
  }

  return DEFAULT_BACKEND_ORIGIN;
}

export async function askQuestion(query, { apiBaseUrl = resolveApiBaseUrl(), fetchImpl = fetch } = {}) {
  const response = await fetchImpl(`${apiBaseUrl}/api/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail || "The assistant could not complete the request. Please try again.");
  }

  return payload;
}
