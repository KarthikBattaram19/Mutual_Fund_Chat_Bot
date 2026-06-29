/**
 * Writes config.js from API_BASE_URL (Vercel build env var).
 */
const fs = require("fs");
const path = require("path");

const apiBaseUrl = (process.env.API_BASE_URL || "").trim().replace(/\/$/, "");

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
