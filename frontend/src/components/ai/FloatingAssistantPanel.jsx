import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import { useNavigate } from "react-router-dom";
import {
  ArrowSquareOut,
  ChatCircleDots,
  CircleNotch,
  PaperPlaneRight,
  Plus,
  Stop,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import AIMessage from "@/components/ai/AIMessage";
import { contextIdentity, useAIConversation } from "@/components/ai/AIConversationProvider";
import BrandLogo from "@/components/brand/BrandLogo";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useGetAIConversationQuery,
  useGetConversationMessagePageQuery,
  useSubmitAIMessageFeedbackMutation,
} from "@/store/api/aiCacheApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import {
  openResultDrawer,
  setMessageFeedback,
  setMessages,
} from "@/store/slices/aiSlice";

const EMPTY_MESSAGES = Object.freeze([]);
const suggestions = {
  college: [
    "Who needs placement support today?",
    "Show students with missing readiness evidence",
  ],
  business: [
    "What needs my attention today?",
    "Show today's business snapshot",
  ],
};

function useDesktopPanel() {
  const [desktop, setDesktop] = useState(() => (
    typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches
  ));
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  return desktop;
}

function requestContext(context) {
  if (!context) return null;
  const { label: _label, ...payload } = context;
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value != null && value !== ""),
  );
}

export default function FloatingAssistantPanel({ open, onOpenChange }) {
  const desktop = useDesktopPanel();
  const content = <AssistantSurface onClose={() => onOpenChange(false)} />;

  if (desktop) {
    if (!open) return null;
    return (
      <aside
        role="dialog"
        aria-modal="false"
        aria-label="Edvatiq assistant"
        className="fixed bottom-5 right-5 z-[70] flex h-[min(700px,calc(100dvh-6.25rem))] w-[min(430px,calc(100vw-2.5rem))] min-h-[440px] flex-col overflow-hidden rounded-[1.5rem] border bg-card shadow-[0_28px_80px_hsl(var(--foreground)/.20)] animate-in fade-in-0 slide-in-from-bottom-3 duration-200"
      >
        {content}
      </aside>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        aria-describedby={undefined}
        className="bottom-[calc(4.25rem+env(safe-area-inset-bottom))] flex h-[min(84dvh,760px)] flex-col gap-0 overflow-hidden rounded-t-[1.5rem] p-0 md:bottom-0 md:h-[min(86dvh,800px)] [&>button]:hidden"
      >
        <SheetTitle className="sr-only">Edvatiq assistant</SheetTitle>
        {content}
      </SheetContent>
    </Sheet>
  );
}

function AssistantSurface({ onClose }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { industry } = useBusiness();
  const isCollege = industry === "college";
  const {
    activeConversationId: active,
    messages = EMPTY_MESSAGES,
    streaming,
    streamStatus,
    streamError,
    draftAssistantId,
    pendingHistoryConversationId,
    pendingHistoryMessageId,
    draft,
    setDraft,
    pageContext,
    sendMessage,
    stopGeneration,
    startNewConversation,
    confirmAction,
    undoAction,
  } = useAIConversation();
  const detailQuery = useGetAIConversationQuery(
    active,
    withSkip(QUERY_POLICIES.reference, !active),
  );
  const messagesQuery = useGetConversationMessagePageQuery(
    { conversationId: active, limit: 20 },
    withSkip(QUERY_POLICIES.reference, !active),
  );
  const [submitFeedback, feedbackState] = useSubmitAIMessageFeedbackMutation();
  const [feedbackTarget, setFeedbackTarget] = useState(null);
  const [feedbackReason, setFeedbackReason] = useState("");
  const [contextEnabled, setContextEnabled] = useState(true);
  const viewportRef = useRef(null);
  const inputRef = useRef(null);
  const contextKey = contextIdentity(pageContext);
  const activeConversation = detailQuery.currentData;
  const page = messagesQuery.currentData;
  const conversationUnavailable = Boolean(active && (detailQuery.isError || messagesQuery.isError));
  const conversationReadOnly = Boolean(activeConversation?.archived_at || conversationUnavailable);
  const loadingConversation = Boolean(active && messagesQuery.isFetching && !messages.length);
  const visibleMessages = useMemo(() => messages.slice(-20), [messages]);

  useEffect(() => setContextEnabled(true), [contextKey]);

  useEffect(() => {
    const incoming = page?.items;
    if (!active || !incoming || streaming) return;
    const waitingForCompletedMessage = (
      pendingHistoryConversationId === active
      && pendingHistoryMessageId
      && !incoming.some((message) => message.id === pendingHistoryMessageId)
    );
    if (!waitingForCompletedMessage) {
      dispatch(setMessages({ conversationId: active, messages: incoming, preserveOlder: true }));
    }
  }, [
    active,
    dispatch,
    page?.items,
    pendingHistoryConversationId,
    pendingHistoryMessageId,
    streaming,
  ]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  }, [draftAssistantId, messages.length, streamStatus, visibleMessages.at(-1)?.content]);

  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 104)}px`;
  }, [draft]);

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === "Escape" && !feedbackTarget) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [feedbackTarget, onClose]);

  const openFullAI = ({ result } = {}) => {
    if (result) dispatch(openResultDrawer(result));
    navigate(active ? `/app/ai?chat=${encodeURIComponent(active)}` : "/app/ai");
    onClose();
  };

  const submit = (value = draft, explicitContext = undefined) => {
    const question = String(value || "").trim();
    if (!question || streaming || conversationReadOnly) return;
    void sendMessage(question, {
      context: explicitContext === undefined
        ? (contextEnabled ? requestContext(pageContext) : null)
        : explicitContext,
      readOnly: conversationReadOnly,
    });
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
      await submitFeedback({
        conversationId: active,
        messageId: message.id,
        rating,
        reason: reason.trim(),
      }).unwrap();
      dispatch(setMessageFeedback({ conversationId: active, messageId: message.id, rating }));
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
    void saveFeedback(message, rating);
  };

  const createNew = () => {
    if (streaming) {
      toast.info("Stop the current response before starting a new chat");
      return;
    }
    startNewConversation();
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  return (
    <>
      <header className="flex h-[4.5rem] shrink-0 items-center gap-3 border-b bg-card/95 px-4 backdrop-blur-xl">
        <BrandLogo showName={false} markClassName="h-9 w-9 rounded-xl" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">Edvatiq assistant</div>
          <div className="truncate text-[11px] text-muted-foreground">
            {activeConversation?.title || (streaming ? streamStatus || "Working on your answer" : "Grounded in your workspace")}
          </div>
        </div>
        <Button type="button" variant="ghost" size="icon" onClick={createNew} disabled={streaming} title="New chat" aria-label="New chat">
          <Plus />
        </Button>
        <Button type="button" variant="ghost" size="icon" onClick={() => openFullAI()} title="Open full AI" aria-label="Open full AI">
          <ArrowSquareOut />
        </Button>
        <Button type="button" variant="ghost" size="icon" onClick={onClose} title="Close assistant" aria-label="Close assistant">
          <X />
        </Button>
      </header>

      {pageContext && contextEnabled && (
        <div className="flex shrink-0 items-center gap-2 border-b bg-secondary/35 px-4 py-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Using</span>
          <span className="min-w-0 flex-1 truncate text-xs font-medium">{pageContext.label || "Current page"}</span>
          <button type="button" onClick={() => setContextEnabled(false)} className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-card hover:text-foreground" aria-label="Remove page context">
            <X size={12} weight="bold" />
          </button>
        </div>
      )}

      <div ref={viewportRef} className="premium-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto bg-background/70 px-4 py-4" aria-live="polite">
        {loadingConversation ? <AssistantSkeleton /> : null}
        {!loadingConversation && !visibleMessages.length && !conversationUnavailable && (
          <CompactWelcome isCollege={isCollege} onAsk={submit} />
        )}
        {conversationUnavailable && !visibleMessages.length && (
          <RecoveryState
            title="This chat is no longer available"
            description="It may have expired, been removed, or no longer be within your access."
            onNew={createNew}
          />
        )}
        {activeConversation?.archived_at && !visibleMessages.length && (
          <RecoveryState
            title="This chat is archived"
            description="Open the full AI workspace to restore it, or begin a new chat here."
            onNew={createNew}
            onOpen={openFullAI}
          />
        )}
        {messages.length > visibleMessages.length && (
          <button type="button" onClick={() => openFullAI()} className="mx-auto block rounded-full border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
            Earlier messages in full AI
          </button>
        )}
        {visibleMessages.map((message) => (
          <AIMessage
            key={message.id}
            message={message}
            compact
            isCollege={isCollege}
            isStreaming={streaming && message.id === draftAssistantId}
            streamStatus={streamStatus}
            onCopy={() => copyMessage(message)}
            onFeedback={(rating) => rateMessage(message, rating)}
            onViewAll={({ sessionId, querySpec, title }) => openFullAI({
              result: { id: sessionId, querySpec, title },
            })}
            onConfirm={confirmAction}
            onUndo={undoAction}
            onSelectEntity={(item) => submit(
              `Tell me about ${item.display_name || "this record"}`,
              item.selection_ref,
            )}
          />
        ))}
        {streamError && !streaming && (
          <div className="flex items-start gap-2 rounded-xl border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
            <WarningCircle className="mt-0.5 shrink-0" />
            <span className="flex-1">{streamError}</span>
            <button type="button" className="font-semibold underline underline-offset-2" onClick={() => submit()}>Retry</button>
          </div>
        )}
      </div>

      <form
        onSubmit={(event) => { event.preventDefault(); submit(); }}
        className="shrink-0 border-t bg-card/95 p-3 pb-[max(.75rem,env(safe-area-inset-bottom))] backdrop-blur-xl"
      >
        {conversationReadOnly ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border bg-secondary/50 px-3 py-2.5 text-xs text-muted-foreground">
            <span>{activeConversation?.archived_at ? "This chat is archived and read-only." : "Start a new chat to continue."}</span>
            <Button type="button" size="sm" variant="outline" onClick={createNew}>New chat</Button>
          </div>
        ) : (
          <div className="flex items-end gap-2 rounded-2xl border bg-background p-2 shadow-sm focus-within:border-primary/35 focus-within:ring-2 focus-within:ring-primary/10">
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              rows={1}
              maxLength={5000}
              disabled={streaming}
              placeholder={isCollege ? "Ask about students, readiness, or placements..." : "Ask about your business..."}
              className="premium-scrollbar min-h-10 flex-1 resize-none bg-transparent px-2 py-2.5 text-sm leading-5 outline-none placeholder:text-muted-foreground/70 disabled:opacity-60"
            />
            {streaming ? (
              <Button type="button" size="icon" variant="outline" onClick={stopGeneration} aria-label="Stop generating" title="Stop generating">
                <Stop weight="fill" />
              </Button>
            ) : (
              <Button type="submit" size="icon" disabled={!draft.trim()} aria-label="Send message" title="Send message">
                <PaperPlaneRight weight="fill" />
              </Button>
            )}
          </div>
        )}
      </form>

      <Dialog open={Boolean(feedbackTarget)} onOpenChange={(next) => { if (!next) setFeedbackTarget(null); }}>
        <DialogContent className="rounded-2xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle>What could be better?</DialogTitle>
            <DialogDescription>This is optional and helps us improve Edvatiq responses.</DialogDescription>
          </DialogHeader>
          <textarea
            autoFocus
            value={feedbackReason}
            onChange={(event) => setFeedbackReason(event.target.value)}
            maxLength={500}
            rows={4}
            className="w-full resize-none rounded-xl border bg-background p-3 text-sm outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10"
            placeholder="The answer was incomplete, incorrect, or not relevant..."
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setFeedbackTarget(null)}>Cancel</Button>
            <Button
              type="button"
              loading={feedbackState.isLoading}
              loadingText="Sending"
              onClick={() => {
                void saveFeedback(feedbackTarget, "not_helpful", feedbackReason).then((saved) => {
                  if (saved) setFeedbackTarget(null);
                });
              }}
            >
              Send feedback
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function CompactWelcome({ isCollege, onAsk }) {
  const items = isCollege ? suggestions.college : suggestions.business;
  return (
    <section className="rounded-2xl border bg-card p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground"><ChatCircleDots weight="duotone" /></span>
        <div>
          <h2 className="text-sm font-semibold">What can I help with?</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">Ask naturally. I’ll use only records and actions you are allowed to access.</p>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {items.map((item) => (
          <button key={item} type="button" onClick={() => onAsk(item)} className="flex w-full items-center justify-between gap-3 rounded-xl border bg-background px-3 py-2.5 text-left text-xs font-medium transition-colors hover:border-primary/25 hover:bg-secondary/50">
            <span>{item}</span>
            <PaperPlaneRight className="shrink-0 text-accent" />
          </button>
        ))}
      </div>
    </section>
  );
}

function RecoveryState({ title, description, onNew, onOpen }) {
  return (
    <section className="rounded-2xl border bg-card p-5 text-center shadow-sm">
      <WarningCircle className="mx-auto text-accent" size={28} />
      <h2 className="mt-3 text-sm font-semibold">{title}</h2>
      <p className="mx-auto mt-1 max-w-xs text-xs leading-5 text-muted-foreground">{description}</p>
      <div className="mt-4 flex justify-center gap-2">
        <Button type="button" size="sm" onClick={onNew}>New chat</Button>
        {onOpen && <Button type="button" size="sm" variant="outline" onClick={onOpen}>Open full AI</Button>}
      </div>
    </section>
  );
}

function AssistantSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading conversation">
      <div className="ml-auto h-16 w-3/4 animate-pulse rounded-2xl bg-secondary" />
      <div className="space-y-2 rounded-2xl border bg-card p-4">
        <div className="flex items-center gap-2"><CircleNotch className="animate-spin text-accent" /><span className="text-xs text-muted-foreground">Loading your chat</span></div>
        <div className="h-3 w-full animate-pulse rounded bg-secondary" />
        <div className="h-3 w-4/5 animate-pulse rounded bg-secondary" />
      </div>
    </div>
  );
}
