import { AIStreamError, parseSSEBuffer } from "./aiStream";

test("parses SSE events split across network chunks and CRLF boundaries", () => {
  const events = [];
  let buffer = parseSSEBuffer('event: status\r\ndata: {"message":"Checking"}\r\n', (event, data) => events.push([event, data]));
  expect(events).toEqual([]);

  buffer = parseSSEBuffer(`${buffer}\r\nevent: answer_delta\r\ndata: {"text":"Hello"}\r\n\r\n`, (event, data) => events.push([event, data]));

  expect(buffer).toBe("");
  expect(events).toEqual([
    ["status", { message: "Checking" }],
    ["answer_delta", { text: "Hello" }],
  ]);
});

test("ignores keepalive comments and flushes the final event", () => {
  const events = [];
  parseSSEBuffer(': keepalive\n\nevent: complete\ndata: {"conversation_id":"1"}', (event, data) => events.push([event, data]), true);
  expect(events).toEqual([["complete", { conversation_id: "1" }]]);
});

test("preserves retry metadata from a staged stream failure", () => {
  const error = new AIStreamError({
    message: "The planner timed out.",
    code: "planner_timeout",
    stage: "planner",
    retryable: true,
  });

  expect(error.message).toBe("The planner timed out.");
  expect(error.code).toBe("planner_timeout");
  expect(error.stage).toBe("planner");
  expect(error.retryable).toBe(true);
});
