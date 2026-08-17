"""Heading-aware, bounded document chunking for hybrid retrieval."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SemanticChunk:
    page_number: int | None
    section: str | None
    content: str
    token_count: int
    partial_index: bool = False


def estimate_tokens(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    return max(1, len(text) // 4, int(words * 1.25))


def _is_heading(line: str) -> bool:
    value = line.strip().strip("#").strip()
    if not value or len(value) > 140 or value.endswith(('.', '?', '!', ';')):
        return False
    if line.lstrip().startswith("#"):
        return True
    letters = [character for character in value if character.isalpha()]
    if letters and len(value.split()) <= 12 and all(character.isupper() for character in letters):
        return True
    return bool(re.match(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z][\w &'(),:/-]{2,100}$", value)) and len(value.split()) <= 10


def _sections(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    body: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if _is_heading(line):
            if body:
                sections.append((heading, "\n".join(body).strip()))
            heading = line.strip("# ")[:250]
            body = []
        elif line:
            body.append(line)
        elif body and body[-1] != "":
            body.append("")
    if body:
        sections.append((heading, "\n".join(body).strip()))
    return sections or [(None, text.strip())]


def _windows(text: str, *, minimum: int, maximum: int, overlap: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
    units: list[str] = []
    for paragraph in paragraphs:
        if estimate_tokens(paragraph) <= maximum:
            units.append(paragraph)
        else:
            units.extend(_split_long_text(paragraph, maximum=maximum, overlap=overlap))

    windows: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip() if current else unit
        if current and estimate_tokens(candidate) > maximum:
            windows.append(current)
            overlap_text = _tail_for_tokens(current, overlap)
            candidate = f"{overlap_text}\n\n{unit}".strip() if overlap_text else unit
            current = candidate if estimate_tokens(candidate) <= maximum else unit
        else:
            current = candidate
    if current:
        rendered = current
        if windows and estimate_tokens(rendered) < minimum:
            combined = f"{windows[-1]}\n\n{rendered}".strip()
            if estimate_tokens(combined) <= maximum:
                windows[-1] = combined
            else:
                windows.append(rendered)
        else:
            windows.append(rendered)
    return windows


def _tail_for_tokens(text: str, target_tokens: int) -> str:
    if target_tokens <= 0:
        return ""
    words = text.split()
    start = len(words)
    while start > 0:
        candidate = " ".join(words[start - 1:])
        if estimate_tokens(candidate) > target_tokens:
            break
        start -= 1
    return " ".join(words[start:]).strip()


def _split_long_text(text: str, *, maximum: int, overlap: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        piece = ""
        while end < len(words):
            candidate = " ".join(words[start:end + 1])
            if piece and estimate_tokens(candidate) > maximum:
                break
            piece = candidate
            end += 1
            if estimate_tokens(piece) >= maximum:
                break
        if not piece:
            piece = words[start]
            end = start + 1
        chunks.append(piece)
        if end >= len(words):
            break
        overlap_text = _tail_for_tokens(piece, overlap)
        overlap_words = len(overlap_text.split())
        start = max(start + 1, end - overlap_words)
    return chunks


def chunk_document_pages(
    pages: list[tuple[int | None, str]],
    *,
    minimum_tokens: int = 400,
    maximum_tokens: int = 700,
    overlap_tokens: int = 80,
    max_chunks: int = 1000,
) -> list[SemanticChunk]:
    chunks: list[SemanticChunk] = []
    truncated = False
    for page_number, page_text in pages:
        for section, body in _sections(page_text):
            for content in _windows(
                body, minimum=minimum_tokens, maximum=maximum_tokens, overlap=overlap_tokens,
            ):
                if len(chunks) >= max_chunks:
                    truncated = True
                    break
                chunks.append(SemanticChunk(
                    page_number=page_number, section=section, content=content,
                    token_count=estimate_tokens(content),
                ))
            if truncated:
                break
        if truncated:
            break
    if truncated and chunks:
        last = chunks[-1]
        chunks[-1] = SemanticChunk(
            page_number=last.page_number, section=last.section, content=last.content,
            token_count=last.token_count, partial_index=True,
        )
    return chunks
