import React, { useMemo, useState } from "react";
import { Check, Copy } from "@phosphor-icons/react";

function safeHref(value = "") {
  const href = value.trim();
  if (href.startsWith("/") || href.startsWith("#")) return href;
  try {
    const url = new URL(href);
    return ["https:", "mailto:"].includes(url.protocol) ? href : "#";
  } catch { return "#"; }
}

function inline(text) {
  const parts = String(text).split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index} className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[.9em]">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      const href = safeHref(link[2]);
      const external = href.startsWith("https://");
      return <a key={index} href={href} target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined} className="font-medium text-accent underline decoration-accent/35 underline-offset-4 hover:decoration-accent">{link[1]}</a>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-");
}

export function markdownHeadings(markdown = "") {
  return markdown.split("\n").map((line) => line.match(/^(#{2,3})\s+(.+)$/)).filter(Boolean).map((match) => ({ level: match[1].length, title: match[2], id: slug(match[2]) }));
}

function CodeBlock({ language, value }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };
  return <div className="my-6 overflow-hidden rounded-xl border bg-[hsl(165_30%_9%)] text-white"><div className="flex items-center justify-between border-b border-white/10 px-4 py-2 text-[11px] text-white/55"><span>{language || "text"}</span><button type="button" onClick={copy} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-white/10">{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy"}</button></div><pre className="overflow-x-auto p-4 font-mono text-xs leading-6"><code>{value}</code></pre></div>;
}

export default function SafeMarkdown({ content = "", className = "" }) {
  const blocks = useMemo(() => {
    const lines = content.replace(/\r/g, "").split("\n");
    const output = [];
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index += 1; continue; }
      if (line.startsWith("```")) {
        const language = line.slice(3).trim();
        const values = [];
        index += 1;
        while (index < lines.length && !lines[index].startsWith("```")) { values.push(lines[index]); index += 1; }
        output.push({ type: "code", language, value: values.join("\n") });
        index += 1;
        continue;
      }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) { output.push({ type: "heading", level: heading[1].length, value: heading[2] }); index += 1; continue; }
      if (/^[-*]\s+/.test(line)) {
        const values = [];
        while (index < lines.length && /^[-*]\s+/.test(lines[index])) { values.push(lines[index].replace(/^[-*]\s+/, "")); index += 1; }
        output.push({ type: "ul", values }); continue;
      }
      if (/^\d+\.\s+/.test(line)) {
        const values = [];
        while (index < lines.length && /^\d+\.\s+/.test(lines[index])) { values.push(lines[index].replace(/^\d+\.\s+/, "")); index += 1; }
        output.push({ type: "ol", values }); continue;
      }
      if (line.startsWith("> ")) { output.push({ type: "quote", value: line.slice(2) }); index += 1; continue; }
      const values = [line.trim()];
      index += 1;
      while (index < lines.length && lines[index].trim() && !/^(#{1,4})\s|^```|^[-*]\s+|^\d+\.\s+|^>\s+/.test(lines[index])) { values.push(lines[index].trim()); index += 1; }
      output.push({ type: "paragraph", value: values.join(" ") });
    }
    return output;
  }, [content]);

  return <article className={`public-prose ${className}`}>{blocks.map((block, index) => {
    if (block.type === "code") return <CodeBlock key={index} language={block.language} value={block.value} />;
    if (block.type === "heading") {
      const Tag = `h${block.level}`;
      return <Tag key={index} id={slug(block.value)}>{inline(block.value)}</Tag>;
    }
    if (block.type === "ul") return <ul key={index}>{block.values.map((value) => <li key={value}>{inline(value)}</li>)}</ul>;
    if (block.type === "ol") return <ol key={index}>{block.values.map((value) => <li key={value}>{inline(value)}</li>)}</ol>;
    if (block.type === "quote") return <blockquote key={index}>{inline(block.value)}</blockquote>;
    return <p key={index}>{inline(block.value)}</p>;
  })}</article>;
}
