import React, { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaperPlaneRight, Sparkle, Wrench, CircleNotch, ChatCircleDots } from "@phosphor-icons/react";
import { toast } from "sonner";

const SUGGESTIONS = [
  "How many students do we have?",
  "Show attendance for section A this month",
  "Which students are at risk in CSE?",
  "Search students named Suresh",
  "Give me a summary of the CSE department",
];

export default function AIChat() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  const loadConvos = () => api.get("/ai/conversations").then((r) => setConversations(r.data));
  useEffect(() => { loadConvos(); }, []);

  useEffect(() => {
    if (activeId) api.get(`/ai/conversations/${activeId}/messages`).then((r) => setMessages(r.data));
    else setMessages([]);
  }, [activeId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg) return;
    setSending(true);
    const optimistic = { id: `tmp-${Date.now()}`, role: "user", content: msg, created_at: new Date().toISOString() };
    setMessages((m) => [...m, optimistic]);
    setInput("");
    try {
      const { data } = await api.post("/ai/chat", { conversation_id: activeId, message: msg });
      if (!activeId) { setActiveId(data.conversation_id); loadConvos(); }
      setMessages((m) => [...m, data.message]);
    } catch (err) {
      toast.error(err.response?.data?.detail || "AI failed");
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="h-[calc(100vh-6rem)] flex gap-4" data-testid="ai-chat-page">
      <aside className="w-64 shrink-0 space-y-2 overflow-y-auto">
        <Button onClick={() => { setActiveId(null); setMessages([]); }} variant="outline" className="w-full rounded-sm" data-testid="new-chat-btn">
          <Sparkle size={14} className="mr-2" /> New chat
        </Button>
        {conversations.map((c) => (
          <button key={c.id} onClick={() => setActiveId(c.id)}
            data-testid={`convo-${c.id}`}
            className={`w-full text-left p-3 text-sm rounded-sm border ${activeId === c.id ? "border-accent bg-secondary" : "border-border hover:bg-secondary"}`}>
            <div className="truncate">{c.title}</div>
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1 font-mono">{c.provider} · {c.model}</div>
          </button>
        ))}
      </aside>

      <div className="flex-1 flex flex-col border border-border rounded-sm bg-card">
        <div className="px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Sparkle size={18} weight="fill" className="text-accent" />
            <div className="font-display text-xl tracking-tight">Athena AI</div>
            <span className="overline">tool-calling · tenant-scoped</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">She reads only your organization's data and respects your permissions. Ask anything.</p>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && !sending && (
            <div className="max-w-2xl mx-auto text-center py-10">
              <ChatCircleDots size={40} className="mx-auto text-muted-foreground" />
              <h3 className="mt-4 font-display text-xl">Ask a question</h3>
              <p className="text-sm text-muted-foreground mt-1">Try one of these:</p>
              <div className="mt-4 flex flex-wrap gap-2 justify-center">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="text-xs border border-border px-3 py-2 hover:bg-secondary rounded-sm" data-testid={`suggestion-${s.slice(0, 12)}`}>{s}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-sm ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary"} p-4`}>
                {Array.isArray(m.tool_calls) && m.tool_calls.length > 0 && (
                  <div className="mb-3 font-mono text-[11px] text-muted-foreground border border-border bg-background p-2 space-y-1">
                    {m.tool_calls.map((t, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <Wrench size={12} className="mt-0.5" />
                        <div>
                          <span className="text-accent">{t.name}</span>({JSON.stringify(t.arguments)})
                          {t.result?.count !== undefined && <span className="ml-2 opacity-70">→ {t.result.count} row(s)</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</div>
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-secondary p-4 rounded-sm inline-flex items-center gap-2 text-sm">
                <CircleNotch size={14} className="animate-spin" /> Athena is thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="p-4 border-t border-border">
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2" data-testid="ai-form">
            <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask Athena…" className="rounded-sm" disabled={sending} data-testid="ai-input" />
            <Button type="submit" className="rounded-sm" disabled={sending || !input.trim()} data-testid="ai-send-btn"><PaperPlaneRight size={14} /></Button>
          </form>
        </div>
      </div>
    </div>
  );
}
