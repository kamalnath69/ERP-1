import { createSelector, createSlice } from "@reduxjs/toolkit";

const initialState = {
  activeConversationId: null,
  messagesByConversation: { __new__: [] },
  streaming: false,
  streamStatus: "",
  streamError: null,
  draftAssistantId: null,
  pendingUserMessageId: null,
  streamConversationKey: null,
  pendingHistoryMessageId: null,
  pendingHistoryConversationId: null,
  resultDrawer: null,
};

const conversationKey = (state, id = state.activeConversationId) => id || "__new__";
const currentMessages = (state) => {
  const key = conversationKey(state);
  if (!state.messagesByConversation[key]) state.messagesByConversation[key] = [];
  return state.messagesByConversation[key];
};
const streamingMessages = (state) => {
  const key = state.streamConversationKey || conversationKey(state);
  if (!state.messagesByConversation[key]) state.messagesByConversation[key] = [];
  return state.messagesByConversation[key];
};

const aiSlice = createSlice({
  name: "aiWorkspace",
  initialState,
  reducers: {
    setActiveConversation: (state, action) => { state.activeConversationId = action.payload; state.streamError = null; },
    setMessages: (state, action) => {
      const payload = Array.isArray(action.payload) ? { messages: action.payload } : action.payload || {};
      const key = conversationKey(state, payload.conversationId);
      let messages = payload.messages || [];
      const isPendingConversation = state.pendingHistoryConversationId === key && state.pendingHistoryMessageId;
      const containsCompletedMessage = !isPendingConversation || messages.some((message) => message.id === state.pendingHistoryMessageId);

      // A cached history response can finish just after SSE completion. Keep the
      // live response until the server history includes that completed message.
      if (!containsCompletedMessage) return;
      if (payload.preserveOlder && messages.length) {
        const incomingIds = new Set(messages.map((message) => message.id));
        const firstTimestamp = messages[0]?.created_at ? new Date(messages[0].created_at).getTime() : null;
        const older = (state.messagesByConversation[key] || []).filter((message) => (
          !incomingIds.has(message.id)
          && message.created_at
          && firstTimestamp != null
          && new Date(message.created_at).getTime() < firstTimestamp
        ));
        messages = [...older, ...messages];
      }
      state.messagesByConversation[key] = messages;
      if (isPendingConversation) {
        state.pendingHistoryMessageId = null;
        state.pendingHistoryConversationId = null;
      }
    },
    prependMessages: (state, action) => {
      const payload = action.payload || {};
      const key = conversationKey(state, payload.conversationId);
      const existing = state.messagesByConversation[key] || [];
      const existingIds = new Set(existing.map((message) => message.id));
      state.messagesByConversation[key] = [
        ...(payload.messages || []).filter((message) => !existingIds.has(message.id)),
        ...existing,
      ];
    },
    appendUserMessage: (state, action) => { currentMessages(state).push(action.payload); },
    startStreaming: (state, action) => {
      const payload = typeof action.payload === "string"
        ? { assistantId: action.payload, userId: null }
        : action.payload;
      state.streaming = true; state.streamError = null; state.streamStatus = "Understanding your request";
      state.draftAssistantId = payload.assistantId;
      state.pendingUserMessageId = payload.userId;
      state.streamConversationKey = conversationKey(state);
      currentMessages(state).push({ id: payload.assistantId, role: "assistant", content: "", blocks: [], actions: [], citations: [] });
    },
    setStreamStatus: (state, action) => { state.streamStatus = action.payload; },
    appendTextDelta: (state, action) => {
      const message = streamingMessages(state).find((item) => item.id === state.draftAssistantId);
      if (message) message.content += action.payload;
    },
    appendStreamBlock: (state, action) => {
      const message = streamingMessages(state).find((item) => item.id === state.draftAssistantId);
      if (message && !message.blocks.some((item) => item.id === action.payload.id)) message.blocks.push(action.payload);
    },
    appendStreamAction: (state, action) => {
      const message = streamingMessages(state).find((item) => item.id === state.draftAssistantId);
      if (message) message.actions.push(action.payload);
    },
    completeStreaming: (state, action) => {
      const activeKey = conversationKey(state); const oldKey = state.streamConversationKey || activeKey; const messages = streamingMessages(state);
      const index = messages.findIndex((item) => item.id === state.draftAssistantId);
      if (index >= 0) messages[index] = action.payload.message;
      state.messagesByConversation[action.payload.conversation_id] = messages;
      if (oldKey === "__new__") state.messagesByConversation.__new__ = [];
      if (activeKey === oldKey) state.activeConversationId = action.payload.conversation_id;
      state.pendingHistoryMessageId = action.payload.message?.id || null;
      state.pendingHistoryConversationId = action.payload.conversation_id || null;
      state.streaming = false; state.streamStatus = ""; state.draftAssistantId = null; state.pendingUserMessageId = null; state.streamConversationKey = null;
    },
    failStreaming: (state, action) => {
      const key = state.streamConversationKey || conversationKey(state);
      state.messagesByConversation[key] = streamingMessages(state).filter((item) => item.id !== state.draftAssistantId && item.id !== state.pendingUserMessageId);
      state.streaming = false; state.streamStatus = ""; state.draftAssistantId = null; state.pendingUserMessageId = null; state.streamConversationKey = null; state.streamError = action.payload;
    },
    cancelStreaming: (state) => {
      const key = state.streamConversationKey || conversationKey(state);
      state.messagesByConversation[key] = streamingMessages(state).filter((item) => item.id !== state.draftAssistantId && item.id !== state.pendingUserMessageId);
      state.streaming = false; state.streamStatus = ""; state.draftAssistantId = null; state.pendingUserMessageId = null; state.streamConversationKey = null; state.streamError = null;
    },
    removeConversation: (state, action) => {
      delete state.messagesByConversation[action.payload];
      if (state.activeConversationId === action.payload) state.activeConversationId = null;
    },
    removeTurn: (state, action) => {
      const { conversationId, turnId } = action.payload;
      state.messagesByConversation[conversationId] = (state.messagesByConversation[conversationId] || [])
        .filter((message) => message.turn_id !== turnId);
    },
    setMessageFeedback: (state, action) => {
      const { conversationId, messageId, rating } = action.payload;
      const messages = state.messagesByConversation[conversationId] || [];
      const message = messages.find((item) => item.id === messageId);
      if (message) message.feedback_rating = rating;
    },
    updateAction: (state, action) => {
      for (const messages of Object.values(state.messagesByConversation)) {
        for (const message of messages) {
          message.actions = (message.actions || []).map((item) => item.action_id === action.payload.action_id ? { ...item, ...action.payload } : item);
          message.blocks = (message.blocks || []).map((block) => block.type === "action" && block.data?.action_id === action.payload.action_id
            ? { ...block, data: { ...block.data, ...action.payload } } : block);
        }
      }
    },
    openResultDrawer: (state, action) => { state.resultDrawer = action.payload; },
    closeResultDrawer: (state) => { state.resultDrawer = null; },
    resetAIWorkspace: () => initialState,
  },
});

export const {
  setActiveConversation, setMessages, prependMessages, appendUserMessage, startStreaming, setStreamStatus,
  appendTextDelta, appendStreamBlock, appendStreamAction, completeStreaming, failStreaming, cancelStreaming,
  removeConversation, removeTurn, setMessageFeedback, updateAction, openResultDrawer, closeResultDrawer, resetAIWorkspace,
} = aiSlice.actions;
export const selectAIWorkspace = createSelector([(state) => state.aiWorkspace], (workspace) => {
  return { ...workspace, messages: workspace.messagesByConversation[workspace.activeConversationId || "__new__"] || [] };
});
export default aiSlice.reducer;
