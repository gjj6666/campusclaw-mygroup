from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any


MAX_GATEWAY_BYTES = 20_000_000


class GatewayError(Exception):
    pass


class GatewayUnavailable(GatewayError):
    pass


class GatewayInvalidResponse(GatewayError):
    pass


class GatewayRequestTooLarge(GatewayError):
    pass


def _post_json(base_url: str, path: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_GATEWAY_BYTES:
        raise GatewayRequestTooLarge("gateway request exceeds 20MB")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/{path}",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            decoded = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GatewayUnavailable("model gateway unavailable") from exc
    except (ValueError, UnicodeError) as exc:
        raise GatewayInvalidResponse("model gateway returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise GatewayInvalidResponse("model gateway returned invalid JSON object")
    return decoded


class EmbeddingClient:
    def __init__(self, base_url: str, api_key: str, model: str, dimension: int):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        result = _post_json(
            self.base_url, "embeddings", self.api_key, {"model": self.model, "input": text}
        )
        try:
            vector = result["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GatewayInvalidResponse("embedding response missing vector") from exc
        if not isinstance(vector, list) or len(vector) != self.dimension:
            raise GatewayInvalidResponse("embedding dimension mismatch")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
            raise GatewayInvalidResponse("embedding contains invalid values")
        return [float(value) for value in vector]


class ChatClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def complete(self, messages: list[dict[str, str]]) -> str:
        result = _post_json(
            self.base_url, "chat/completions", self.api_key,
            {"model": self.model, "messages": messages},
        )
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GatewayInvalidResponse("chat response missing content") from exc
        if not isinstance(content, str) or not content.strip():
            raise GatewayInvalidResponse("chat response has empty content")
        return content.strip()

    def stream(self, messages: list[dict[str, str]]):
        body = json.dumps({'model': self.model, 'messages': messages, 'stream': True}, ensure_ascii=False).encode('utf-8')
        if len(body) > MAX_GATEWAY_BYTES:
            raise GatewayRequestTooLarge('gateway request exceeds 20MB')
        request = urllib.request.Request(self.base_url.rstrip('/') + '/chat/completions', data=body,
                                         headers={'Authorization': f'Bearer {self.api_key}',
                                                  'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data, total, received, finished = [], 0, False, False
                for raw in response:
                    total += len(raw)
                    if total > MAX_GATEWAY_BYTES:
                        raise GatewayInvalidResponse('stream response too large')
                    line = raw.decode('utf-8').rstrip('\r\n')
                    if line.startswith('data:'):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        value = '\n'.join(data)
                        data.clear()
                        if value == '[DONE]':
                            if not received or not finished:
                                raise GatewayInvalidResponse('stream missing text or finish reason')
                            return
                        frame = json.loads(value)
                        if 'error' in frame:
                            raise GatewayInvalidResponse('model stream error')
                        choices = frame.get('choices')
                        if choices == []:  # Optional usage frame.
                            continue
                        if not isinstance(choices, list) or not choices:
                            raise GatewayInvalidResponse('invalid stream choices')
                        choice = choices[0]
                        reason = choice.get('finish_reason')
                        if reason is not None:
                            if reason != 'stop':
                                raise GatewayInvalidResponse('model response was not completed')
                            finished = True
                        delta = choice.get('delta')
                        if not isinstance(delta, dict):
                            raise GatewayInvalidResponse('missing stream delta')
                        content = delta.get('content')
                        if content is not None and not isinstance(content, str):
                            raise GatewayInvalidResponse('invalid stream content')
                        if content:
                            received = True
                            yield content
                raise GatewayInvalidResponse('stream ended before DONE')
        except GatewayError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GatewayUnavailable('model gateway unavailable') from exc
        except (ValueError, UnicodeError, KeyError, TypeError, IndexError) as exc:
            raise GatewayInvalidResponse('invalid model stream') from exc
