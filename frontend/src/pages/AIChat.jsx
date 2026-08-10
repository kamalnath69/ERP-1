import React, {
  useCallback,
  useDeferredValue,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { useDispatch, useSelector } from "react-redux";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { streamAI } from "@/lib/aiStream";
import { cn } from "@/lib/utils";
import { useBusiness } from "@/contexts/BusinessContext";
import SecondarySidebarLayout, { SecondarySidebarTrigger } from "@/components/layout/SecondarySidebarLayout";
import AssistantPersonalizationSheet from "@/components/ai/AssistantPersonalizationSheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import ResponseBlocks from "@/components/ai/ResponseBlocks";
import RichText from "@/components/ai/RichText";
import {
  EntityAvatar,
  EntityCard,
  EntityProfileLink,
  ProfileTableRow,
} from "@/components/entities/EntityProfile";
import {
  PROFILE_INTERNAL_FIELDS,
  visibleProfileFields,
} from "@/lib/profileNavigation";
import {
  appendStreamAction,
  appendStreamBlock,
  appendTextDelta,
  appendUserMessage,
  closeResultDrawer,
  cancelStreaming,
  completeStreaming,
  failStreaming,
  openResultDrawer,
  selectAIWorkspace,
  setActiveConversation,
  prependMessages,
  removeConversation,
  removeTurn,
  setMessageFeedback,
  setMessages,
  setStreamStatus,
  startStreaming,
  updateAction,
} from "@/store/slices/aiSlice";
import {
  Archive,
  ChatCircleDots,
  CircleNotch,
  Copy,
  DotsThreeVertical,
  FileArrowUp,
  List,
  MagnifyingGlass,
  Microphone,
  PaperPlaneRight,
  PencilSimple,
  PushPin,
  SidebarSimple,
  SlidersHorizontal,
  Sparkle,
  Stop,
  ThumbsDown,
  ThumbsUp,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  aiCacheApi,
  useDeleteAIConversationMutation,
  useDeleteAIConversationTurnMutation,
  useGetAIConversationQuery,
  useGetAIConversationsQuery,
  useGetAIWorkspaceQuery,
  useGetConversationMessagePageQuery,
  useLazyGetConversationMessagePageQuery,
  useSubmitAIMessageFeedbackMutation,
  useUpdateAIConversationMutation,
} from "@/store/api/aiCacheApi";
import { baseApi } from "@/store/api/baseApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import {
  selectAISidebarCollapsed,
  setAISidebarCollapsed,
} from "@/store/slices/preferencesSlice";
import useCursorPagination from "@/hooks/useCursorPagination";

const EMPTY_ITEMS = Object.freeze([]);
const businessSuggestions = [
  "Show today's business snapshot",
  "Compare revenue for the last 30 days",
  "Naalaiku appointments sollu",
  "Show clients who need attention",
];
const collegeSuggestions = [
  "Which students need placement support?",
  "Show placement-ready students",
  "Compare departments by readiness",
  "Which students have stale coding profiles?",
];

export default function AIChat() {
  const dispatch = useDispatch();
  const { locationId, industry } = useBusiness();
  const isCollege = industry === "college";
  const historyCollapsed = useSelector(selectAISidebarCollapsed);
  const {
    activeConversationId: active,
    messages,
    streaming,
    streamStatus,
    streamError,
    draftAssistantId,
    pendingHistoryMessageId,
    pendingHistoryConversationId,
    resultDrawer,
  } = useSelector(selectAIWorkspace);
  const workspaceQuery = useGetAIWorkspaceQuery(
    undefined,
    QUERY_POLICIES.operational,
  );
  const { data: sidebar, isLoading: workspaceLoading } = workspaceQuery;
  const refreshSidebar = workspaceQuery.refetch;
  const [conversationScope, setConversationScope] = useState("active");
  const [conversationSearch, setConversationSearch] = useState("");
  const deferredConversationSearch = useDeferredValue(
    conversationSearch.trim(),
  );
  const conversationPageKey = JSON.stringify({
    scope: deferredConversationSearch ? "all" : conversationScope,
    q: deferredConversationSearch,
  });
  const conversationPaging = useCursorPagination(conversationPageKey);
  const conversationListQuery = useGetAIConversationsQuery(
    {
      scope: deferredConversationSearch ? "all" : conversationScope,
      q: deferredConversationSearch,
      cursor: conversationPaging.cursor,
      limit: 25,
    },
    QUERY_POLICIES.operational,
  );
  const { accept: acceptConversationPage } = conversationPaging;
  useEffect(() => { acceptConversationPage(conversationListQuery.data); }, [acceptConversationPage, conversationListQuery.data]);
  const conversations = conversationPaging.items;
  const conversationsLoading = conversationListQuery.isLoading && !conversations.length;
  const listedActiveConversation = conversations.find((item) => item.id === active);
  const conversationDetailQuery = useGetAIConversationQuery(
    active,
    withSkip(QUERY_POLICIES.reference, !active || Boolean(listedActiveConversation)),
  );
  const conversationQuery = useGetConversationMessagePageQuery(
    { conversationId: active, limit: 50 },
    withSkip(QUERY_POLICIES.reference, !active),
  );
  const [loadOlderMessagePage, olderMessageState] = useLazyGetConversationMessagePageQuery();
  const [messageCursor, setMessageCursor] = useState(null);
  const {
    currentData: conversationMessagePage,
    isFetching: conversationFetching,
    isError: conversationError,
  } = conversationQuery;
  const conversationMessages = conversationMessagePage?.items;
  const documents = sidebar?.documents || EMPTY_ITEMS;
  const savedViews = sidebar?.savedViews || EMPTY_ITEMS;
  const sidebarLoading = workspaceLoading || conversationsLoading;
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [feedbackTarget, setFeedbackTarget] = useState(null);
  const [feedbackReason, setFeedbackReason] = useState("");
  const [personalizationOpen, setPersonalizationOpen] = useState(false);
  const [deleteConversation, deleteConversationState] =
    useDeleteAIConversationMutation();
  const [deleteConversationTurn, deleteTurnState] =
    useDeleteAIConversationTurnMutation();
  const [updateConversation, updateConversationState] =
    useUpdateAIConversationMutation();
  const [submitMessageFeedback, feedbackState] =
    useSubmitAIMessageFeedbackMutation();
  const [searchParams, setSearchParams] = useSearchParams();
  const messageViewport = useRef(null);
  const inputRef = useRef(null);
  const keepAtBottom = useRef(true);
  const historyRefreshKey = useRef(null);
  const requestController = useRef(null);
  const stopRequested = useRef(false);
  const conversationCache = useRef(new Map());
  const initialSent = useRef(false);
  const startingNewConversation = useRef(false);
  const requestedConversation = searchParams.get("chat");
  const draftMessage = draftAssistantId
    ? messages.find((message) => message.id === draftAssistantId)
    : null;
  conversations.forEach((item) => conversationCache.current.set(item.id, item));
  if (conversationDetailQuery.currentData) {
    conversationCache.current.set(active, conversationDetailQuery.currentData);
  }
  const activeConversation =
    listedActiveConversation ||
    conversationDetailQuery.currentData ||
    conversationCache.current.get(active);

  useLayoutEffect(() => {
    const composer = inputRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    composer.style.height = `${Math.min(composer.scrollHeight, 128)}px`;
  }, [input]);

  useLayoutEffect(() => {
    if (!requestedConversation) {
      startingNewConversation.current = false;
      return;
    }
    if (startingNewConversation.current) return;
    if (requestedConversation && requestedConversation !== active) {
      dispatch(setActiveConversation(requestedConversation));
    }
  }, [active, dispatch, requestedConversation]);

  useEffect(() => {
    setMessageCursor(null);
  }, [active]);

  useEffect(() => {
    const waitingForCompletedMessage =
      pendingHistoryConversationId === active &&
      pendingHistoryMessageId &&
      !conversationMessages?.some(
        (message) => message.id === pendingHistoryMessageId,
      );
    if (
      active &&
      conversationMessages &&
      !streaming &&
      !waitingForCompletedMessage
    ) {
      dispatch(
        setMessages({ conversationId: active, messages: conversationMessages, preserveOlder: true }),
      );
      setMessageCursor(conversationMessagePage?.next_cursor || null);
    }
  }, [
    active,
    conversationMessages,
    dispatch,
    pendingHistoryConversationId,
    pendingHistoryMessageId,
    conversationMessagePage?.next_cursor,
    streaming,
  ]);

  useEffect(() => {
    if (!pendingHistoryMessageId) {
      historyRefreshKey.current = null;
      return;
    }
    if (pendingHistoryConversationId !== active || conversationFetching) return;
    const refreshKey = `${active}:${pendingHistoryMessageId}`;
    if (historyRefreshKey.current === refreshKey) return;
    historyRefreshKey.current = refreshKey;
    conversationQuery.refetch().catch(() => {});
  }, [
    active,
    conversationFetching,
    conversationQuery,
    pendingHistoryConversationId,
    pendingHistoryMessageId,
  ]);

  useLayoutEffect(() => {
    const viewport = messageViewport.current;
    if (!viewport || !keepAtBottom.current) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [
    active,
    draftMessage?.content,
    draftMessage?.blocks?.length,
    messages.length,
    streaming,
  ]);

  const loadEarlierMessages = async () => {
    if (!active || !messageCursor || olderMessageState.isFetching) return;
    const viewport = messageViewport.current;
    const previousHeight = viewport?.scrollHeight || 0;
    keepAtBottom.current = false;
    try {
      const page = await loadOlderMessagePage({
        conversationId: active,
        cursor: messageCursor,
        limit: 50,
      }).unwrap();
      dispatch(prependMessages({ conversationId: active, messages: page.items || [] }));
      setMessageCursor(page.next_cursor || null);
      requestAnimationFrame(() => {
        if (viewport) viewport.scrollTop += viewport.scrollHeight - previousHeight;
      });
    } catch (error) {
      toast.error(error?.data?.detail || "Earlier messages could not be loaded");
    }
  };

  const send = useCallback(
    async (text, explicitContext = null) => {
      const question = (text || input).trim();
      if (!question || streaming) return;
      if (activeConversation?.archived_at) {
        toast.error("Restore this chat before sending a new message");
        return;
      }
      keepAtBottom.current = true;
      const requestId = crypto.randomUUID();
      const userMessageId = `user-${requestId}`;
      const assistantId = `stream-${requestId}`;
      const contextKind = searchParams.get("context_kind");
      const contextId = searchParams.get("context_id");
      dispatch(
        appendUserMessage({
          id: userMessageId,
          role: "user",
          content: question,
        }),
      );
      dispatch(startStreaming({ assistantId, userId: userMessageId }));
      setInput("");
      const controller = new AbortController();
      requestController.current = controller;
      stopRequested.current = false;
      try {
        await streamAI(
          {
            conversation_id: active,
            message: question,
            location_id: locationId,
            idempotency_key: requestId,
            context:
              explicitContext ||
              (contextKind && contextId
                ? { kind: contextKind, id: contextId }
                : null),
          },
          (event, data) => {
            if (event === "accepted")
              dispatch(setStreamStatus("Request received"));
            else if (event === "status")
              dispatch(setStreamStatus(data.message));
            else if (event === "text_delta")
              dispatch(appendTextDelta(data.text));
            else if (event === "block") dispatch(appendStreamBlock(data));
            else if (event === "action") dispatch(appendStreamAction(data));
            else if (event === "complete") {
              dispatch(completeStreaming(data));
              if (data.ai_wallet)
                dispatch(
                  baseApi.util.updateQueryData(
                    "get",
                    { url: "/organization/context" },
                    (draft) => {
                      if (draft?.data) draft.data.ai_wallet = data.ai_wallet;
                    },
                  ),
                );
              if (data.conversation) {
                conversationCache.current.set(
                  data.conversation.id,
                  data.conversation,
                );
                dispatch(
                  aiCacheApi.util.invalidateTags([
                    { type: "Resource", id: "ai" },
                  ]),
                );
              }
              const next = new URLSearchParams(searchParams);
              if (data.conversation_id) next.set("chat", data.conversation_id);
              next.delete("ask");
              setSearchParams(next, { replace: true });
            } else if (event === "error") throw new Error(data.message);
          },
          controller.signal,
        );
      } catch (error) {
        if (error.name === "AbortError") {
          const explicitlyStopped = stopRequested.current;
          dispatch(cancelStreaming());
          if (explicitlyStopped) {
            setInput(question);
            toast.info("Response stopped. Your question is ready to retry.");
          }
        } else {
          dispatch(failStreaming(error.message));
          setInput(question);
          toast.error(error.message || "Edvatiq could not respond");
        }
      } finally {
        if (requestController.current === controller) {
          requestController.current = null;
        }
        stopRequested.current = false;
      }
    },
    [
      active,
      activeConversation?.archived_at,
      dispatch,
      input,
      locationId,
      searchParams,
      setSearchParams,
      streaming,
    ],
  );

  const stopGeneration = () => {
    if (!requestController.current || !streaming) return;
    stopRequested.current = true;
    requestController.current.abort();
  };

  useEffect(() => {
    const requested = searchParams.get("ask");
    if (requested && !initialSent.current && !streaming) {
      initialSent.current = true;
      send(requested);
    }
  }, [searchParams, send, streaming]);

  const chooseConversation = (id) => {
    stopRequested.current = false;
    requestController.current?.abort();
    startingNewConversation.current = false;
    keepAtBottom.current = true;
    dispatch(setActiveConversation(id));
    const next = new URLSearchParams(searchParams);
    next.set("chat", id);
    setSearchParams(next, { replace: true });
  };
  const newConversation = () => {
    startingNewConversation.current = true;
    stopRequested.current = false;
    requestController.current?.abort();
    requestController.current = null;
    keepAtBottom.current = true;
    if (streaming) dispatch(cancelStreaming());
    dispatch(setActiveConversation(null));
    dispatch(setMessages({ conversationId: null, messages: [] }));
    dispatch(closeResultDrawer());
    setInput("");
    setConversationScope("active");
    setConversationSearch("");
    const next = new URLSearchParams(searchParams);
    next.delete("chat");
    next.delete("ask");
    next.delete("context_kind");
    next.delete("context_id");
    setSearchParams(next, { replace: true });
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const changeConversation = async (item, changes, successMessage) => {
    try {
      const updated = await updateConversation({
        conversationId: item.id,
        changes,
      }).unwrap();
      conversationCache.current.set(item.id, updated);
      conversationPaging.reset();
      if (successMessage) toast.success(successMessage);
      return updated;
    } catch (error) {
      toast.error(error?.data?.detail || "This chat could not be updated");
      return null;
    }
  };

  const togglePin = async (item) => {
    await changeConversation(
      item,
      { pinned: !item.pinned_at },
      item.pinned_at ? "Chat unpinned" : "Chat pinned",
    );
  };

  const openRename = (item) => {
    setRenameTarget(item);
    setRenameTitle(item.title || "");
  };

  const saveRename = async () => {
    const title = renameTitle.trim().replace(/\s+/g, " ");
    if (!renameTarget || !title) return;
    const updated = await changeConversation(
      renameTarget,
      { title },
      "Chat renamed",
    );
    if (updated) {
      setRenameTarget(null);
      setRenameTitle("");
    }
  };

  const toggleArchive = async (item) => {
    const restoring = Boolean(item.archived_at);
    const updated = await changeConversation(
      item,
      { archived: !restoring },
      restoring ? "Chat restored" : "Chat archived",
    );
    if (!updated) return;
    if (restoring) {
      setConversationScope("active");
      setConversationSearch("");
      chooseConversation(item.id);
    } else if (item.id === active) {
      newConversation();
    }
  };

  const copyMessage = async (message) => {
    try {
      await navigator.clipboard.writeText(message.content || "");
      toast.success("Response copied");
    } catch {
      toast.error("This response could not be copied");
    }
  };

  const saveFeedback = async (message, rating, reason = "") => {
    if (!message?.id || !active) return false;
    try {
      await submitMessageFeedback({
        conversationId: active,
        messageId: message.id,
        rating,
        reason: reason.trim(),
      }).unwrap();
      dispatch(
        setMessageFeedback({
          conversationId: active,
          messageId: message.id,
          rating,
        }),
      );
      toast.success(rating === "helpful" ? "Thanks for the feedback" : "Feedback received");
      return true;
    } catch (error) {
      toast.error(error?.data?.detail || "Feedback could not be saved");
      return false;
    }
  };

  const rateMessage = (message, rating) => {
    if (rating === "not_helpful") {
      setFeedbackTarget(message);
      setFeedbackReason("");
      return;
    }
    saveFeedback(message, rating);
  };

  const submitNegativeFeedback = async () => {
    if (!feedbackTarget) return;
    if (await saveFeedback(feedbackTarget, "not_helpful", feedbackReason)) {
      setFeedbackTarget(null);
      setFeedbackReason("");
    }
  };

  const removeSelected = async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.type === "conversation") {
        await deleteConversation(deleteTarget.conversationId).unwrap();
        dispatch(removeConversation(deleteTarget.conversationId));
        conversationPaging.reset();
        if (deleteTarget.conversationId === active) {
          const next = new URLSearchParams(searchParams);
          next.delete("chat");
          setSearchParams(next, { replace: true });
        }
      } else {
        await deleteConversationTurn({
          conversationId: deleteTarget.conversationId,
          turnId: deleteTarget.turnId,
        }).unwrap();
        dispatch(
          removeTurn({
            conversationId: deleteTarget.conversationId,
            turnId: deleteTarget.turnId,
          }),
        );
      }
      setDeleteTarget(null);
      toast.success(
        deleteTarget.type === "conversation"
          ? "Chat deleted"
          : "Question and answer deleted",
      );
    } catch (error) {
      toast.error(error.data?.detail || "Could not delete this chat history");
    }
  };

  const confirm = async (action) => {
    try {
      let current = action;
      if (!current.confirmation_token)
        current = (
          await api.post(`/ai/actions/${action.action_id}/confirmation`)
        ).data;
      const result = (
        await api.post(`/ai/actions/${action.action_id}/confirm`, {
          confirmation_token: current.confirmation_token,
        })
      ).data;
      dispatch(updateAction(result));
      toast.success("Action completed");
    } catch (error) {
      toast.error(
        error.response?.data?.detail || "Could not complete the action",
      );
    }
  };
  const undo = async (action) => {
    try {
      const result = (await api.post(`/ai/actions/${action.action_id}/undo`))
        .data;
      dispatch(updateAction(result));
      toast.success("Action undone");
    } catch (error) {
      toast.error(
        error.response?.data?.detail || "This action could not be undone",
      );
    }
  };
  const pin = async ({ sessionId, querySpec, title }) => {
    try {
      await api.post("/ai/views", {
        name: title || "Saved insight",
        query_spec: querySpec || (await api.get(`/ai/results/${sessionId}`, { params: { limit: 5 } })).data.query_spec,
        layout: [],
        visibility: "private",
      });
      toast.success("Pinned to your saved views");
      await refreshSidebar();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Could not pin this view");
    }
  };
  const runSavedView = async (view) => {
    try {
      const response = await api.post(`/ai/views/${view.id}/run`);
      dispatch(
        openResultDrawer({ title: view.name, initial: response.data.result }),
      );
    } catch {
      toast.error("Could not refresh this view");
    }
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    form.append("visibility", "team");
    if (locationId) form.append("location_id", locationId);
    try {
      await api.post("/documents/upload", form);
      toast.success("Document is being prepared");
      await refreshSidebar();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Could not upload document");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const listen = () => {
    const Recognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition)
      return toast.error("Voice input is not supported in this browser");
    const recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.onresult = (event) => setInput(event.results[0][0].transcript);
    recognition.onerror = () =>
      toast.error("Could not understand the recording");
    recognition.start();
  };
  const conversationLoading = Boolean(
    active && conversationFetching && !messages.length,
  );
  const conversationUnavailable = Boolean(
    active && (conversationError || conversationDetailQuery.isError),
  );
  const conversationReadOnly = Boolean(
    activeConversation?.archived_at || conversationUnavailable,
  );

  return (
    <SecondarySidebarLayout
      ariaLabel="Chat history"
      className="h-full reveal"
      sidebarWidthClassName={historyCollapsed ? "w-[4.5rem]" : "w-[208px]"}
      sidebarClassName="overflow-hidden bg-card duration-300"
      contentClassName="flex min-h-0 bg-background"
      mobileTitle="Chat history"
      mobileDescription="Choose or remove a conversation"
      sidebar={historyCollapsed ? (
          <CollapsedHistoryRail
            isCollege={isCollege}
            active={active}
            conversations={conversations}
            savedViews={savedViews}
            documents={documents}
            onExpand={() => dispatch(setAISidebarCollapsed(false))}
            onNew={newConversation}
            onChoose={chooseConversation}
            onSavedView={runSavedView}
            onUpload={upload}
          />
        ) : (
          <HistoryPanel
            isCollege={isCollege}
            active={active}
            conversations={conversations}
            savedViews={savedViews}
            documents={documents}
            loading={sidebarLoading}
            uploading={uploading}
            onNew={newConversation}
            onChoose={chooseConversation}
            onSavedView={runSavedView}
            onUpload={upload}
            search={conversationSearch}
            scope={conversationScope}
            onSearch={setConversationSearch}
            onScopeChange={setConversationScope}
            onCollapse={() => dispatch(setAISidebarCollapsed(true))}
            onPin={togglePin}
            onRename={openRename}
            onArchive={toggleArchive}
            onDelete={(item) =>
              setDeleteTarget({
                type: "conversation",
                conversationId: item.id,
                title: item.title,
              })
            }
            streaming={streaming}
            hasMore={Boolean(conversationListQuery.data?.has_more)}
            loadingMore={conversationListQuery.isFetching}
            onLoadMore={() => conversationPaging.loadMore(conversationListQuery.data?.next_cursor)}
          />
        )}
      mobileSidebar={({ closeSidebar }) => <HistoryPanel
        isCollege={isCollege}
        active={active}
        conversations={conversations}
        savedViews={savedViews}
        documents={documents}
        loading={sidebarLoading}
        uploading={uploading}
        onNew={() => { newConversation(); closeSidebar(); }}
        onChoose={(id) => { chooseConversation(id); closeSidebar(); }}
        onSavedView={(view) => { runSavedView(view); closeSidebar(); }}
        onUpload={upload}
        search={conversationSearch}
        scope={conversationScope}
        onSearch={setConversationSearch}
        onScopeChange={setConversationScope}
        onPin={togglePin}
        onRename={openRename}
        onArchive={toggleArchive}
        onDelete={(item) => setDeleteTarget({
          type: "conversation",
          conversationId: item.id,
          title: item.title,
        })}
        streaming={streaming}
        hasMore={Boolean(conversationListQuery.data?.has_more)}
        loadingMore={conversationListQuery.isFetching}
        onLoadMore={() => conversationPaging.loadMore(conversationListQuery.data?.next_cursor)}
        mobile
      />}
    >
      {({ openSidebar }) => <>
      <section className="ai-surface flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="px-4 py-3.5 md:px-6 md:py-4 border-b bg-card/80 backdrop-blur flex items-center gap-3">
          <SecondarySidebarTrigger compact icon={List} label="chat history" onClick={openSidebar} className="border-0 bg-transparent shadow-none hover:bg-secondary" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 font-display text-2xl">
              <span className="h-9 w-9 rounded-xl bg-primary text-primary-foreground grid place-items-center shadow-sm"><Sparkle weight="fill" className="text-accent" /></span>
              <span className="truncate">{isCollege ? "College assistant" : "Ask your business"}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1 truncate">
              {activeConversation?.title || (isCollege ? "Student readiness, academics, coding, and placements" : "Live answers, document knowledge, and useful next steps")}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 shrink-0 rounded-xl px-2.5 shadow-none sm:px-3"
            onClick={() => setPersonalizationOpen(true)}
          >
            <SlidersHorizontal size={17} />
            <span className="ml-2 hidden sm:inline">Personalize</span>
          </Button>
        </header>
        <div
          ref={messageViewport}
          onScroll={(event) => {
            const viewport = event.currentTarget;
            keepAtBottom.current =
              viewport.scrollHeight -
                viewport.scrollTop -
                viewport.clientHeight <
              120;
          }}
          className="premium-scrollbar flex-1 overflow-y-auto p-4 md:p-6 space-y-6"
        >
          {conversationLoading ? (
            <ConversationSkeleton />
          ) : (
            !messages.length &&
            !streaming &&
            !conversationError && <Welcome send={send} isCollege={isCollege} />
          )}
          {conversationError && !messages.length && (
            <InlineState
              icon={WarningCircle}
              text="This conversation could not be loaded."
              action={() => conversationQuery.refetch()}
            />
          )}
          {messageCursor && messages.length > 0 && (
            <div className="mx-auto flex w-full max-w-5xl justify-center">
              <Button type="button" variant="outline" size="sm" disabled={olderMessageState.isFetching} onClick={loadEarlierMessages}>
                {olderMessageState.isFetching ? "Loading earlier messages..." : "Load earlier messages"}
              </Button>
            </div>
          )}
          {messages.map((message) => (
            <Message
              key={message.id}
              message={message}
              isCollege={isCollege}
              isStreaming={streaming && message.id === draftAssistantId}
              streamStatus={streamStatus}
              onDelete={
                message.turn_id && !streaming
                  ? () =>
                      setDeleteTarget({
                        type: "turn",
                        conversationId: active,
                        turnId: message.turn_id,
                      })
                  : null
              }
              onCopy={() => copyMessage(message)}
              onFeedback={(rating) => rateMessage(message, rating)}
              onViewAll={({ sessionId, querySpec, title }) =>
                dispatch(openResultDrawer({ id: sessionId, querySpec, title }))
              }
              onPin={pin}
              onConfirm={confirm}
              onUndo={undo}
              onSelectEntity={(item) =>
                send(
                  `Tell me about ${item.display_name || "this record"}`,
                  item.selection_ref,
                )
              }
            />
          ))}
          {streamError && !streaming && (
            <InlineState icon={WarningCircle} text={streamError} />
          )}
          <div aria-hidden="true" />
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
          className="border-t bg-card/85 p-3 md:p-4 backdrop-blur"
        >
          {activeConversation?.archived_at ? (
            <div className="mx-auto mb-2 flex max-w-5xl items-center justify-between gap-3 rounded-xl border bg-secondary/70 px-3 py-2 text-xs text-muted-foreground">
              <span>This chat is archived and read-only.</span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 shrink-0"
                onClick={() => toggleArchive(activeConversation)}
              >
                Restore chat
              </Button>
            </div>
          ) : conversationUnavailable ? (
            <div className="mx-auto mb-2 flex max-w-5xl items-center justify-between gap-3 rounded-xl border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              <span>This chat is no longer available.</span>
              <Button type="button" size="sm" variant="outline" className="h-8 shrink-0" onClick={newConversation}>
                Start new chat
              </Button>
            </div>
          ) : null}
          <div className="mx-auto max-w-5xl rounded-2xl border bg-background/80 p-2 shadow-[0_10px_30px_hsl(var(--primary)/.08)] focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent/10 transition">
            <div className="flex items-end gap-2">
            <button
              type="button"
              onClick={listen}
              className="h-10 w-10 shrink-0 grid place-items-center rounded-xl text-muted-foreground hover:bg-secondary hover:text-foreground"
              title="Voice input"
              disabled={conversationReadOnly}
            >
              <Microphone />
            </button>
            <textarea
              ref={inputRef}
              rows={1}
              className="premium-scrollbar min-h-10 max-h-32 flex-1 resize-none bg-transparent px-2 py-2.5 text-sm leading-5 outline-none"
              placeholder={conversationReadOnly ? "Start or restore a chat to continue" : isCollege ? "Ask about students, readiness, attendance, coding, or placements..." : "Ask about sales, clients, stock, appointments or documents..."}
              value={input}
              disabled={conversationReadOnly}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
            />
            {streaming ? (
              <Button
                type="button"
                variant="destructive"
                className="h-10 w-10 shrink-0 rounded-xl p-0 shadow-sm"
                aria-label="Stop generating"
                title="Stop generating"
                onClick={stopGeneration}
              >
                <Stop size={17} weight="fill" />
              </Button>
            ) : (
              <Button
                className="h-10 w-10 shrink-0 rounded-xl p-0 shadow-sm"
                disabled={!input.trim() || conversationReadOnly}
                aria-label="Send question"
              >
                <PaperPlaneRight />
              </Button>
            )}
            </div>
          </div>
        </form>
      </section>
      <DeleteHistoryDialog
        target={deleteTarget}
        busy={deleteConversationState.isLoading || deleteTurnState.isLoading}
        close={() => setDeleteTarget(null)}
        confirm={removeSelected}
      />
      <RenameConversationDialog
        target={renameTarget}
        title={renameTitle}
        busy={updateConversationState.isLoading}
        onTitleChange={setRenameTitle}
        close={() => setRenameTarget(null)}
        confirm={saveRename}
      />
      <FeedbackDialog
        target={feedbackTarget}
        reason={feedbackReason}
        busy={feedbackState.isLoading}
        onReasonChange={setFeedbackReason}
        close={() => setFeedbackTarget(null)}
        confirm={submitNegativeFeedback}
      />
      <AssistantPersonalizationSheet
        open={personalizationOpen}
        onOpenChange={setPersonalizationOpen}
      />
      <ResultDrawer
        drawer={resultDrawer}
        close={() => dispatch(closeResultDrawer())}
      />
      </>}
    </SecondarySidebarLayout>
  );
}

function CollapsedHistoryRail({ active, conversations, savedViews, documents, onExpand, onNew, onChoose, onSavedView, onUpload, isCollege = false }) {
  const recent = conversations.slice(0, 5);
  return <div className="flex h-full flex-col items-center py-2.5">
    <RailButton label="Expand chat history" onClick={onExpand}><SidebarSimple size={20} /></RailButton>
    <div className="my-2 h-px w-8 bg-border" />
    <RailButton label="New conversation" onClick={onNew} primary><ChatCircleDots size={21} weight="fill" /></RailButton>
    <div className="premium-scrollbar mt-3 flex min-h-0 flex-1 flex-col items-center gap-1.5 overflow-y-auto px-2">
      {recent.map((item) => <RailButton key={item.id} label={item.title} active={active === item.id} onClick={() => onChoose(item.id)}>
        <ChatCircleDots size={19} weight={active === item.id ? "fill" : "regular"} />
        {item.active_stream && <i className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-accent" />}
      </RailButton>)}
      {!!savedViews.length && <div className="my-1 h-px w-8 bg-border" />}
      {savedViews.slice(0, 3).map((view) => <RailButton key={view.id} label={`Open ${view.name}`} onClick={() => onSavedView(view)}><PushPin size={19} /></RailButton>)}
    </div>
    <div className="mb-2 h-px w-8 bg-border" />
    <label className="relative h-11 w-11 cursor-pointer rounded-xl text-muted-foreground grid place-items-center hover:bg-secondary hover:text-foreground" title={isCollege ? "Add College knowledge" : "Add business knowledge"}>
      <FileArrowUp size={20} />
      {documents.filter((item) => item.status === "ready").length > 0 && <span className="absolute right-0 top-0 min-w-4 rounded-full bg-primary px-1 text-center text-[9px] leading-4 text-primary-foreground">{documents.filter((item) => item.status === "ready").length}</span>}
      <input hidden type="file" accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" onChange={onUpload} />
    </label>
  </div>;
}

function RailButton({ children, label, onClick, active = false, primary = false }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick} className={`relative h-11 w-11 shrink-0 rounded-xl grid place-items-center transition ${primary ? "bg-primary text-primary-foreground shadow-sm hover:-translate-y-0.5" : active ? "bg-accent/15 text-accent ring-1 ring-accent/25" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}>{children}</button>;
}

function SidebarLabel({ children }) {
  return (
    <div className="text-[10px] uppercase tracking-[.16em] text-muted-foreground px-3 pt-3 pb-2">
      {children}
    </div>
  );
}
function HistoryPanel({
  isCollege = false,
  active,
  conversations,
  savedViews,
  documents,
  loading,
  uploading,
  onNew,
  onChoose,
  onSavedView,
  onUpload,
  search,
  scope,
  onSearch,
  onScopeChange,
  onCollapse,
  onPin,
  onRename,
  onArchive,
  onDelete,
  streaming,
  hasMore,
  loadingMore,
  onLoadMore,
  mobile = false,
}) {
  const searching = Boolean(search.trim());
  const pinned = searching || scope === "archived"
    ? EMPTY_ITEMS
    : conversations.filter((item) => item.pinned_at && !item.archived_at);
  const remaining = pinned.length
    ? conversations.filter((item) => !item.pinned_at)
    : conversations;
  const showRows = (items) => items.map((item) => (
    <ConversationRow
      key={item.id}
      item={item}
      active={active === item.id}
      streaming={(streaming && active === item.id) || item.active_stream}
      onChoose={onChoose}
      onPin={onPin}
      onRename={onRename}
      onArchive={onArchive}
      onDelete={onDelete}
    />
  ));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1.5 border-b px-2.5 py-2.5">
        <Button
          variant="outline"
          className="h-10 min-w-0 flex-1 justify-start rounded-xl px-3 text-sm shadow-none"
          onClick={onNew}
        >
          <ChatCircleDots size={17} className="mr-2 shrink-0" />
          <span className="truncate">New chat</span>
        </Button>
        {!mobile && (
          <button
            type="button"
            className="grid h-10 w-9 shrink-0 place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Collapse chat history"
            title="Collapse chat history"
            onClick={onCollapse}
          >
            <SidebarSimple size={18} />
          </button>
          )}
      </div>
      <div className="space-y-2 border-b px-2.5 py-2.5">
        <div className="relative">
          <MagnifyingGlass
            size={15}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            maxLength={120}
            className="h-9 rounded-xl border-transparent bg-secondary pl-8 pr-2 text-xs shadow-none focus-visible:bg-background"
            placeholder="Search chats"
            aria-label="Search chats"
          />
        </div>
        <div className="grid grid-cols-2 rounded-xl bg-secondary p-0.5" aria-label="Conversation scope">
          {["active", "archived"].map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                onSearch("");
                onScopeChange(value);
              }}
              className={cn(
                "h-7 rounded-[10px] text-[11px] font-medium capitalize transition",
                !searching && scope === value
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {value}
            </button>
          ))}
        </div>
      </div>
      <div className="premium-scrollbar flex-1 overflow-y-auto px-2">
        {loading ? (
          <div className="space-y-2 px-2 pt-4">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-14 rounded-xl bg-secondary animate-pulse"
              />
            ))}
          </div>
        ) : conversations.length ? (
          <>
            {!!pinned.length && (
              <>
                <SidebarLabel>Pinned</SidebarLabel>
                {showRows(pinned)}
              </>
            )}
            <SidebarLabel>
              {searching ? "Search results" : scope === "archived" ? "Archived" : "Recent"}
            </SidebarLabel>
            {showRows(remaining)}
          </>
        ) : (
          <div className="px-3 py-8 text-center text-xs text-muted-foreground">
            {searching
              ? "No chats match your search."
              : scope === "archived"
                ? "Archived chats will appear here."
                : "Your conversations will appear here."}
          </div>
        )}
        {hasMore && <div className="px-3 pt-2"><button type="button" disabled={loadingMore} onClick={onLoadMore} className="h-9 w-full rounded-xl border bg-card text-xs font-semibold transition hover:bg-secondary disabled:opacity-60">{loadingMore ? "Loading chats..." : "Load more chats"}</button></div>}
        {!!savedViews.length && (
          <>
            <SidebarLabel>Saved views</SidebarLabel>
            {savedViews.map((view) => (
              <button
                key={view.id}
                onClick={() => onSavedView(view)}
                className="w-full text-left p-3 rounded-xl text-sm mb-1 hover:bg-secondary flex gap-2 items-center"
              >
                <PushPin className="text-accent" />
                <span className="truncate">{view.name}</span>
              </button>
            ))}
          </>
        )}
      </div>
      <div className="border-t p-3">
        <SidebarLabel>Knowledge</SidebarLabel>
        <label className="block border border-dashed rounded-xl p-3 text-center text-xs cursor-pointer hover:bg-secondary">
          <FileArrowUp className="mx-auto mb-1" />
          {uploading ? "Preparing upload..." : isCollege ? "Add College knowledge" : "Add business knowledge"}
          <input
            hidden
            type="file"
            accept=".pdf,.docx,.txt,.jpg,.jpeg,.png"
            onChange={onUpload}
          />
        </label>
        <div className="text-xs text-muted-foreground mt-2">
          {documents.filter((item) => item.status === "ready").length}{" "}
          searchable document{documents.length === 1 ? "" : "s"}
        </div>
      </div>
    </div>
  );
}

function ConversationRow({ item, active, streaming, onChoose, onPin, onRename, onArchive, onDelete }) {
  return (
    <div
      className={cn(
        "group relative mb-1 overflow-hidden rounded-xl transition-colors",
        active ? "bg-primary text-primary-foreground" : "hover:bg-secondary",
      )}
    >
      <button
        type="button"
        onClick={() => onChoose(item.id)}
        className="block w-full min-w-0 px-3 py-2.5 pr-10 text-left"
      >
        <div className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
          {item.pinned_at && !item.archived_at && (
            <PushPin size={11} weight="fill" className={active ? "text-accent" : "text-muted-foreground"} />
          )}
          {item.archived_at && (
            <Archive size={12} className={active ? "text-white/65" : "text-muted-foreground"} />
          )}
          <span className="truncate">{item.title}</span>
          {item.active_stream && (
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" aria-label="Answer in progress" />
          )}
        </div>
        <div className={cn("mt-1 flex gap-2 text-[10px]", active ? "text-white/60" : "text-muted-foreground")}>
          <span className="min-w-0 flex-1 truncate">
            {item.preview || `${item.turn_count || 0} question${item.turn_count === 1 ? "" : "s"}`}
          </span>
          <span className="shrink-0">{formatRelative(item.updated_at)}</span>
        </div>
      </button>
      <ConversationMenu
        item={item}
        archiveDisabled={streaming}
        onPin={() => onPin(item)}
        onRename={() => onRename(item)}
        onArchive={() => onArchive(item)}
        onDelete={() => onDelete(item)}
        active={active}
      />
    </div>
  );
}
function formatRelative(value) {
  if (!value) return "Recently";
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}
function Welcome({ send, isCollege = false }) {
  const suggestions = isCollege ? collegeSuggestions : businessSuggestions;
  return (
    <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col justify-center py-2 text-center md:py-4">
      <div className="relative mx-auto grid h-14 w-14 place-items-center rounded-[1.15rem] ai-hero shadow-[0_14px_36px_hsl(var(--primary)/.16)] md:h-16 md:w-16 md:rounded-[1.35rem]">
        <Sparkle size={28} weight="fill" className="text-accent" />
        <span className="absolute -right-1 -top-1 h-4 w-4 rounded-full border-[3px] border-background bg-emerald-500" />
      </div>
      <div className="overline mt-4 text-accent">{isCollege ? "Your placement workspace, ready to answer" : "Your business, ready to answer"}</div>
      <h2 className="mt-1.5 font-display text-3xl md:text-4xl">
        What would you like to know?
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
        {isCollege ? "Understand student evidence, readiness, support needs, and placement outcomes from authorized records." : "Get a live view of your business, find a record, or explore your uploaded knowledge."}
      </p>
      <div className="mt-5 grid gap-2 text-left sm:grid-cols-2">
        {suggestions.map((item, index) => (
          <button
            key={item}
            onClick={() => send(item)}
            className="group rounded-2xl border bg-card/75 px-3.5 py-3 text-sm shadow-sm transition hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <span className="flex items-center gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-secondary text-muted-foreground group-hover:bg-accent/15 group-hover:text-accent"><Sparkle size={15} weight={index === 0 ? "fill" : "regular"} /></span><span className="font-medium">{item}</span></span>
          </button>
        ))}
      </div>
    </div>
  );
}
function Message({ message, isCollege = false, isStreaming, streamStatus, onDelete, onCopy, onFeedback, ...actions }) {
  const user = message.role === "user";
  return (
    <div className={`group mx-auto flex w-full max-w-5xl ${user ? "justify-end" : "justify-start"}`}>
      <div
        className={`relative ${user ? "max-w-[88%] rounded-[1.4rem] rounded-br-md bg-primary px-4 py-3 text-primary-foreground shadow-sm md:max-w-[72%]" : "w-full min-w-0"}`}
      >
        {user && onDelete && (
          <HistoryMenu
            onDelete={onDelete}
            label="Message options"
            className="absolute -left-10 top-0"
          />
        )}
        {user ? (
          <div className="whitespace-pre-wrap text-sm leading-7">
            {message.content}
          </div>
        ) : (
          <>
            <div className="mb-2.5 flex items-center gap-2.5">
              <span className="h-8 w-8 rounded-xl bg-primary text-primary-foreground grid place-items-center shadow-sm"><Sparkle size={15} weight="fill" className="text-accent" /></span>
              <div className="min-w-0"><div className="text-sm font-semibold">Edvatiq</div><div className="text-[10px] text-muted-foreground">{isCollege ? "Your placement assistant" : "Your business assistant"}</div></div>
              {onDelete && <HistoryMenu onDelete={onDelete} label="Message options" className="ml-auto" />}
            </div>
            {message.content ? <div className="rounded-2xl rounded-tl-md border bg-card/80 px-4 py-3.5 shadow-[0_8px_26px_hsl(var(--primary)/.04)] md:px-5"><RichText>{message.content}</RichText></div> : isStreaming && <Thinking status={streamStatus} />}
            {isStreaming && message.content && (
              <div className="mt-2 flex items-center gap-2 px-1 text-xs text-muted-foreground">
                <CircleNotch className="animate-spin text-accent" />
                {streamStatus || "Preparing your answer"}
              </div>
            )}
            <ResponseBlocks message={message} {...actions} />
            {!isStreaming && message.content && (
              <div className="mt-2 flex items-center gap-0.5 px-1 text-muted-foreground">
                <MessageAction label="Copy response" onClick={onCopy}>
                  <Copy size={15} />
                </MessageAction>
                <MessageAction
                  label="Helpful"
                  active={message.feedback_rating === "helpful"}
                  onClick={() => onFeedback("helpful")}
                >
                  <ThumbsUp size={15} weight={message.feedback_rating === "helpful" ? "fill" : "regular"} />
                </MessageAction>
                <MessageAction
                  label="Not helpful"
                  active={message.feedback_rating === "not_helpful"}
                  onClick={() => onFeedback("not_helpful")}
                >
                  <ThumbsDown size={15} weight={message.feedback_rating === "not_helpful" ? "fill" : "regular"} />
                </MessageAction>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function MessageAction({ label, active = false, onClick, children }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active || undefined}
      onClick={onClick}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-lg transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "bg-secondary text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function ConversationMenu({ item, active, archiveDisabled, onPin, onRename, onArchive, onDelete }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Options for ${item.title}`}
          className={cn(
            "absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-lg border shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            active
              ? "border-white/15 bg-white/10 text-white/75 hover:bg-white/20 hover:text-white"
              : "border-border/70 bg-card/85 text-muted-foreground/70 hover:border-border hover:bg-card hover:text-foreground",
          )}
        >
          <DotsThreeVertical size={13} weight="bold" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="z-[100] w-44 rounded-xl p-1.5">
        {!item.archived_at && (
          <DropdownMenuItem onSelect={onPin}>
            <PushPin weight={item.pinned_at ? "fill" : "regular"} />
            {item.pinned_at ? "Unpin chat" : "Pin chat"}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={onRename}>
          <PencilSimple />
          Rename
        </DropdownMenuItem>
        <DropdownMenuItem disabled={archiveDisabled} onSelect={onArchive}>
          <Archive />
          {item.archived_at ? "Restore chat" : "Archive chat"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={archiveDisabled}
          onSelect={onDelete}
          className="text-red-600 focus:text-red-700"
        >
          <Trash />
          Delete chat
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function HistoryMenu({
  onDelete,
  disabled = false,
  label,
  className = "",
  compact = false,
  menuText = "Delete question and answer",
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label={label}
          className={cn(
            "grid h-8 w-8 shrink-0 place-items-center rounded-lg border bg-card text-muted-foreground opacity-60 transition-opacity hover:text-foreground disabled:opacity-30 md:pointer-events-none md:opacity-0 md:group-hover:pointer-events-auto md:group-hover:opacity-100 md:group-focus-within:pointer-events-auto md:group-focus-within:opacity-100 focus:pointer-events-auto focus:opacity-100",
            className,
          )}
        >
          <DotsThreeVertical size={compact ? 14 : 18} weight="bold" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="z-[100]">
        <DropdownMenuItem
          onSelect={onDelete}
          className="text-red-600 focus:text-red-700"
        >
          <Trash className="mr-2" />
          {menuText}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RenameConversationDialog({ target, title, busy, onTitleChange, close, confirm }) {
  const normalized = title.trim();
  return (
    <Dialog open={!!target} onOpenChange={(open) => !open && close()}>
      <DialogContent>
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            confirm();
          }}
        >
          <DialogHeader>
            <DialogTitle>Rename chat</DialogTitle>
            <DialogDescription>Use a short title that makes this conversation easy to find.</DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={title}
            maxLength={120}
            onChange={(event) => onTitleChange(event.target.value)}
            aria-label="Chat title"
          />
          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>1 to 120 characters</span>
            <span className="tabular-nums">{title.length}/120</span>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close} disabled={busy}>Cancel</Button>
            <Button type="submit" disabled={busy || !normalized}>
              {busy ? "Saving..." : "Save title"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FeedbackDialog({ target, reason, busy, onReasonChange, close, confirm }) {
  return (
    <Dialog open={!!target} onOpenChange={(open) => !open && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>What could be better?</DialogTitle>
          <DialogDescription>
            This is optional. Your feedback helps improve future answers.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          autoFocus
          rows={4}
          maxLength={500}
          value={reason}
          onChange={(event) => onReasonChange(event.target.value)}
          placeholder="For example: the answer missed the customer linked to this invoice."
        />
        <div className="text-right text-xs tabular-nums text-muted-foreground">{reason.length}/500</div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={close} disabled={busy}>Cancel</Button>
          <Button type="button" onClick={confirm} disabled={busy}>
            {busy ? "Sending..." : "Send feedback"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteHistoryDialog({ target, busy, close, confirm }) {
  return (
    <AlertDialog open={!!target} onOpenChange={(open) => !open && close()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {target?.type === "conversation"
              ? "Delete this chat?"
              : "Delete this question and answer?"}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {target?.type === "conversation"
              ? `"${target?.title || "This chat"}" and its messages will be permanently removed.`
              : "This complete turn will be permanently removed. Completed workspace actions will not be reversed."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Keep it</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            onClick={(event) => {
              event.preventDefault();
              confirm();
            }}
            className="bg-red-600 hover:bg-red-700"
          >
            {busy ? "Deleting..." : "Delete permanently"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function Thinking({ status }) {
  return (
    <div className="inline-flex items-center gap-3 rounded-2xl rounded-tl-md border bg-card/80 px-4 py-3 text-sm text-muted-foreground shadow-sm">
      <span className="flex gap-1" aria-hidden="true">
        <i className="h-1.5 w-1.5 rounded-full bg-accent animate-bounce" />
        <i className="h-1.5 w-1.5 rounded-full bg-accent animate-bounce [animation-delay:120ms]" />
        <i className="h-1.5 w-1.5 rounded-full bg-accent animate-bounce [animation-delay:240ms]" />
      </span>
      {status || "Working on your answer"}
    </div>
  );
}
function ConversationSkeleton() {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-5" aria-label="Loading conversation">
      {["w-2/3", "w-5/6", "w-1/2"].map((width, index) => (
        <div
          key={index}
          className={`h-16 ${width} rounded-2xl bg-secondary animate-pulse ${index === 1 ? "ml-auto" : ""}`}
        />
      ))}
    </div>
  );
}
function InlineState({ icon: Icon, text, action }) {
  return (
    <div className="rounded-2xl border border-amber-300/60 bg-amber-50 p-4 text-sm text-amber-950 flex flex-wrap items-center justify-between gap-3">
      <span className="flex items-center gap-2">
        <Icon />
        {text}
      </span>
      {action && (
        <Button size="sm" variant="outline" onClick={action}>
          Try again
        </Button>
      )}
    </div>
  );
}

function ResultDrawer({ drawer, close }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cursor, setCursor] = useState(null);
  useEffect(() => {
    if (!drawer) {
      setData(null);
      setCursor(null);
      return;
    }
    if (drawer.initial) {
      setData(drawer.initial);
      setCursor(drawer.initial.next_cursor || null);
      return;
    }
    setLoading(true);
    const request = drawer.querySpec
      ? api.post("/ai/results/run", { query_spec: drawer.querySpec })
      : api.get(`/ai/results/${drawer.id}`);
    request
      .then((response) => {
        setData(response.data);
        setCursor(response.data.next_cursor);
      })
      .catch(() => toast.error("Could not load the complete result"))
      .finally(() => setLoading(false));
  }, [drawer]);
  const more = async () => {
    if ((!drawer?.id && !drawer?.querySpec) || !cursor) return;
    setLoading(true);
    try {
      const response = drawer.querySpec
        ? await api.post("/ai/results/run", { query_spec: drawer.querySpec, cursor })
        : await api.get(`/ai/results/${drawer.id}`, { params: { cursor } });
      setData((current) => ({
        ...response.data,
        items: [...(current?.items || []), ...response.data.items],
      }));
      setCursor(response.data.next_cursor);
    } finally {
      setLoading(false);
    }
  };
  const items = data?.items || [];
  const hasProfiles = items.some((item) => item.profile_ref);
  const columns = [...new Set(items.flatMap((item) => Object.keys(item)))]
    .filter((key) => !PROFILE_INTERNAL_FIELDS.has(key) && !key.endsWith("_id"))
    .slice(0, 7);
  return (
    <Sheet open={!!drawer} onOpenChange={(open) => !open && close()}>
      <SheetContent className="premium-scrollbar sm:max-w-4xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="font-display text-3xl">
            {drawer?.title || "Complete result"}
          </SheetTitle>
          <SheetDescription>
            {data
              ? `${Number(data.count || items.length).toLocaleString("en-IN")} matching records`
              : "Loading current workspace information"}
          </SheetDescription>
        </SheetHeader>
        {loading && !data ? (
          <div className="mt-8 h-56 animate-pulse bg-secondary rounded-2xl" />
        ) : (
          <>
            {hasProfiles && (
              <div className="mt-6 grid gap-3 md:hidden">
                {items.map((item, index) => (
                  <EntityCard
                    key={item.id || index}
                    item={item}
                    details={visibleProfileFields(item, 3).map(
                      ([key, value]) => [key, drawerValue(value, key)],
                    )}
                  />
                ))}
              </div>
            )}
            <div
              className={`premium-scrollbar mt-6 overflow-x-auto border rounded-2xl ${hasProfiles ? "hidden md:block" : ""}`}
            >
              <table className="w-full text-sm">
                <thead className="bg-secondary">
                  <tr>
                    {columns.map((key) => (
                      <th
                        key={key}
                        className="text-left px-4 py-3 capitalize whitespace-nowrap"
                      >
                        {key.replaceAll("_", " ")}
                      </th>
                    ))}
                    {hasProfiles && <th className="px-4 py-3" />}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, index) => (
                    <ProfileTableRow
                      key={item.id || index}
                      profileRef={item.profile_ref}
                      ariaLabel={`Open ${item.display_name || item.name || "record"} profile`}
                      className="border-t"
                    >
                      {columns.map((key, columnIndex) => (
                        <td key={key} className="px-4 py-3 max-w-64 truncate">
                          {columnIndex === 0 && item.profile_ref ? (
                            <div className="flex items-center gap-2.5">
                              <EntityAvatar
                                name={item.display_name || item.name}
                                kind={item.profile_ref.kind}
                                avatarUrl={item.avatar_url}
                                className="h-9 w-9 rounded-xl text-sm"
                              />
                              <EntityProfileLink
                                profileRef={item.profile_ref}
                                className="font-medium hover:text-accent"
                              >
                                {drawerValue(item[key], key)}
                              </EntityProfileLink>
                            </div>
                          ) : (
                            drawerValue(item[key], key)
                          )}
                        </td>
                      ))}
                      {hasProfiles && (
                        <td className="px-4 py-3 text-right">
                          {item.profile_ref && (
                            <EntityProfileLink
                              profileRef={item.profile_ref}
                              className="text-xs font-semibold text-accent"
                            >
                              Open profile
                            </EntityProfileLink>
                          )}
                        </td>
                      )}
                    </ProfileTableRow>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {cursor && (
          <Button
            variant="outline"
            className="w-full mt-4"
            disabled={loading}
            onClick={more}
          >
            {loading ? "Loading..." : "Load more"}
          </Button>
        )}
      </SheetContent>
    </Sheet>
  );
}

function drawerValue(value, key = "") {
  if (value == null || value === "") return "-";
  if (key.endsWith("_paise"))
    return `INR ${(Number(value) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object")
    return Array.isArray(value) ? value.join(", ") : "Details";
  if (/(_at|_on)$/.test(key) && !Number.isNaN(Date.parse(value)))
    return new Date(value).toLocaleString("en-IN", {
      dateStyle: "medium",
      timeStyle: key.endsWith("_at") ? "short" : undefined,
    });
  return String(value);
}
