from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class VectorStoreError(Exception):
    pass


class VectorStore:
    def __init__(self, url: str, collection: str, dimension: int):
        self.url = url.rstrip("/")
        self.collection = collection
        self.dimension = dimension

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            self.url + path, data=body, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise VectorStoreError("collection_not_found") from exc
            raise VectorStoreError("vector store request failed") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise VectorStoreError("vector store unavailable") from exc
        if not isinstance(result, dict) or result.get("status") != "ok":
            raise VectorStoreError("vector store returned an invalid response")
        return result

    @property
    def path(self) -> str:
        return "/collections/" + urllib.parse.quote(self.collection, safe="")

    def ensure_collection(self) -> None:
        try:
            result = self._request("GET", self.path)["result"]
        except VectorStoreError as exc:
            if str(exc) != "collection_not_found":
                raise
            self._request("PUT", self.path, {"vectors": {"size": self.dimension, "distance": "Cosine"}})
            result = self._request("GET", self.path)["result"]
        try:
            params = result["config"]["params"]["vectors"]
            size, distance = params["size"], params["distance"]
        except (KeyError, TypeError) as exc:
            raise VectorStoreError("vector collection has an invalid configuration") from exc
        if size != self.dimension or str(distance).lower() != "cosine":
            raise VectorStoreError("vector collection dimension or distance mismatch")

    def upsert(self, points: list[dict[str, Any]]) -> None:
        if points:
            self._request("PUT", self.path + "/points?wait=true", {"points": points})

    def delete(self, ids: list[int]) -> None:
        if ids:
            self._request("POST", self.path + "/points/delete?wait=true", {"points": ids})

    def query(self, vector: list[float], class_id: int, limit: int, min_score: float,
              index_version: str, material_ids: list[int] | None = None) -> list[tuple[int, float]]:
        must = [
            {"key": "class_id", "match": {"value": class_id}},
            {"key": "index_version", "match": {"any": index_version} if isinstance(index_version, list) else {"value": index_version}},
        ]
        if material_ids is not None:
            if not material_ids:
                return []
            must.append({'key': 'material_id', 'match': {'any': material_ids}})
        result = self._request("POST", self.path + "/points/query", {
            "query": vector,
            "filter": {"must": must},
            "limit": limit,
            "score_threshold": min_score,
            "with_payload": False,
        })
        try:
            points = result["result"]["points"]
            return [(int(point["id"]), float(point["score"])) for point in points]
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreError("vector query returned invalid points") from exc
