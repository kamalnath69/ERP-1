import reducer, {
  appendTextDelta, appendUserMessage, cancelStreaming, completeStreaming, selectAIWorkspace, setActiveConversation,
  removeTurn, setMessageFeedback, setMessages, startStreaming,
} from "./aiSlice";

describe("AI workspace conversation cache", () => {
  test("keeps messages isolated when switching conversations", () => {
    let state = reducer(undefined, setMessages({ conversationId: "first", messages: [{ id: "1", role: "user", content: "First" }] }));
    state = reducer(state, setMessages({ conversationId: "second", messages: [{ id: "2", role: "user", content: "Second" }] }));
    state = reducer(state, setActiveConversation("first"));

    expect(selectAIWorkspace({ aiWorkspace: state }).messages[0].content).toBe("First");

    state = reducer(state, setActiveConversation("second"));
    expect(selectAIWorkspace({ aiWorkspace: state }).messages[0].content).toBe("Second");
  });

  test("moves a streamed new conversation into its server conversation cache", () => {
    let state = reducer(undefined, appendUserMessage({ id: "user-1", role: "user", content: "Hello" }));
    state = reducer(state, startStreaming("draft-1"));
    state = reducer(state, completeStreaming({
      conversation_id: "conversation-1",
      message: { id: "assistant-1", role: "assistant", content: "Hi" },
    }));

    expect(state.activeConversationId).toBe("conversation-1");
    expect(state.messagesByConversation["conversation-1"].map((message) => message.content)).toEqual(["Hello", "Hi"]);
    expect(state.messagesByConversation.__new__).toEqual([]);
  });

  test("keeps stream deltas attached to their original conversation", () => {
    let state = reducer(undefined, setMessages({ conversationId: "first", messages: [] }));
    state = reducer(state, setActiveConversation("first"));
    state = reducer(state, startStreaming("draft-1"));
    state = reducer(state, setActiveConversation("second"));
    state = reducer(state, appendTextDelta("Still first"));

    expect(state.messagesByConversation.first[0].content).toBe("Still first");
    expect(state.messagesByConversation.second).toBeUndefined();
  });

  test("keeps a live completion until refreshed history contains it", () => {
    const oldHistory = [{ id: "question-1", role: "user", content: "Who is new?" }];
    let state = reducer(undefined, setMessages({ conversationId: "first", messages: oldHistory }));
    state = reducer(state, setActiveConversation("first"));
    state = reducer(state, appendUserMessage({ id: "question-live", role: "user", content: "Show clients" }));
    state = reducer(state, startStreaming("draft-1"));
    state = reducer(state, appendTextDelta("Three clients found"));

    expect(selectAIWorkspace({ aiWorkspace: state }).messages.at(-1).content).toBe("Three clients found");

    state = reducer(state, completeStreaming({
      conversation_id: "first",
      message: { id: "answer-1", role: "assistant", content: "Three clients found" },
    }));
    state = reducer(state, setMessages({ conversationId: "first", messages: oldHistory }));

    expect(selectAIWorkspace({ aiWorkspace: state }).messages.at(-1).id).toBe("answer-1");
    expect(state.pendingHistoryMessageId).toBe("answer-1");

    const refreshedHistory = [...oldHistory, { id: "answer-1", role: "assistant", content: "Three clients found" }];
    state = reducer(state, setMessages({ conversationId: "first", messages: refreshedHistory }));

    expect(state.messagesByConversation.first).toEqual(refreshedHistory);
    expect(state.pendingHistoryMessageId).toBeNull();
  });

  test("cancels a switched conversation without leaking an error", () => {
    let state = reducer(undefined, setActiveConversation("first"));
    state = reducer(state, startStreaming("draft-1"));
    state = reducer(state, setActiveConversation("second"));
    state = reducer(state, cancelStreaming());

    expect(state.messagesByConversation.first).toEqual([]);
    expect(state.activeConversationId).toBe("second");
    expect(state.streaming).toBe(false);
    expect(state.streamError).toBeNull();
  });

  test("stop removes the optimistic turn so the prompt can be retried cleanly", () => {
    let state = reducer(undefined, appendUserMessage({ id: "user-live", role: "user", content: "Show sales" }));
    state = reducer(state, startStreaming({ assistantId: "draft-live", userId: "user-live" }));
    state = reducer(state, appendTextDelta("Partial response"));
    state = reducer(state, cancelStreaming());

    expect(state.messagesByConversation.__new__).toEqual([]);
    expect(state.pendingUserMessageId).toBeNull();
    expect(state.streaming).toBe(false);
  });

  test("stores assistant feedback in the conversation cache", () => {
    let state = reducer(undefined, setMessages({
      conversationId: "first",
      messages: [{ id: "answer", role: "assistant", content: "Three clients" }],
    }));

    state = reducer(state, setMessageFeedback({
      conversationId: "first",
      messageId: "answer",
      rating: "helpful",
    }));

    expect(state.messagesByConversation.first[0].feedback_rating).toBe("helpful");
  });

  test("removes a complete question and answer turn from the local cache", () => {
    let state = reducer(undefined, setMessages({ conversationId: "first", messages: [
      { id: "question", turn_id: "turn-1", role: "user", content: "Who is Kavin?" },
      { id: "answer", turn_id: "turn-1", role: "assistant", content: "Kavin is a client." },
      { id: "other", turn_id: "turn-2", role: "user", content: "Show visits" },
    ] }));

    state = reducer(state, removeTurn({ conversationId: "first", turnId: "turn-1" }));

    expect(state.messagesByConversation.first).toHaveLength(1);
    expect(state.messagesByConversation.first[0].id).toBe("other");
  });
});
