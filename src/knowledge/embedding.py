"""Text embeddings from multilingual-e5-small, run with ONNX Runtime.

The model turns a text into 384 numbers; texts with a similar meaning get
vectors that point in a similar direction. It is the same model for the
index and for the query, as it has to be.

E5 models expect a prefix: "query: " in front of a question and
"passage: " in front of a text to be found. Leaving it out lowers the
quality, so the two public functions add it themselves.

The model file is not in the repository. It is downloaded once, from a
pinned revision, and kept in the Hugging Face cache.
"""

from typing import Protocol

import numpy as np

import config

QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
PAD_TOKEN = "<pad>"
PAD_TOKEN_ID = 1


class Session(Protocol):
    """The part of an ONNX Runtime session that is used here."""

    def run(self, output_names, input_feed) -> list: ...
    def get_inputs(self) -> list: ...


class Tokenizer(Protocol):
    """The part of a tokenizer that is used here."""

    def encode_batch(self, texts: list[str]) -> list: ...


class Embedder:
    """Turns texts into vectors with the quantized ONNX model."""

    def __init__(self, session: Session, tokenizer: Tokenizer) -> None:
        self._session = session
        self._tokenizer = tokenizer
        self._input_names = {model_input.name for model_input in session.get_inputs()}

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        """Embed questions; one row of unit length per text.

        Args:
            texts (list[str]): The questions.

        Returns:
            One unit-length row per text.
        """
        return self._embed([QUERY_PREFIX + text for text in texts])

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        """Embed texts to be searched; one row of unit length per text.

        Args:
            texts (list[str]): The texts to be searched.

        Returns:
            One unit-length row per text.
        """
        return self._embed([PASSAGE_PREFIX + text for text in texts])

    def _embed(self, texts: list[str]) -> np.ndarray:
        encoded = self._tokenizer.encode_batch(texts)
        token_ids = np.array([item.ids for item in encoded], dtype=np.int64)
        # 1 for a real token, 0 for padding added to make the rows equal.
        mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)

        feed = {"input_ids": token_ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(token_ids)
        token_vectors = self._session.run(None, feed)[0]

        # Mean pooling: the average of the token vectors, padding left out.
        weights = mask[..., np.newaxis]
        text_vectors = (token_vectors * weights).sum(axis=1) / weights.sum(axis=1)
        # Unit length, so a dot product of two rows is their cosine similarity.
        return text_vectors / np.linalg.norm(text_vectors, axis=1, keepdims=True)


def fetch_model_file(filename: str) -> str:
    """The path of one file of the embedding model, downloaded if needed.

    Args:
        filename (str): The file in the model repository.

    Returns:
        The local path of the file.
    """
    # Imported here so that code using only Embedder never loads it.
    from huggingface_hub import hf_hub_download

    return hf_hub_download(
        config.EMBEDDING_MODEL_REPO,
        filename,
        revision=config.EMBEDDING_MODEL_REVISION,
    )


def load_embedder() -> Embedder:
    """Download the model if needed and load it. Needs the network once."""
    # Imported here so that code using only Embedder never loads them.
    import onnxruntime
    from tokenizers import Tokenizer as HubTokenizer

    tokenizer = HubTokenizer.from_file(
        fetch_model_file(config.EMBEDDING_TOKENIZER_FILE)
    )
    tokenizer.enable_padding(pad_id=PAD_TOKEN_ID, pad_token=PAD_TOKEN)
    tokenizer.enable_truncation(max_length=config.EMBEDDING_MAX_TOKENS)
    options = onnxruntime.SessionOptions()
    # Without this, ONNX Runtime keeps the memory of the largest batch it has
    # seen: embedding 28 long passages left 1,141 MB in use instead of 496.
    options.enable_cpu_mem_arena = False
    session = onnxruntime.InferenceSession(
        fetch_model_file(config.EMBEDDING_MODEL_FILE),
        options,
        providers=["CPUExecutionProvider"],
    )
    return Embedder(session, tokenizer)
