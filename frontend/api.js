const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:8000";

function normalizeApiBaseUrl(value) {
  const trimmed = String(value || "").trim().replace(/\/$/, "");
  if (!trimmed) {
    return "";
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  return `https://${trimmed}`;
}

export function resolveApiBaseUrl(location = window.location) {
  const params = new URLSearchParams(location.search);
  const configured = params.get("apiBase") || window.__API_BASE_URL__;
  if (configured) {
    return normalizeApiBaseUrl(configured);
  }

  const host = location.hostname;
  const isLocalHost = host === "localhost" || host === "127.0.0.1";
  if (isLocalHost) {
    return DEFAULT_BACKEND_ORIGIN;
  }

  throw new Error("API_BASE_URL is not configured for this deployment.");
}

export async function askQuestion(query, { apiBaseUrl = resolveApiBaseUrl(), fetchImpl = fetch } = {}) {
  let response;
  try {
    response = await fetchImpl(`${apiBaseUrl}/api/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });
  } catch {
    throw new Error(
      "Could not reach the API backend. Confirm Railway is running and API_BASE_URL is set correctly in Vercel.",
    );
  }

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
