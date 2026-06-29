/**
 * Writes config.js from API_BASE_URL (Vercel build env var).
 */
const fs = require("fs");
const path = require("path");

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

const apiBaseUrl = normalizeApiBaseUrl(process.env.API_BASE_URL);

if (process.env.VERCEL && !apiBaseUrl) {
  console.error("ERROR: Set API_BASE_URL in Vercel env vars");
  process.exit(1);
}

const target = path.join(__dirname, "config.js");
const contents = [
  "// Auto-generated at build time",
  `window.__API_BASE_URL__ = ${JSON.stringify(apiBaseUrl)};`,
  "",
].join("\n");

fs.writeFileSync(target, contents, "utf8");
console.log(apiBaseUrl ? `Wrote config.js with API_BASE_URL=${apiBaseUrl}` : "Wrote config.js (local fallback)");
