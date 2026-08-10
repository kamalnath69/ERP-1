import React from "react";

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g;

function inline(text) {
  return String(text).split(INLINE).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index} className="rounded bg-secondary px-1.5 py-0.5 text-[.9em]">{part.slice(1, -1)}</code>;
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
    if (link) return <a key={index} href={link[2]} target="_blank" rel="noreferrer" className="font-medium text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent">{link[1]}</a>;
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

export default function RichText({ children }) {
  const lines = String(children || "").split("\n");
  return <div className="space-y-2.5 text-[14px] leading-7 text-foreground/90">{lines.map((line, index) => {
    if (!line.trim()) return <div key={index} className="h-1" />;
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) return <div key={index} className={`${heading[1].length === 1 ? "text-xl" : "text-lg"} pt-1 font-display font-semibold text-foreground`}>{inline(heading[2])}</div>;
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) return <div key={index} className="flex items-start gap-3 pl-1"><span aria-hidden="true" className="mt-[.68rem] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" /><span>{inline(bullet[1])}</span></div>;
    const numbered = line.match(/^(\d+)\.\s+(.+)$/);
    if (numbered) return <div key={index} className="flex items-start gap-3 pl-1"><span className="mt-1 h-5 min-w-5 rounded-md bg-secondary px-1 text-center text-[10px] font-semibold leading-5 text-muted-foreground">{numbered[1]}</span><span>{inline(numbered[2])}</span></div>;
    return <p key={index}>{inline(line)}</p>;
  })}</div>;
}
