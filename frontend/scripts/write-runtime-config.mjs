import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";


export function normalizePublicApiUrl(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) throw new Error("PUBLIC_API_URL is required");

  const url = new URL(text);
  if (url.protocol !== "https:") {
    throw new Error("PUBLIC_API_URL must use HTTPS");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("PUBLIC_API_URL must not contain credentials, query, or hash");
  }
  return url.toString().replace(/\/+$/, "");
}


export function serializeRuntimeConfig(value) {
  const apiUrl = normalizePublicApiUrl(value);
  return `globalThis.__PARKINGAI_CONFIG__ = Object.freeze({ API_URL: ${JSON.stringify(apiUrl)} });\n`;
}


export async function writeRuntimeConfig(outputPath, value) {
  if (!outputPath) throw new Error("Runtime config output path is required");
  await writeFile(outputPath, serializeRuntimeConfig(value), "utf8");
}


async function main() {
  await writeRuntimeConfig(process.argv[2], process.env.PUBLIC_API_URL);
}


if (
  process.argv[1]
  && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
