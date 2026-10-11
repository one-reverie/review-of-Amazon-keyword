from pathlib import Path
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import threading
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from token_analyzer.llm import (
    parse_recommendation_content,
    recommend_candidates_with_llm,
    request_chat_completion,
)
from token_analyzer.recommendation import RecommendationCandidate, RecommendationCandidates
from token_analyzer.settings import ModelProfile


def candidate(text: str, kind: str, score: float) -> RecommendationCandidate:
    return RecommendationCandidate(
        text=text,
        kind=kind,
        frequency=10,
        impressions=1000,
        clicks=50,
        orders=5,
        ctr=0.05,
        cvr=0.10,
        smoothed_ctr=0.05,
        smoothed_cvr=0.10,
        score=score,
    )


class LlmParsingTests(unittest.TestCase):
    def test_recommendation_discards_hallucinated_terms(self) -> None:
        candidates = RecommendationCandidates(
            scope_query="white",
            mode="balanced",
            record_count=20,
            words=[candidate("sandals", "word", 90)],
            phrases=[candidate("arch support", "phrase", 85)],
        )
        result = parse_recommendation_content(
            candidates,
            json.dumps(
                {
                    "recommendations": [
                        {
                            "text": "sandals",
                            "kind": "word",
                            "category": "商品",
                            "reason": "订单稳定",
                            "risk": "",
                        },
                        {
                            "text": "made up",
                            "kind": "phrase",
                            "category": "其他",
                            "reason": "模型臆造",
                            "risk": "",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual([item.candidate.text for item in result.words], ["sandals"])
        self.assertEqual(result.phrases, [])

    def test_extra_instruction_is_sent_once_with_candidates(self) -> None:
        candidates = RecommendationCandidates(
            scope_query="",
            mode="traffic",
            record_count=20,
            words=[candidate("sandals", "word", 90)],
            phrases=[],
        )
        profile = ModelProfile("测试", "https://example.invalid/v1", "test-model", "")
        response = json.dumps(
            {
                "recommendations": [
                    {
                        "text": "sandals",
                        "kind": "word",
                        "category": "商品",
                        "reason": "符合要求",
                        "risk": "",
                    }
                ]
            },
            ensure_ascii=False,
        )
        with patch("token_analyzer.llm.request_chat_completion", return_value=response) as mocked:
            result = recommend_candidates_with_llm(
                candidates,
                profile,
                extra_instruction="排除品牌词",
            )

        messages = mocked.call_args.args[1]
        request_payload = json.loads(messages[1]["content"])
        self.assertEqual(request_payload["extra_instruction"], "排除品牌词")
        self.assertEqual(result.extra_instruction, "排除品牌词")

    def test_openai_compatible_request_against_local_server(self) -> None:
        received: dict[str, object] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                received["path"] = self.path
                received["authorization"] = self.headers.get("Authorization")
                received["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                response = {"choices": [{"message": {"content": "OK"}}]}
                payload = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            profile = ModelProfile(
                provider="测试服务商",
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                model="test-model",
                api_key="test-key-not-real",
            )
            content = request_chat_completion(
                profile,
                [{"role": "user", "content": "ping"}],
                timeout=5,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(content, "OK")
        self.assertEqual(received["path"], "/v1/chat/completions")
        self.assertEqual(received["authorization"], "Bearer test-key-not-real")
        self.assertEqual(received["body"]["model"], "test-model")

    def test_remote_http_rejects_api_key(self) -> None:
        profile = ModelProfile(
            provider="不安全接口",
            base_url="http://example.com/v1",
            model="test-model",
            api_key="test-key-not-real",
        )

        with self.assertRaisesRegex(ValueError, "必须使用https"):
            request_chat_completion(profile, [{"role": "user", "content": "ping"}])


if __name__ == "__main__":
    unittest.main()
