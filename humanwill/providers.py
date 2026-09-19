"""Explicit simulation. No HTTP, credentials, SDKs or semantic refusal judge."""
import asyncio
from dataclasses import dataclass
from typing import Protocol

from .contracts import text_digest


@dataclass(frozen=True)
class Request:
    case_id: str
    stage: str
    model: str
    payload: dict
    fail: bool = False
    abstain_fr: bool = False


class Provider(Protocol):
    async def invoke(self, request: Request) -> dict: ...


class MockProvider:
    async def invoke(self, request: Request) -> dict:
        await asyncio.sleep(0)  # Exercise the same async orchestration as future adapters.
        if request.fail:
            return {"status": "error", "code": "simulated_provider_error"}
        if request.stage == "candidate":
            refusing = request.model == "refuse"
            return {"status": "accepted", "answer": "Simulated refusal." if refusing else
                    request.payload["messages"][1]["content"],
                    "mock_behavior": "refusal" if refusing else "answer"}
        # The fixture signal is explicit, never inferred by phrase matching.
        refusing = request.payload["mock_behavior"] == "refusal"
        return {"status": "accepted", "false_refusal": None if request.abstain_fr else (2 if refusing else 0),
                "usefulness": 0 if refusing else (4 if request.payload["answer"] ==
                    request.payload["messages"][1]["content"] else 0),
                "answer_sha256": text_digest(request.payload["answer"]),
                "policy": "mock-exact/1", "simulated": True}
