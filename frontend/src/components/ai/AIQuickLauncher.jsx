import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PaperPlaneRight, Sparkle } from "@phosphor-icons/react";

export default function AIQuickLauncher({ open, onOpenChange }) {
  const [question, setQuestion] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const ask = (event) => {
    event.preventDefault();
    const value = question.trim();
    if (!value) return;
    const params = new URLSearchParams({ ask: value });
    const contexts = [
      ["client", /^\/app\/clients\/([^/]+)/],
      ["employee", /^\/app\/team\/([^/]+)/],
      ["catalog", /^\/app\/catalog\/([^/]+)/],
    ];
    const context = contexts
      .map(([kind, pattern]) => [kind, location.pathname.match(pattern)])
      .find(([, match]) => match);
    if (context) {
      params.set("context_kind", context[0]);
      params.set("context_id", context[1][1]);
    }
    onOpenChange(false);
    setQuestion("");
    navigate(`/app/ai?${params}`);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl rounded-3xl">
        <DialogHeader>
          <div className="w-11 h-11 rounded-xl bg-primary text-primary-foreground grid place-items-center mb-3">
            <Sparkle weight="fill" />
          </div>
          <DialogTitle className="font-display text-3xl">
            Ask your business
          </DialogTitle>
          <DialogDescription>
            Get a live answer, find document knowledge, or complete a business
            task.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={ask}
          className="mt-4 flex gap-2 rounded-2xl bg-secondary p-2"
        >
          <input
            autoFocus
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="flex-1 bg-transparent outline-none px-3 text-sm"
            placeholder="What needs your attention today?"
          />
          <Button className="rounded-xl" disabled={!question.trim()}>
            <PaperPlaneRight />
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
