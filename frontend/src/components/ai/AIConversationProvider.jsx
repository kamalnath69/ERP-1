import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useDispatch, useSelector } from "react-redux";
import { useLocation } from "react-router-dom";
import { toast } from "sonner";

import api from "@/lib/api";
import { AIStreamError, streamAI } from "@/lib/aiStream";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { aiCacheApi } from "@/store/api/aiCacheApi";
import { baseApi } from "@/store/api/baseApi";
import {
  appendStreamAction,
  appendStreamBlock,
  appendTextDelta,
  appendUserMessage,
  cancelStreaming,
  closeResultDrawer,
  completeStreaming,
  failStreaming,
  selectAIWorkspace,
  setActiveConversation,
  setMessages,
  setStreamStatus,
  startStreaming,
  updateAction,
} from "@/store/slices/aiSlice";

const AIConversationContext = createContext(null);

function safeSessionValue(key) {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSessionValue(key, value) {
  try {
    if (value) window.sessionStorage.setItem(key, value);
    else window.sessionStorage.removeItem(key);
  } catch {
    // Chat remains usable when storage is unavailable.
  }
}

function activeConversationKey(userId) {
  return `edvatiq.ai.active_conversation.v1:${userId}`;
}

export function contextIdentity(context) {
  if (!context) return "none";
  return JSON.stringify([
    context.kind,
    context.id,
    context.domain,
    context.graduation_year,
    context.department_id,
    context.program_id,
    context.cohort_id,
    ...(context.cohort_ids || []),
  ]);
}

function requestPageContext(context, route, locationId) {
  const base = {
    route,
    location_id: locationId || null,
  };
  if (!context) return locationId ? base : null;
  if (context.route || context.entity || context.selected_entities) {
    return { ...base, ...context };
  }
  if (context.kind === "college_scope") {
    const selected = (context.cohort_ids || (context.cohort_id ? [context.cohort_id] : []))
      .map((id) => ({ kind: "cohort", id, label: context.display_name || context.label || null }));
    if (!selected.length && context.department_id) {
      selected.push({ kind: "department", id: context.department_id, label: context.display_name || context.label || null });
    }
    return {
      ...base,
      selected_entities: selected,
      department_id: context.department_id || null,
      program_id: context.program_id || null,
      cohort_ids: context.cohort_ids || (context.cohort_id ? [context.cohort_id] : []),
      graduation_year: context.graduation_year || null,
    };
  }
  return {
    ...base,
    entity: {
      kind: context.kind,
      id: context.id,
      label: context.display_name || context.label || null,
    },
  };
}

export function AIConversationProvider({ children }) {
  const dispatch = useDispatch();
  const location = useLocation();
  const { user } = useAuth();
  const { locationId } = useBusiness();
  const workspace = useSelector(selectAIWorkspace);
  const { activeConversationId: active, streaming } = workspace;
  const [draft, setDraft] = useState("");
  const [restoredUserId, setRestoredUserId] = useState(null);
  const [registeredContext, setRegisteredContext] = useState(null);
  const [lastCompletedMessageId, setLastCompletedMessageId] = useState(null);
  const requestController = useRef(null);
  const abortMode = useRef(null);
  const routeKey = `${location.pathname}${location.search}`;

  useEffect(() => {
    if (!user?.id || restoredUserId === user.id) return;
    const stored = safeSessionValue(activeConversationKey(user.id));
    if (stored && !active) dispatch(setActiveConversation(stored));
    setRestoredUserId(user.id);
  }, [active, dispatch, restoredUserId, user?.id]);

  useEffect(() => {
    if (!user?.id || restoredUserId !== user.id) return;
    writeSessionValue(activeConversationKey(user.id), active);
  }, [active, restoredUserId, user?.id]);

  useEffect(() => () => {
    abortMode.current = "discard";
    requestController.current?.abort();
  }, []);

  const registerPageContext = useCallback((context) => {
    if (!context?.kind || !context?.id) return () => {};
    const token = `${Date.now()}:${Math.random()}`;
    const entry = { token, routeKey, value: context };
    setRegisteredContext(entry);
    return () => setRegisteredContext((current) => (
      current?.token === token ? null : current
    ));
  }, [routeKey]);

  const pageContext = registeredContext?.routeKey === routeKey
    ? registeredContext.value
    : null;

  const sendMessage = useCallback(async (text, options = {}) => {
    const interaction = options.interaction || null;
    const question = interaction ? "" : String(text ?? draft).trim();
    if ((!question && !interaction) || streaming || requestController.current) return false;
    if (question.length > 5000) {
      toast.error("Keep your message within 5,000 characters");
      return false;
    }
    if (options.readOnly) {
      toast.error(options.readOnlyMessage || "Start or restore a chat before sending a message");
      return false;
    }

    const requestId = crypto.randomUUID();
    const displayText = interaction
      ? options.displayText || interaction.entity?.label || "Selected record"
      : question;
    const userMessageId = `user-${requestId}`;
    const assistantId = `stream-${requestId}`;
    dispatch(appendUserMessage({ id: userMessageId, role: "user", content: displayText }));
    dispatch(startStreaming({ assistantId, userId: userMessageId }));
    setDraft("");

    const controller = new AbortController();
    requestController.current = controller;
    abortMode.current = null;
    try {
      await streamAI(
        {
          conversation_id: active,
          ...(interaction ? { interaction } : { message: question }),
          idempotency_key: requestId,
          context: requestPageContext(options.context, routeKey, locationId),
        },
        (event, data) => {
          if (event === "accepted") dispatch(setStreamStatus("Request received"));
          else if (event === "status") dispatch(setStreamStatus(data.message));
          else if (event === "answer_delta") dispatch(appendTextDelta(data.text));
          else if (event === "artifact") dispatch(appendStreamBlock(data));
          else if (event === "action") dispatch(appendStreamAction(data));
          else if (event === "complete") {
            dispatch(completeStreaming(data));
            setLastCompletedMessageId(data.message?.id || `${data.conversation_id}:${Date.now()}`);
            if (data.ai_wallet) {
              dispatch(baseApi.util.updateQueryData(
                "get",
                { url: "/organization/context" },
                (cached) => {
                  if (cached?.data) cached.data.ai_wallet = data.ai_wallet;
                },
              ));
            }
            dispatch(aiCacheApi.util.invalidateTags([{ type: "Resource", id: "ai" }]));
          } else if (event === "error") {
            throw new AIStreamError(data);
          }
        },
        controller.signal,
      );
      return true;
    } catch (error) {
      if (error.name === "AbortError") {
        const mode = abortMode.current;
        dispatch(cancelStreaming());
        if (mode === "stop") {
          setDraft(question);
          toast.info("Response stopped. Your question is ready to retry.");
        }
      } else {
        dispatch(failStreaming({
          message: error.message || "Edvatiq could not respond",
          code: error.code || "ai_execution_failed",
          stage: error.stage || "execution",
          retryable: error.retryable !== false,
          question: question || displayText,
        }));
        if (!interaction) setDraft(question);
        toast.error(error.message || "Edvatiq could not respond");
      }
      return false;
    } finally {
      if (requestController.current === controller) requestController.current = null;
      abortMode.current = null;
    }
  }, [active, dispatch, draft, locationId, routeKey, streaming]);

  const selectClarificationEntity = useCallback((clarificationId, entity) => sendMessage(null, {
    interaction: {
      type: "select_entity",
      clarification_id: clarificationId,
      entity,
    },
    displayText: entity?.label || "Selected record",
  }), [sendMessage]);

  const stopGeneration = useCallback(() => {
    if (!requestController.current) return;
    abortMode.current = "stop";
    requestController.current.abort();
  }, []);

  const discardActiveStream = useCallback(() => {
    if (!requestController.current) return;
    abortMode.current = "discard";
    requestController.current.abort();
  }, []);

  const selectConversation = useCallback((conversationId) => {
    discardActiveStream();
    dispatch(setActiveConversation(conversationId || null));
  }, [discardActiveStream, dispatch]);

  const startNewConversation = useCallback(() => {
    discardActiveStream();
    if (streaming) dispatch(cancelStreaming());
    dispatch(setActiveConversation(null));
    dispatch(setMessages({ conversationId: null, messages: [] }));
    dispatch(closeResultDrawer());
    setDraft("");
  }, [discardActiveStream, dispatch, streaming]);

  const confirmAction = useCallback(async (action) => {
    try {
      let current = action;
      if (!current.confirmation_token) {
        current = (await api.post(`/ai/actions/${action.action_id}/confirmation`)).data;
      }
      const result = (await api.post(`/ai/actions/${action.action_id}/confirm`, {
        confirmation_token: current.confirmation_token,
      })).data;
      dispatch(updateAction(result));
      toast.success("Action completed");
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || "Could not complete the action");
      return false;
    }
  }, [dispatch]);

  const undoAction = useCallback(async (action) => {
    try {
      const result = (await api.post(`/ai/actions/${action.action_id}/undo`)).data;
      dispatch(updateAction(result));
      toast.success("Action undone");
      return true;
    } catch (error) {
      toast.error(error.response?.data?.detail || "This action could not be undone");
      return false;
    }
  }, [dispatch]);

  const value = useMemo(() => ({
    ...workspace,
    draft,
    setDraft,
    pageContext,
    registerPageContext,
    sendMessage,
    selectClarificationEntity,
    stopGeneration,
    discardActiveStream,
    selectConversation,
    startNewConversation,
    confirmAction,
    undoAction,
    lastCompletedMessageId,
  }), [
    confirmAction,
    discardActiveStream,
    draft,
    lastCompletedMessageId,
    pageContext,
    registerPageContext,
    selectConversation,
    sendMessage,
    selectClarificationEntity,
    startNewConversation,
    stopGeneration,
    undoAction,
    workspace,
  ]);

  return <AIConversationContext.Provider value={value}>{children}</AIConversationContext.Provider>;
}

export function useAIConversation() {
  const value = useContext(AIConversationContext);
  if (!value) throw new Error("useAIConversation must be used within AIConversationProvider");
  return value;
}

export function useRegisterAIPageContext(context) {
  const conversation = useContext(AIConversationContext);
  const registerPageContext = conversation?.registerPageContext;
  const identity = contextIdentity(context);
  useEffect(() => {
    if (!context || !registerPageContext) return undefined;
    return registerPageContext(context);
    // Context objects are often rebuilt from query responses; identity is the stable contract.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity, registerPageContext]);
}
