from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    char_start: int
    char_end: int
    content: str


def split_text(text: str, *, size: int = 500, overlap: int = 80) -> list[Chunk]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("invalid chunk size or overlap")

    paragraphs: list[tuple[int, int]] = []
    cursor = 0
    for separator in re.finditer(r"\n\s*\n", text):
        span = _trimmed_span(text, cursor, separator.start())
        if span:
            paragraphs.append(span)
        cursor = separator.end()
    span = _trimmed_span(text, cursor, len(text))
    if span:
        paragraphs.append(span)

    chunks: list[Chunk] = []
    current: tuple[int, int] | None = None

    def flush(start: int, end: int) -> None:
        position = start
        while position < end:
            stop = min(position + size, end)
            chunks.append(Chunk(len(chunks), position, stop, text[position:stop]))
            if stop == end:
                break
            position = stop - overlap

    for start, end in paragraphs:
        if current and end - current[0] <= size:
            current = (current[0], end)
            continue
        if current:
            flush(*current)
            current = None
        if end - start > size:
            flush(start, end)
        else:
            current = (start, end)
    if current:
        flush(*current)
    return chunks


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None
