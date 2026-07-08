import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  currentConversationId: null,
  messages: [], // { role: 'user'|'assistant'|'tool', content, id, tool? }
  isSending: false,
  suggestedPrompts: [
    "Which students are at risk this month?",
    "Show department-wise attendance summary",
    "Top performing students in ECE",
    "Faculty workload by department",
  ],
};

const slice = createSlice({
  name: "ai",
  initialState,
  reducers: {
    setConversationId: (s, a) => {
      s.currentConversationId = a.payload;
    },
    appendMessage: (s, a) => {
      s.messages.push(a.payload);
    },
    setMessages: (s, a) => {
      s.messages = a.payload;
    },
    setSending: (s, a) => {
      s.isSending = a.payload;
    },
    resetConversation: (s) => {
      s.currentConversationId = null;
      s.messages = [];
      s.isSending = false;
    },
    streamChunkReceived: (s, a) => {
      // Placeholder for future streaming; append to last assistant message.
      const last = s.messages[s.messages.length - 1];
      if (last && last.role === "assistant") last.content = (last.content || "") + a.payload;
    },
  },
});

export const {
  setConversationId,
  appendMessage,
  setMessages,
  setSending,
  resetConversation,
  streamChunkReceived,
} = slice.actions;
export const selectMessages = (s) => s.ai.messages;
export const selectIsSending = (s) => s.ai.isSending;
export const selectSuggested = (s) => s.ai.suggestedPrompts;
export default slice.reducer;
