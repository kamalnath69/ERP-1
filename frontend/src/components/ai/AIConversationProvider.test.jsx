import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import aiReducer from "@/store/slices/aiSlice";
import { baseApi } from "@/store/api/baseApi";
import {
  AIConversationProvider,
  contextIdentity,
  useAIConversation,
  useRegisterAIPageContext,
} from "./AIConversationProvider";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const streamHarness = vi.hoisted(() => ({ calls: [], finish: null, fail: null }));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));

vi.mock("@/contexts/BusinessContext", () => ({
  useBusiness: () => ({ locationId: "location-1" }),
}));

vi.mock("@/lib/aiStream", () => ({
  AIStreamError: class AIStreamError extends Error {
    constructor(payload) {
      super(payload?.message || "Stream failed");
      this.code = payload?.code;
      this.stage = payload?.stage;
      this.retryable = payload?.retryable !== false;
    }
  },
  streamAI: (payload, emit) => {
    streamHarness.calls.push(payload);
    return new Promise((resolve, reject) => {
      streamHarness.finish = () => {
        emit("complete", {
          conversation_id: "conversation-1",
          message: {
            id: "assistant-1",
            role: "assistant",
            content: "Current answer",
            artifacts: [],
            suggestions: [],
            evidence: [],
          },
        });
        resolve();
      };
      streamHarness.fail = (errorPayload) => {
        try {
          emit("error", errorPayload);
        } catch (error) {
          reject(error);
        }
      };
    });
  },
}));

function makeStore() {
  return configureStore({
    reducer: {
      aiWorkspace: aiReducer,
      [baseApi.reducerPath]: baseApi.reducer,
    },
    middleware: (getDefault) => getDefault().concat(baseApi.middleware),
  });
}

let currentConversation = null;

function Probe({ context }) {
  useRegisterAIPageContext(context);
  currentConversation = useAIConversation();
  return <span>{currentConversation.pageContext?.label || "No context"}</span>;
}

function Harness({ store, context }) {
  return (
    <Provider store={store}>
      <MemoryRouter initialEntries={["/app/clients?batch=2027"]}>
        <AIConversationProvider>
          <Probe context={context} />
        </AIConversationProvider>
      </MemoryRouter>
    </Provider>
  );
}

beforeEach(() => {
  streamHarness.calls = [];
  streamHarness.finish = null;
  streamHarness.fail = null;
  currentConversation = null;
  window.sessionStorage.clear();
});

test("registers only authorized page data and removes it with the page", async () => {
  const store = makeStore();
  const container = document.createElement("div");
  const root = createRoot(container);
  const context = {
    kind: "college_scope",
    id: "graduation:2027",
    label: "2027 batch",
    graduation_year: 2027,
  };

  await act(async () => root.render(<Harness store={store} context={context} />));
  expect(currentConversation.pageContext).toEqual(context);
  expect(container.textContent).toContain("2027 batch");

  await act(async () => root.render(<Harness store={store} context={null} />));
  expect(currentConversation.pageContext).toBeNull();
  await act(async () => root.unmount());
});

test("allows only one active stream and stores the resulting active conversation", async () => {
  const store = makeStore();
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<Harness store={store} context={null} />));

  let firstRequest;
  await act(async () => {
    firstRequest = currentConversation.sendMessage("Show current students");
    await Promise.resolve();
  });
  expect(streamHarness.calls).toHaveLength(1);
  expect(streamHarness.calls[0]).toMatchObject({
    message: "Show current students",
    context: { route: "/app/clients?batch=2027", location_id: "location-1" },
  });

  let duplicateAccepted;
  await act(async () => {
    duplicateAccepted = await currentConversation.sendMessage("Run this twice");
  });
  expect(duplicateAccepted).toBe(false);
  expect(streamHarness.calls).toHaveLength(1);

  await act(async () => {
    streamHarness.finish();
    await firstRequest;
  });
  expect(currentConversation.activeConversationId).toBe("conversation-1");
  expect(currentConversation.messages.at(-1)?.content).toBe("Current answer");
  expect(window.sessionStorage.getItem("edvatiq.ai.active_conversation.v1:user-1")).toBe("conversation-1");
  await act(async () => root.unmount());
});

test("uses a stable identity for academic scope changes", () => {
  const first = contextIdentity({
    kind: "college_scope",
    id: "graduation:2027",
    graduation_year: 2027,
    cohort_ids: ["a", "b"],
  });
  const same = contextIdentity({
    kind: "college_scope",
    id: "graduation:2027",
    label: "A changed display label",
    graduation_year: 2027,
    cohort_ids: ["a", "b"],
  });
  const changed = contextIdentity({
    kind: "college_scope",
    id: "graduation:2027",
    graduation_year: 2027,
    cohort_ids: ["a", "c"],
  });

  expect(first).toBe(same);
  expect(changed).not.toBe(first);
});

test("restores the exact prompt and retry metadata after a staged failure", async () => {
  const store = makeStore();
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => root.render(<Harness store={store} context={null} />));

  let request;
  await act(async () => {
    request = currentConversation.sendMessage("who Aarav");
    await Promise.resolve();
  });
  await act(async () => {
    streamHarness.fail({
      message: "Edvatiq took too long to prepare this answer.",
      code: "planner_timeout",
      stage: "planner",
      retryable: true,
    });
    await request;
  });

  expect(currentConversation.streaming).toBe(false);
  expect(currentConversation.draft).toBe("who Aarav");
  expect(currentConversation.streamError).toMatchObject({
    code: "planner_timeout",
    stage: "planner",
    retryable: true,
    question: "who Aarav",
  });
  expect(currentConversation.messages).toEqual([]);
  await act(async () => root.unmount());
});
