import { parseSSEBuffer } from "./aiStream";

test("parses SSE events split across network chunks and CRLF boundaries", () => {
  const events = [];
  let buffer = parseSSEBuffer('event: status\r\ndata: {"message":"Checking"}\r\n', (event, data) => events.push([event, data]));
  expect(events).toEqual([]);

  buffer = parseSSEBuffer(`${buffer}\r\nevent: text_delta\r\ndata: {"text":"Hello"}\r\n\r\n`, (event, data) => events.push([event, data]));

  expect(buffer).toBe("");
  expect(events).toEqual([
    ["status", { message: "Checking" }],
    ["text_delta", { text: "Hello" }],
  ]);
});

test("ignores keepalive comments and flushes the final event", () => {
  const events = [];
  parseSSEBuffer(': keepalive\n\nevent: complete\ndata: {"conversation_id":"1"}', (event, data) => events.push([event, data]), true);
  expect(events).toEqual([["complete", { conversation_id: "1" }]]);
});
