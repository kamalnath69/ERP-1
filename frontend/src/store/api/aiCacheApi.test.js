import { configureStore } from "@reduxjs/toolkit";
import http from "../../lib/http";
import { baseApi } from "./baseApi";
import { aiCacheApi } from "./aiCacheApi";

jest.mock("../../lib/http", () => ({
  __esModule: true,
  default: { request: jest.fn() },
}));

function testStore() {
  return configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefault) => getDefault().concat(baseApi.middleware),
  });
}

describe("AI conversation API", () => {
  beforeEach(() => {
    http.request.mockReset();
    http.request.mockResolvedValue({
      data: { items: [], next_cursor: null, has_more: false },
      status: 200,
      headers: {},
    });
  });

  test("searches across the requested conversation scope", async () => {
    const store = testStore();

    await store.dispatch(aiCacheApi.endpoints.getAIConversations.initiate({
      scope: "all",
      q: "renewal invoice",
      limit: 100,
    })).unwrap();

    expect(http.request).toHaveBeenCalledWith(expect.objectContaining({
      method: "GET",
      url: "/ai/conversations/page",
      params: expect.objectContaining({ scope: "all", q: "renewal invoice", limit: 100 }),
    }));
  });

  test("loads older messages with an opaque cursor", async () => {
    const store = testStore();

    await store.dispatch(aiCacheApi.endpoints.getConversationMessagePage.initiate({
      conversationId: "chat-1",
      cursor: "older-page",
      limit: 50,
    })).unwrap();

    expect(http.request).toHaveBeenCalledWith(expect.objectContaining({
      method: "GET",
      url: "/ai/conversations/chat-1/messages/page",
      params: { cursor: "older-page", limit: 50 },
    }));
  });

  test("sends only explicit conversation metadata changes", async () => {
    http.request.mockResolvedValue({ data: { id: "chat-1", pinned_at: "2026-08-06T10:00:00Z" }, status: 200, headers: {} });
    const store = testStore();

    await store.dispatch(aiCacheApi.endpoints.updateAIConversation.initiate({
      conversationId: "chat-1",
      changes: { pinned: true },
    })).unwrap();

    expect(http.request).toHaveBeenCalledWith(expect.objectContaining({
      method: "PATCH",
      url: "/ai/conversations/chat-1",
      data: { pinned: true },
    }));
  });

  test("loads scoped metadata for a directly opened chat", async () => {
    http.request.mockResolvedValue({ data: { id: "chat-archived", archived_at: "2026-08-06T10:00:00Z" }, status: 200, headers: {} });
    const store = testStore();

    await store.dispatch(aiCacheApi.endpoints.getAIConversation.initiate("chat-archived")).unwrap();

    expect(http.request).toHaveBeenCalledWith(expect.objectContaining({
      method: "GET",
      url: "/ai/conversations/chat-archived",
    }));
  });

  test("persists assistant feedback with an optional reason", async () => {
    http.request.mockResolvedValue({ data: { ok: true, rating: "not_helpful" }, status: 200, headers: {} });
    const store = testStore();

    await store.dispatch(aiCacheApi.endpoints.submitAIMessageFeedback.initiate({
      conversationId: "chat-1",
      messageId: "message-1",
      rating: "not_helpful",
      reason: "Wrong invoice scope",
    })).unwrap();

    expect(http.request).toHaveBeenCalledWith(expect.objectContaining({
      method: "POST",
      url: "/ai/messages/message-1/feedback",
      data: { rating: "not_helpful", reason: "Wrong invoice scope" },
    }));
  });
});
