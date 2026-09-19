"""Tool-free HTTP adapters, extracted from the historical frozen424/stream runners.

No SDK retries/fallback, proxy environment or redirects. Captures are decoded HTTP
client body bytes, not wire bytes; normalized text is always a separate artifact.
"""
import asyncio
import os
from . import runs
from .contracts import decode, digest, encode, fields, require, HumanWillError

ENDPOINTS = {"openai": "https://api.openai.com/v1/responses",
             "anthropic": "https://api.anthropic.com/v1/messages",
             "openrouter": "https://openrouter.ai/api/v1/chat/completions"}
# Avoid storing arbitrary response headers (cookies, echoed authorization, etc.).
SAFE_HEADERS = {"content-type", "content-encoding", "content-length", "date", "request-id", "x-request-id",
                "x-generation-id", "retry-after", "anthropic-request-id"}
MAX_CAPTURE = 64 * 1024 * 1024


def request(spec, messages):
    provider, options = spec["provider"], spec.get("settings", {})
    if provider == "mock": return {"messages": messages}
    result = {"model": spec["model"], "stream": provider == "openrouter"}
    if provider == "openai":
        result.update(input=messages, max_output_tokens=spec["max_output_tokens"], store=False)
    else:
        result.update(messages=messages, max_tokens=spec["max_output_tokens"])
    if provider == "anthropic":
        result.update(system=messages[0]["content"], messages=messages[1:])
        if "thinking" in options: result["thinking"] = {"type": options["thinking"]}
        if "effort" in options: result["output_config"] = {"effort": options["effort"]}
    if provider == "openrouter":
        result["provider"] = {"only": [spec["route"]], "order": [spec["route"]],
                              "allow_fallbacks": False, "require_parameters": True}
    if "reasoning_effort" in options:
        result["reasoning"] = {"effort": options["reasoning_effort"]}
    if "temperature" in options: result["temperature"] = options["temperature"]
    return result


def reservation(spec, payload):
    if spec["provider"] == "mock": return 0
    count = len(encode(payload)) + 4096
    require(count <= spec["max_input_tokens"], "input_limit", "Request exceeds the configured conservative input bound.")
    return priced(spec, count, spec["max_output_tokens"])


def priced(spec, inputs, outputs):
    p = spec["prices"]
    # Integer micro-USD, rounded up. Rates must cover every context/route tier used.
    return (inputs * p["input_micro_usd_per_million"] + outputs * p["output_micro_usd_per_million"] + 999999) // 1000000


def usage_bound(spec, usage):
    if not isinstance(usage, dict): return None
    names = ("prompt_tokens", "completion_tokens") if spec["provider"] == "openrouter" else ("input_tokens", "output_tokens")
    i, o = (usage.get(k) for k in names)
    if type(i) is not int or type(o) is not int or min(i, o) < 0: return None
    if spec["provider"] == "anthropic":
        # No cache writes are requested. Unexpected writes retain the full hold.
        if usage.get("cache_creation_input_tokens", 0) != 0: return None
        cached = usage.get("cache_read_input_tokens", 0)
        if type(cached) is not int or cached < 0: return None
        i += cached
    else:
        details = usage.get("input_tokens_details", usage.get("prompt_tokens_details")) or {}
        if not isinstance(details, dict) or details.get("cache_write_tokens") or details.get("cache_creation_tokens"): return None
        cached = details.get("cached_tokens", 0)
        if type(cached) is not int or not 0 <= cached <= i: return None
    # Output already includes reasoning tokens. Cache discounts intentionally not claimed.
    return priced(spec, i, o)


def _sse(body):
    events, done = [], False
    # Only complete frames count. Keep all original bytes, including a torn last frame.
    text = body.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    for frame in text.split("\n\n")[:-1]:
        payload = "\n".join(line[5:].lstrip(" ") for line in frame.split("\n") if line.startswith("data:"))
        if not payload: continue
        if payload == "[DONE]": done = True; continue
        require(not done, message="Data after stream terminator.")
        event = decode(payload)
        require(isinstance(event, dict), message="Invalid stream event.")
        events.append(event)
    return events, done


def normalize(spec, status, body, complete):
    result = {"status": "error", "code": "unclassified_response", "answer": "", "complete": False,
              "signal": "unknown", "mechanism": None, "returned_model": None, "returned_provider": None, "usage": None, "usage_final": False}
    provider = spec["provider"]
    try:
        if status != 200:
            result["code"] = "http_error"
            data = decode(body)
            error = data.get("error") if isinstance(data, dict) else None
            if provider == "openai" and isinstance(error, dict) and status in (400, 403) and not data.get("output"):
                code = error.get("code")
                if code in ("cyber_policy", "content_filter"):
                    result.update(status="blocked", code=None, complete=complete, signal="provider_safety_block", mechanism=code)
            return result
        text, refusal, usage, finish = [], False, None, None
        if provider == "openrouter":
            events, done = _sse(body)
            models, providers, identities = set(), set(), set()
            had_error = False
            for item in events:
                if item.get("model"): models.add(item["model"])
                if item.get("provider"): providers.add(item["provider"])
                if item.get("id"): identities.add(item["id"])
                if item.get("error"): had_error = True
                if item.get("usage") is not None: usage = item["usage"]
                for choice in item.get("choices", []):
                    require(choice.get("index", 0) == 0, message="Multiple choices unsupported.")
                    delta = choice.get("delta", {})
                    require(not delta.get("tool_calls") and not delta.get("function_call"), message="Tool output unsupported.")
                    for key in ("content", "refusal"):
                        value = delta.get(key)
                        if value is not None:
                            require(isinstance(value, str), message="Invalid text delta.")
                            text.append(value)
                            refusal |= key == "refusal" and bool(value)
                    if choice.get("finish_reason") is not None: finish = choice["finish_reason"]
            require(len(models) == 1 and models <= set(spec["returned_models"]) and len(providers) == 1
                    and providers <= set(spec["returned_providers"]) and len(identities) == 1,
                    "identity_mismatch", "Returned model or route mismatch.")
            result.update(returned_model=next(iter(models)), returned_provider=next(iter(providers)))
            result["usage_final"] = complete and done and not had_error and finish in ("stop", "length", "content_filter")
            complete = complete and done and not had_error and finish in ("stop", "length", "content_filter")
            complete = complete and finish == "stop"
        else:
            data = decode(body)
            require(isinstance(data, dict), message="Expected provider object.")
            result["returned_model"] = data.get("model")
            require(data.get("model") in spec["returned_models"], "identity_mismatch", "Returned model mismatch.")
            usage = data.get("usage")
            result["usage_final"] = complete and not data.get("error")
            if provider == "openai":
                for item in data.get("output", []):
                    if item.get("type") == "reasoning": continue
                    require(item.get("type") == "message" and item.get("role") == "assistant", message="Unsupported output item.")
                    for part in item.get("content", []):
                        kind = part.get("type")
                        require(kind in ("output_text", "refusal"), message="Unsupported output part.")
                        value = part.get("text" if kind == "output_text" else "refusal")
                        require(isinstance(value, str), message="Invalid output text.")
                        text.append(value); refusal |= kind == "refusal"
                finish = (data.get("incomplete_details") or {}).get("reason")
                complete = complete and data.get("status") == "completed" and not data.get("error")
            else:
                require(data.get("type") == "message" and data.get("role") == "assistant", message="Unsupported message.")
                for part in data.get("content", []):
                    require(part.get("type") in ("text", "thinking", "redacted_thinking"), message="Unsupported content/fallback.")
                    if part["type"] == "text":
                        require(isinstance(part.get("text"), str), message="Invalid output text.")
                        text.append(part["text"])
                finish = data.get("stop_reason")
                refusal = finish == "refusal"
                complete = complete and finish in ("end_turn", "refusal")
        answer = "".join(text)
        result.update(answer=answer, usage=usage, complete=complete,
                      signal="structured_refusal" if refusal else "text_requires_review")
        if not complete: result["signal"] = "incomplete"
        if finish == "content_filter": result.update(signal="provider_safety_block", mechanism="content_filter")
        result.update(status="accepted" if complete and (answer.strip() or refusal) else ("partial" if answer.strip() else "error"),
                      code=None if complete and (answer.strip() or refusal) else ("incomplete_response" if answer.strip() else "empty_response"))
        return result
    except (HumanWillError, ValueError, TypeError, AttributeError, KeyError):
        # Malformed/mismatched identity never becomes a usable answer; raw evidence remains.
        result.update(code="invalid_provider_response", answer="", complete=False, signal="unknown", usage_final=False)
        return result


async def invoke(spec, payload, directory, secret, *, transport=None):
    try: import httpx
    except ImportError: raise HumanWillError("missing_dependency", "Install humanwill-evals[live] for HTTP providers.") from None
    headers = {"Content-Type": "application/json"}
    if spec["provider"] == "anthropic": headers.update({"x-api-key": secret, "anthropic-version": "2023-06-01"})
    else: headers["Authorization"] = "Bearer " + secret
    metadata = {"format": "humanwill.http/1", "body_file": "response.body", "complete": False,
                "status": None, "headers": [], "header_policy": "allowlist/1", "error": None,
                "representation": "httpx-content-decoded-body", "sha256": None, "bytes": 0}
    path = directory / "response.body"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    cancelled = False
    with os.fdopen(fd, "wb") as output:
        try:
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                         timeout=spec["timeout_seconds"]) as client:
                # Total deadline also bounds a server sending heartbeat chunks forever.
                async with asyncio.timeout(spec["timeout_seconds"]):
                    async with client.stream("POST", ENDPOINTS[spec["provider"]], headers=headers, content=encode(payload)) as response:
                        metadata.update(status=response.status_code, headers=[(k, v) for k, v in response.headers.multi_items() if k.lower() in SAFE_HEADERS])
                        async for chunk in response.aiter_bytes():
                            if metadata["bytes"] + len(chunk) > MAX_CAPTURE:
                                metadata["error"] = "capture_limit"; break
                            output.write(chunk); output.flush(); os.fsync(output.fileno())
                            metadata["bytes"] += len(chunk)
                        else: metadata["complete"] = True
        except asyncio.CancelledError:
            cancelled = True; metadata["error"] = "cancelled"
        except Exception:
            metadata["error"] = "transport_error"
        finally:
            output.flush(); os.fsync(output.fileno())
    body = path.read_bytes()
    metadata["sha256"] = digest(body)
    runs.write(directory / "http.json", metadata)
    if cancelled: raise asyncio.CancelledError
    return normalize(spec, metadata["status"], body, metadata["complete"]), metadata
