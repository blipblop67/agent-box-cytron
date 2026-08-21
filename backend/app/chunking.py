"""
A small, dependency-free recursive splitter. Deliberately not pulling in a
framework's text-splitter here - this is ~30 lines and it's the kind of thing
someone learning the system should be able to open and actually read.

Strategy: try to break on paragraph boundaries, then sentences, then just
hard-wrap on characters as a last resort - always keeping some overlap between
chunks so a fact that spans a chunk boundary doesn't get lost.
"""
SEPARATORS = ["\n\n", "\n", ". ", " "]


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    pieces = _split_recursive(text, chunk_size)
    return _merge_with_overlap(pieces, chunk_size, chunk_overlap)


def _split_recursive(text: str, chunk_size: int, sep_index: int = 0) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    if sep_index >= len(SEPARATORS):
        # last resort: hard character split
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    sep = SEPARATORS[sep_index]
    parts = text.split(sep)
    if len(parts) == 1:
        return _split_recursive(text, chunk_size, sep_index + 1)

    out: list[str] = []
    for part in parts:
        if len(part) > chunk_size:
            out.extend(_split_recursive(part, chunk_size, sep_index + 1))
        elif part.strip():
            out.append(part)
    return out


def _merge_with_overlap(pieces: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip() if current else piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = (current[-chunk_overlap:] + " " + piece).strip() if chunk_overlap else piece
    if current:
        chunks.append(current)
    return chunks
