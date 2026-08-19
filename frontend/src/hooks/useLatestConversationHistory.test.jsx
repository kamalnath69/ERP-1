import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { vi } from "vitest";

import useLatestConversationHistory, {
  isCancelledHistoryRequest,
} from "./useLatestConversationHistory";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function deferredRequest() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {
    abort: vi.fn(),
    reject,
    resolve,
    unwrap: () => promise,
  };
}

test("aborts superseded history and accepts only the latest conversation", async () => {
  const requests = [];
  const accepted = vi.fn();
  const loadPage = vi.fn((args, preferCache) => {
    const request = deferredRequest();
    requests.push({ args, preferCache, request });
    return request;
  });
  let latestState;

  function Probe({ conversationId }) {
    latestState = useLatestConversationHistory({
      conversationId,
      loadPage,
      onPage: accepted,
    });
    return <span>{latestState.status}</span>;
  }

  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<Probe conversationId="chat-a" />));
  expect(requests).toHaveLength(1);
  expect(requests[0].preferCache).toBe(true);

  await act(async () => root.render(<Probe conversationId="chat-b" />));
  expect(requests[0].request.abort).toHaveBeenCalledTimes(1);
  expect(requests).toHaveLength(2);

  await act(async () => {
    requests[0].request.resolve({ items: [{ id: "old" }] });
    await Promise.resolve();
  });
  expect(accepted).not.toHaveBeenCalled();

  await act(async () => {
    requests[1].request.resolve({ items: [{ id: "new" }], next_cursor: "next" });
    await Promise.resolve();
  });
  expect(accepted).toHaveBeenCalledTimes(1);
  expect(accepted).toHaveBeenCalledWith("chat-b", {
    items: [{ id: "new" }],
    next_cursor: "next",
  });
  expect(latestState.status).toBe("ready");

  await act(async () => root.unmount());
});

test("uses cache on selection and bypasses it for an explicit refresh", async () => {
  const requests = [];
  const loadPage = vi.fn((args, preferCache) => {
    const request = deferredRequest();
    requests.push({ args, preferCache, request });
    return request;
  });
  let latestState;

  function Probe() {
    latestState = useLatestConversationHistory({
      conversationId: "chat-a",
      hasCachedMessages: true,
      loadPage,
      onPage: vi.fn(),
    });
    return <span>{latestState.status}</span>;
  }

  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<Probe />));
  expect(latestState.status).toBe("refreshing");

  await act(async () => {
    latestState.refresh();
    await Promise.resolve();
  });
  expect(requests[0].request.abort).toHaveBeenCalledTimes(1);
  expect(requests[1].preferCache).toBe(false);

  await act(async () => {
    requests[1].request.resolve({ items: [] });
    await Promise.resolve();
  });
  expect(latestState.status).toBe("ready");

  await act(async () => root.unmount());
});

test("recognizes request cancellation shapes", () => {
  expect(isCancelledHistoryRequest({ name: "AbortError" })).toBe(true);
  expect(isCancelledHistoryRequest({ code: "ERR_CANCELED" })).toBe(true);
  expect(isCancelledHistoryRequest({ status: "CANCELLED" })).toBe(true);
  expect(isCancelledHistoryRequest(new Error("Network failed"))).toBe(false);
});

test("recovers when StrictMode reuses a request canceled during its startup probe", async () => {
  const canceled = deferredRequest();
  canceled.abort.mockImplementation(() => {
    canceled.reject({ status: "CANCELLED" });
  });
  const retry = deferredRequest();
  const loadPage = vi
    .fn()
    .mockReturnValueOnce(canceled)
    .mockReturnValueOnce(canceled)
    .mockReturnValueOnce(retry);
  const accepted = vi.fn();
  let latestState;

  function Probe() {
    latestState = useLatestConversationHistory({
      conversationId: "chat-a",
      loadPage,
      onPage: accepted,
    });
    return <span>{latestState.status}</span>;
  }

  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => {
    root.render(<React.StrictMode><Probe /></React.StrictMode>);
    await Promise.resolve();
  });

  expect(loadPage).toHaveBeenCalledTimes(3);
  expect(loadPage.mock.calls[2][1]).toBe(false);
  expect(latestState.status).toBe("loading");

  await act(async () => {
    retry.resolve({ items: [{ id: "message-1" }] });
    await Promise.resolve();
  });
  expect(accepted).toHaveBeenCalledWith("chat-a", {
    items: [{ id: "message-1" }],
  });
  expect(latestState.status).toBe("ready");

  await act(async () => root.unmount());
});
