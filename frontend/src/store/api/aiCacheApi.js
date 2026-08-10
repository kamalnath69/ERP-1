import { baseApi, domainRequest, resourceTags } from "./baseApi";

const request = (api, url, params) => domainRequest({ url, method: "GET", params }, api);
const write = (api, url, method = "DELETE", data) => domainRequest({ url, method, data }, api);

export const aiCacheApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getAIWorkspace: builder.query({
      async queryFn(_arg, api) {
        const [documents, savedViews] = await Promise.all([
          request(api, "/documents/page", { limit: 25 }), request(api, "/ai/views"),
        ]);
        const failed = [documents, savedViews].find((result) => result.error);
        if (failed) return failed;
        return { data: { documents: documents.data?.items || [], savedViews: savedViews.data } };
      },
      providesTags: [...resourceTags("ai"), ...resourceTags("documents")],
      keepUnusedDataFor: 300,
    }),
    getAIConversations: builder.query({
      queryFn: ({ scope = "active", q = "", cursor, limit = 25 } = {}, api) => request(api, "/ai/conversations/page", {
        scope,
        q: q || undefined,
        cursor: cursor || undefined,
        limit,
      }),
      providesTags: (result) => [
        ...resourceTags("ai"),
        ...(result?.items || []).map((item) => ({ type: "Resource", id: `ai:${item.id}` })),
      ],
      keepUnusedDataFor: 120,
    }),
    getAIConversation: builder.query({
      queryFn: (conversationId, api) => request(api, `/ai/conversations/${conversationId}`),
      providesTags: (_result, _error, conversationId) => resourceTags("ai", conversationId),
      keepUnusedDataFor: 300,
    }),
    getConversationMessages: builder.query({
      queryFn: (conversationId, api) => request(api, `/ai/conversations/${conversationId}/messages`),
      providesTags: (_result, _error, conversationId) => resourceTags("ai", conversationId),
      keepUnusedDataFor: 600,
    }),
    getConversationMessagePage: builder.query({
      queryFn: ({ conversationId, cursor, limit = 50 }, api) => request(api, `/ai/conversations/${conversationId}/messages/page`, {
        cursor: cursor || undefined,
        limit,
      }),
      providesTags: (_result, _error, { conversationId }) => resourceTags("ai", conversationId),
      keepUnusedDataFor: 600,
    }),
    deleteAIConversation: builder.mutation({
      queryFn: (conversationId, api) => write(api, `/ai/conversations/${conversationId}`),
      invalidatesTags: resourceTags("ai"),
    }),
    updateAIConversation: builder.mutation({
      queryFn: ({ conversationId, changes }, api) => write(api, `/ai/conversations/${conversationId}`, "PATCH", changes),
      invalidatesTags: (_result, _error, { conversationId }) => [
        ...resourceTags("ai"),
        ...resourceTags("ai", conversationId),
      ],
    }),
    deleteAIConversationTurn: builder.mutation({
      queryFn: ({ conversationId, turnId }, api) => write(api, `/ai/conversations/${conversationId}/turns/${turnId}`),
      async onQueryStarted({ conversationId, turnId }, { dispatch, queryFulfilled }) {
        const messagesPatch = dispatch(aiCacheApi.util.updateQueryData("getConversationMessages", conversationId, (draft) => {
          if (Array.isArray(draft)) return draft.filter((message) => message.turn_id !== turnId);
          return draft;
        }));
        try {
          await queryFulfilled;
          dispatch(aiCacheApi.util.invalidateTags(resourceTags("ai")));
        } catch { messagesPatch.undo(); }
      },
    }),
    submitAIMessageFeedback: builder.mutation({
      queryFn: ({ messageId, rating, reason }, api) => write(api, `/ai/messages/${messageId}/feedback`, "POST", {
        rating,
        reason: reason || undefined,
      }),
      async onQueryStarted({ conversationId, messageId, rating }, { dispatch, queryFulfilled }) {
        const patch = dispatch(aiCacheApi.util.updateQueryData("getConversationMessages", conversationId, (draft) => {
          const message = Array.isArray(draft) ? draft.find((item) => item.id === messageId) : null;
          if (message) message.feedback_rating = rating;
        }));
        try { await queryFulfilled; } catch { patch.undo(); }
      },
    }),
  }),
});

export const {
  useGetAIWorkspaceQuery, useGetAIConversationsQuery, useGetAIConversationQuery, useGetConversationMessagesQuery,
  useGetConversationMessagePageQuery, useLazyGetConversationMessagePageQuery,
  useDeleteAIConversationMutation, useUpdateAIConversationMutation,
  useDeleteAIConversationTurnMutation, useSubmitAIMessageFeedbackMutation,
} = aiCacheApi;
