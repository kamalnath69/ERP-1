export function withoutMarkdownTitle(markdown = "") {
  const lines = String(markdown).replace(/\r/g, "").split("\n");
  const titleIndex = lines.findIndex((line) => line.trim());

  if (titleIndex >= 0 && /^#\s+/.test(lines[titleIndex])) {
    lines.splice(titleIndex, 1);
  }

  return lines.join("\n").trim();
}

export function legalDocumentDate(document) {
  const value = document?.effective_at || document?.published_at;
  if (!value) return "Not yet effective";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "long" }).format(new Date(value));
}

