"""Embedding index over the vault with mtime-based caching.

Stores vectors in `<vault>/.vault-mcp/embeddings.json`. Re-embeds only notes
whose mtime changed since the last build, so refreshes are cheap.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from shared.tracing import record_upstream

_MAX_CHARS = 8000
_BATCH = 64


class SemanticIndex:
    def __init__(self, client, *, api_key: str, model: str):
        self._client = client
        self._api_key = api_key
        self._model = model
        self._cache_path: Path = client.root / ".vault-mcp" / "embeddings.json"
        self._vectors: dict[str, list[float]] = {}
        self._mtimes: dict[str, float] = {}
        self._loaded = False

    # --- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if self._loaded:
            return
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self._vectors = data.get("vectors", {})
                self._mtimes = data.get("mtimes", {})
            except (json.JSONDecodeError, OSError):
                self._vectors, self._mtimes = {}, {}
        self._loaded = True

    def _save(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps({"model": self._model, "vectors": self._vectors, "mtimes": self._mtimes}),
            encoding="utf-8",
        )

    # --- embedding -----------------------------------------------------------

    def _openai(self):
        from openai import OpenAI

        return OpenAI(api_key=self._api_key)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        client = self._openai()
        for i in range(0, len(texts), _BATCH):
            batch = [t[:_MAX_CHARS] or " " for t in texts[i : i + _BATCH]]
            start = time.monotonic()
            resp = client.embeddings.create(model=self._model, input=batch)
            record_upstream("openai_embeddings", int((time.monotonic() - start) * 1000))
            out.extend(d.embedding for d in resp.data)
        return out

    def refresh(self) -> dict[str, int]:
        """Re-embed new/changed notes, drop deleted ones."""
        self._load()
        current = {p: self._client.mtime(p) for p in self._client.iter_note_paths()}

        stale = [
            p for p, m in current.items() if self._mtimes.get(p) != m or p not in self._vectors
        ]
        removed = [p for p in list(self._vectors) if p not in current]
        for p in removed:
            self._vectors.pop(p, None)
            self._mtimes.pop(p, None)

        if stale:
            texts = []
            for p in stale:
                title = self._client.basename(p)
                try:
                    body = self._client.read_note(p)
                except OSError:
                    body = ""
                texts.append(f"{title}\n\n{body}")
            vectors = self._embed(texts)
            for p, vec in zip(stale, vectors, strict=True):
                self._vectors[p] = vec
                self._mtimes[p] = current[p]

        if stale or removed:
            self._save()
        return {"embedded": len(stale), "removed": len(removed), "total": len(self._vectors)}

    # --- query ---------------------------------------------------------------

    def _matrix(self) -> tuple[list[str], np.ndarray]:
        paths = list(self._vectors)
        mat = np.array([self._vectors[p] for p in paths], dtype=np.float32)
        if mat.size:
            mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
        return paths, mat

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        self.refresh()
        if not self._vectors:
            return []
        qvec = np.array(self._embed([query])[0], dtype=np.float32)
        qvec /= np.linalg.norm(qvec) + 1e-8
        paths, mat = self._matrix()
        scores = mat @ qvec
        top = np.argsort(-scores)[:k]
        return [{"path": paths[i], "score": round(float(scores[i]), 4)} for i in top]

    def duplicates(self, threshold: float = 0.85) -> list[dict[str, Any]]:
        self.refresh()
        paths, mat = self._matrix()
        if len(paths) < 2:
            return []
        sims = mat @ mat.T
        pairs = []
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                score = float(sims[i, j])
                if score >= threshold:
                    pairs.append({"a": paths[i], "b": paths[j], "score": round(score, 4)})
        pairs.sort(key=lambda p: -p["score"])
        return pairs

    def similar(self, path: str, k: int = 5) -> list[dict[str, Any]]:
        self.refresh()
        if path not in self._vectors:
            return []
        qvec = np.array(self._vectors[path], dtype=np.float32)
        qvec /= np.linalg.norm(qvec) + 1e-8
        paths, mat = self._matrix()
        scores = mat @ qvec
        order = np.argsort(-scores)
        results = []
        for i in order:
            if paths[i] == path:
                continue
            results.append({"path": paths[i], "score": round(float(scores[i]), 4)})
            if len(results) >= k:
                break
        return results
