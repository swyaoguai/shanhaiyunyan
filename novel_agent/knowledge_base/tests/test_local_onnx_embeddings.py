import math
from types import SimpleNamespace

import numpy as np
import pytest

from novel_agent.knowledge_base.config import LocalOnnxConfig
from novel_agent.knowledge_base.logic_layer.embeddings import LocalOnnxEmbeddingService


class _Encoding:
    def __init__(self, ids):
        self.ids = ids
        self.attention_mask = [1 if item else 0 for item in ids]
        self.type_ids = [0 for _ in ids]


class _Tokenizer:
    def encode_batch(self, texts):
        encoded = []
        for text in texts:
            ids = [len(text), 1, 0]
            encoded.append(_Encoding(ids))
        return encoded


class _Session:
    def get_inputs(self):
        return [
            SimpleNamespace(name="input_ids"),
            SimpleNamespace(name="attention_mask"),
            SimpleNamespace(name="token_type_ids"),
        ]

    def run(self, output_names, inputs):
        input_ids = inputs["input_ids"].astype(np.float32)
        batch, seq = input_ids.shape
        hidden = np.zeros((batch, seq, 3), dtype=np.float32)
        hidden[:, :, 0] = input_ids
        hidden[:, :, 1] = 1.0
        hidden[:, :, 2] = np.arange(seq, dtype=np.float32)
        return [hidden]


def test_local_onnx_embed_batch_mean_pools_and_normalizes():
    service = LocalOnnxEmbeddingService(
        LocalOnnxConfig(model_name="fake-bge", max_length=3),
        session=_Session(),
        tokenizer=_Tokenizer(),
    )

    vectors = service.embed_batch(["秦川入城", "云烟"])

    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1]) == 3
    assert math.isclose(sum(value * value for value in vectors[0]), 1.0, rel_tol=1e-6)
    assert service.get_model_info()["provider"] == "local_onnx"
    assert service.get_model_info()["embedding_dim"] == 3


def test_local_onnx_empty_text_handling_is_explicit():
    service = LocalOnnxEmbeddingService(
        LocalOnnxConfig(model_name="fake-bge", max_length=3),
        session=_Session(),
        tokenizer=_Tokenizer(),
    )

    with pytest.raises(ValueError):
        service.embed("")

    assert service.embed_batch([""]) == [[]]
