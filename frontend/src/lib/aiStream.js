import { API_BASE } from "@/lib/http";
import http from "@/lib/http";

function cookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const match = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : "";
}

export async function streamAI(payload, onEvent, signal) {
  const options = {
    method: "POST", credentials: "include", signal,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": cookie("edvatiq_csrf") },
    body: JSON.stringify(payload),
  };
  let response = await fetch(`${API_BASE}/ai/chat/stream`, options);
  if (response.status === 401 && !signal?.aborted) {
    await http.post("/auth/refresh");
    options.headers["X-CSRF-Token"] = cookie("edvatiq_csrf");
    response = await fetch(`${API_BASE}/ai/chat/stream`, options);
  }
  if (!response.ok) {
    let detail = "Edvatiq could not start the request";
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  if (!response.body) throw new Error("Streaming is not supported by this browser");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = parseSSEBuffer(buffer, onEvent, done);
    if (done) break;
  }
}

export function parseSSEBuffer(value, onEvent, flush = false) {
  let buffer = value.replace(/\r\n/g, "\n").replace(/\r(?!$)/g, "\n");
  if (flush && buffer.trim()) buffer += "\n\n";
  const frames = buffer.split("\n\n");
  const remainder = frames.pop() || "";
  for (const frame of frames) {
    let event = "message";
    const data = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length) onEvent(event, JSON.parse(data.join("\n")));
  }
  return remainder;
}
