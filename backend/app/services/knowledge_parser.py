"""本地知识库文本解析与语义分块。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


PARSER_VERSION = "1.0"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json"}


@dataclass
class ParsedChunk:
    content: str
    chunk_index: int
    section_title: str | None = None
    heading_path: list[str] | None = None
    start_offset: int | None = None
    end_offset: int | None = None


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _heading_level(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line.strip())
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _split_blocks(text: str) -> list[tuple[str, list[str], str | None, int, int]]:
    """按 Markdown 标题和段落切块，保留标题路径与原文偏移。"""
    lines = text.splitlines(keepends=True)
    headings: list[str] = []
    blocks: list[tuple[str, list[str], str | None, int, int]] = []
    buffer: list[str] = []
    start = 0
    offset = 0

    def flush(end_offset: int) -> None:
        nonlocal buffer, start
        content = "".join(buffer).strip()
        if content:
            blocks.append((content, headings.copy(), headings[-1] if headings else None, start, end_offset))
        buffer = []

    for line in lines:
        heading = _heading_level(line)
        if heading:
            flush(offset)
            level, title = heading
            headings[:] = headings[: level - 1]
            headings.append(title)
        elif line.strip():
            if not buffer:
                start = offset
            buffer.append(line)
        elif buffer:
            buffer.append(line)
        offset += len(line)
    flush(offset)
    return blocks


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[。！？!?；;])", text)
    result: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if current and len(current) + len(sentence) > max_chars:
            result.append(current.strip())
            current = ""
        if len(sentence) > max_chars:
            for index in range(0, len(sentence), max_chars):
                piece = sentence[index:index + max_chars].strip()
                if piece:
                    result.append(piece)
            current = ""
        else:
            current += sentence
    if current.strip():
        result.append(current.strip())
    return result


def chunk_text(text: str, max_chars: int = 420, overlap_chars: int = 60) -> list[ParsedChunk]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    raw_blocks = _split_blocks(normalized)
    chunks: list[ParsedChunk] = []
    for block, headings, section_title, start, end in raw_blocks:
        pieces = _split_long_text(block, max_chars)
        for piece_index, piece in enumerate(pieces):
            if chunks and overlap_chars and piece_index == 0:
                previous = chunks[-1].content[-overlap_chars:]
                piece = f"{previous}\n{piece}"
            chunks.append(ParsedChunk(
                content=piece.strip(),
                chunk_index=len(chunks),
                section_title=section_title,
                heading_path=headings,
                start_offset=start,
                end_offset=end,
            ))
    return chunks


def sha256_bytes(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
