from __future__ import annotations


def chunk_text(text: str, max_chars: int = 1400, overlap_chars: int = 200) -> list[str]:
    txt = (text or "").strip()
    if not txt:
        return []
    if len(txt) <= max_chars:
        return [txt]

    chunks: list[str] = []
    start = 0
    n = len(txt)
    step = max(1, max_chars - max(0, overlap_chars))

    while start < n:
        end = min(n, start + max_chars)
        cut = txt[start:end]

        # Prefer sentence-ish boundaries for cleaner retrieval chunks.
        if end < n:
            boundary = max(cut.rfind("\n\n"), cut.rfind(". "), cut.rfind("\n"))
            if boundary > int(max_chars * 0.55):
                end = start + boundary + 1
                cut = txt[start:end]

        chunk = cut.strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break
        start = max(end - overlap_chars, start + step)

    return chunks
