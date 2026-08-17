import React from "react";
import {
  CircleNotch,
  Copy,
  DotsThreeVertical,
  ThumbsDown,
  ThumbsUp,
  Trash,
} from "@phosphor-icons/react";

import BrandLogo from "@/components/brand/BrandLogo";
import ResponseBlocks from "@/components/ai/ResponseBlocks";
import RichText from "@/components/ai/RichText";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export default function AIMessage({
  message,
  isCollege = false,
  isStreaming,
  streamStatus,
  onDelete,
  onCopy,
  onFeedback,
  compact = false,
  ...actions
}) {
  const user = message.role === "user";
  return (
    <div className={cn(
      "group mx-auto flex w-full",
      compact ? "max-w-none" : "max-w-5xl",
      user ? "justify-end" : "justify-start",
    )}>
      <div className={cn(
        "relative min-w-0",
        user
          ? cn(
              "rounded-[1.25rem] rounded-br-md bg-primary text-primary-foreground shadow-sm",
              compact ? "max-w-[88%] px-3.5 py-2.5" : "max-w-[88%] px-4 py-3 md:max-w-[72%]",
            )
          : "w-full",
      )}>
        {user && onDelete && (
          <HistoryMenu onDelete={onDelete} label="Message options" className="absolute -left-10 top-0" />
        )}
        {user ? (
          <div className={cn("whitespace-pre-wrap text-sm", compact ? "leading-6" : "leading-7")}>
            {message.content}
          </div>
        ) : (
          <>
            <div className={cn("flex items-center", compact ? "mb-2 gap-2" : "mb-2.5 gap-2.5")}>
              <BrandLogo
                showName={false}
                markClassName={compact ? "h-7 w-7 rounded-lg" : "h-8 w-8 rounded-xl"}
              />
              <div className="min-w-0">
                <div className="text-sm font-semibold">Edvatiq</div>
                <div className="text-[10px] text-muted-foreground">
                  {isCollege ? "Your placement assistant" : "Your business assistant"}
                </div>
              </div>
              {onDelete && <HistoryMenu onDelete={onDelete} label="Message options" className="ml-auto" />}
            </div>
            {message.content ? (
              <div className={cn(
                "rounded-2xl rounded-tl-md border bg-card/80 shadow-[0_8px_26px_hsl(var(--primary)/.04)]",
                compact ? "px-3.5 py-3 text-sm" : "px-4 py-3.5 md:px-5",
              )}>
                <RichText>{message.content}</RichText>
              </div>
            ) : isStreaming ? <Thinking status={streamStatus} compact={compact} /> : null}
            {isStreaming && message.content && (
              <div className="mt-2 flex items-center gap-2 px-1 text-xs text-muted-foreground">
                <CircleNotch className="animate-spin text-accent" />
                {streamStatus || "Preparing your answer"}
              </div>
            )}
            <ResponseBlocks message={message} compact={compact} {...actions} />
            {!isStreaming && message.content && onCopy && onFeedback && (
              <div className="mt-1.5 flex items-center gap-0.5 px-1 text-muted-foreground">
                <MessageAction label="Copy response" onClick={onCopy} compact={compact}>
                  <Copy size={compact ? 14 : 15} />
                </MessageAction>
                <MessageAction
                  label="Helpful"
                  active={message.feedback_rating === "helpful"}
                  onClick={() => onFeedback("helpful")}
                  compact={compact}
                >
                  <ThumbsUp size={compact ? 14 : 15} weight={message.feedback_rating === "helpful" ? "fill" : "regular"} />
                </MessageAction>
                <MessageAction
                  label="Not helpful"
                  active={message.feedback_rating === "not_helpful"}
                  onClick={() => onFeedback("not_helpful")}
                  compact={compact}
                >
                  <ThumbsDown size={compact ? 14 : 15} weight={message.feedback_rating === "not_helpful" ? "fill" : "regular"} />
                </MessageAction>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function MessageAction({ label, active = false, onClick, children, compact = false }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active || undefined}
      onClick={onClick}
      className={cn(
        "grid place-items-center rounded-lg transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        compact ? "h-7 w-7" : "h-8 w-8",
        active && "bg-secondary text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function HistoryMenu({ onDelete, disabled = false, label, className = "" }) {
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
          <DotsThreeVertical size={18} weight="bold" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="z-[100]">
        <DropdownMenuItem onSelect={onDelete} className="text-red-600 focus:text-red-700">
          <Trash className="mr-2" />
          Delete question and answer
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Thinking({ status, compact = false }) {
  return (
    <div className={cn(
      "inline-flex items-center gap-3 rounded-2xl rounded-tl-md border bg-card/80 text-sm text-muted-foreground shadow-sm",
      compact ? "px-3.5 py-2.5" : "px-4 py-3",
    )}>
      <span className="flex gap-1" aria-hidden="true">
        <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent" />
        <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:120ms]" />
        <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:240ms]" />
      </span>
      {status || "Working on your answer"}
    </div>
  );
}
