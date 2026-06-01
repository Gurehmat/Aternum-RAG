from dataclasses import dataclass

# All BS need to be replaced in future with actual document chunking logic. This is just a placeholder.

@dataclass(frozen=True)
class TextChunk:
    content: str
    word_start: int
    word_end: int


def split_text_into_chunks(text: str, max_words: int = 220, overlap_words: int = 45) -> list[TextChunk]:
    if max_words <= 0:
        raise ValueError("max_words must be greater than zero")
    if overlap_words < 0:
        raise ValueError("overlap_words cannot be negative")
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words")

    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [TextChunk(content=" ".join(words), word_start=0, word_end=len(words))]

    text_chunks: list[TextChunk] = []
    step_size = max_words - overlap_words

    for word_start in range(0, len(words), step_size):
        word_end = min(word_start + max_words, len(words))
        chunk_content = " ".join(words[word_start:word_end])
        text_chunks.append(TextChunk(content=chunk_content, word_start=word_start, word_end=word_end))

        if word_end >= len(words):
            break

    return text_chunks
