import io
import json
import unittest
from unittest.mock import patch

from campusclaw.gateway import (
    ChatClient,
    EmbeddingClient,
    GatewayInvalidResponse,
    GatewayRequestTooLarge,
    GatewayUnavailable,
)


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class GatewayTests(unittest.TestCase):
    def test_real_stream_contract_and_failures(self):
        frames = [ {'choices': [{'delta': {'content': value}, 'finish_reason': None}]} for value in ('中文', '新增') ]
        frames.append({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
        wire = ''.join('data: ' + json.dumps(f, ensure_ascii=False) + '\r\n\r\n' for f in frames) + 'data: [DONE]\r\n\r\n'
        seen = []
        def transport(request, timeout):
            seen.append(request)
            return io.BytesIO(wire.encode())
        client = ChatClient('http://example/v1', 'test', 'course-chat')
        with patch('campusclaw.gateway.urllib.request.urlopen', side_effect=transport):
            self.assertEqual(list(client.stream([{'role': 'user', 'content': '问题'}])), ['中文', '新增'])
        self.assertIs(json.loads(seen[0].data)['stream'], True)
        for bad in ('data: not-json\n\n', wire.replace('data: [DONE]\r\n\r\n', ''),
                    wire.replace('"stop"', '"length"'), 'data: {"choices": [{}]}\n\n'):
            with patch('campusclaw.gateway.urllib.request.urlopen', return_value=io.BytesIO(bad.encode())):
                with self.assertRaises(GatewayInvalidResponse):
                    list(client.stream([]))
        with patch('campusclaw.gateway.MAX_GATEWAY_BYTES', 10), patch('campusclaw.gateway.urllib.request.urlopen') as network:
            with self.assertRaises(GatewayRequestTooLarge):
                list(client.stream([{'role': 'user', 'content': 'x' * 20}]))
            network.assert_not_called()
        with patch('campusclaw.gateway.urllib.request.urlopen', side_effect=TimeoutError):
            with self.assertRaises(GatewayUnavailable):
                list(client.stream([]))

    def test_embedding_request_contains_only_model_and_input(self):
        seen = []

        def fake_open(request, timeout):
            seen.append((request, timeout))
            return response({"data": [{"embedding": [0.5] * 2048}]})

        with patch("campusclaw.gateway.urllib.request.urlopen", side_effect=fake_open):
            vector = EmbeddingClient("https://example.test/v1", "private-key", "course-embedding", 2048).embed("本班讲义")
        request, timeout = seen[0]
        self.assertEqual(request.full_url, "https://example.test/v1/embeddings")
        self.assertEqual(json.loads(request.data), {"model": "course-embedding", "input": "本班讲义"})
        self.assertEqual(request.get_header("Authorization"), "Bearer private-key")
        self.assertEqual(len(vector), 2048)
        self.assertGreater(timeout, 0)

    def test_embedding_bad_dimension_is_rejected(self):
        with patch("campusclaw.gateway.urllib.request.urlopen", return_value=response({"data": [{"embedding": [1.0]}]})):
            with self.assertRaises(GatewayInvalidResponse):
                EmbeddingClient("https://example.test/v1", "private-key", "course-embedding", 2048).embed("文本")

    def test_chat_request_and_failure_are_sanitized(self):
        seen = []

        def fake_open(request, timeout):
            seen.append(request)
            return response({"choices": [{"message": {"content": "答案 [S1]"}}]})

        with patch("campusclaw.gateway.urllib.request.urlopen", side_effect=fake_open):
            answer = ChatClient("https://example.test/v1", "private-key", "course-chat").complete(
                [{"role": "user", "content": "问题"}]
            )
        self.assertEqual(answer, "答案 [S1]")
        self.assertEqual(seen[0].full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(json.loads(seen[0].data)["model"], "course-chat")
        with patch("campusclaw.gateway.urllib.request.urlopen", side_effect=TimeoutError("private-key")):
            with self.assertRaises(GatewayUnavailable) as ctx:
                ChatClient("https://example.test/v1", "private-key", "course-chat").complete([])
        self.assertNotIn("private-key", str(ctx.exception))

    def test_request_size_is_checked_before_network(self):
        with patch("campusclaw.gateway.MAX_GATEWAY_BYTES", 10):
            with patch("campusclaw.gateway.urllib.request.urlopen") as open_mock:
                with self.assertRaises(GatewayRequestTooLarge):
                    ChatClient("https://example.test/v1", "private-key", "course-chat").complete(
                        [{"role": "user", "content": "too large"}]
                    )
                open_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
