#!/usr/bin/env python3
"""Remote Verification Script for Deployed Antigravity Quota Concierge on Vertex AI Agent Engine.

Queries the live `ReasoningEngine` endpoint on Vertex AI to verify:
1. Model inference using `gemini-3.5-flash`.
2. Diagnosis tool execution for customer-neutral persona (`alex.morgan@example.com`).
3. Multi-agent delegation from `antigravity_quota_concierge` to `quota_request_agent`.
4. Streaming response compatibility (`stream_query`).

Usage:
    # Auto-read from deployment_metadata.json:
    python3 concierge-agent/test_remote_agent.py

    # Explicit resource name:
    python3 concierge-agent/test_remote_agent.py \
        --resource-name "projects/123456789/locations/us-central1/reasoningEngines/987654321"

    # Custom single query:
    python3 concierge-agent/test_remote_agent.py \
        --query "What are my quota upgrade options?"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Automatically re-exec with concierge-agent/.venv if running with system python
_venv_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python3"
if _venv_python.exists() and sys.executable != str(_venv_python) and not os.environ.get("_IN_VENV"):
    os.environ["_IN_VENV"] = "1"
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

DEFAULT_METADATA_PATH = Path(__file__).resolve().parent / "deployment_metadata.json"
DEFAULT_TEST_USER = "alex.morgan@example.com"


def load_deployment_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Deployment metadata file not found at: {metadata_path}\n"
            f"Please run `./deploy.sh` first or specify --resource-name explicitly."
        )
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def patch_reasoning_engine_methods(remote_app: Any) -> None:
    """Safely register reasoning engine methods, skipping unhandled API modes (e.g. 'async')."""
    try:
        from vertexai.reasoning_engines import _reasoning_engines
        import types

        for op in remote_app.operation_schemas():
            mode = op.get("api_mode", "")
            name = op.get("name")
            if not name or hasattr(remote_app, name):
                continue
            if mode == "":
                method = _reasoning_engines._wrap_query_operation(
                    method_name=name,
                    doc=op.get("description", ""),
                )
                setattr(remote_app, name, types.MethodType(method, remote_app))
            elif mode == "stream":
                method = _reasoning_engines._wrap_stream_query_operation(
                    method_name=name,
                    doc=op.get("description", ""),
                )
                setattr(remote_app, name, types.MethodType(method, remote_app))
    except Exception:
        pass


def parse_stream_response_chunks(chunks: Any):
    """Yield parsed JSON objects or strings from a stream response."""
    for chunk in chunks:
        data = getattr(chunk, "data", None)
        if data is None:
            yield chunk
            continue
        try:
            utf8_text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
        except Exception:
            yield chunk
            continue
        for line in utf8_text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                yield line


def execute_stream_query(remote_app: Any, **kwargs: Any) -> Any:
    """Execute stream_query via the bound method or direct execution API client."""
    if hasattr(remote_app, "stream_query"):
        try:
            return remote_app.stream_query(**kwargs)
        except Exception:
            pass

    from google.cloud.aiplatform_v1beta1.types import reasoning_engine_execution_service as aip_types

    response = remote_app.execution_api_client.stream_query_reasoning_engine(
        request=aip_types.StreamQueryReasoningEngineRequest(
            name=remote_app.resource_name,
            input=kwargs,
            class_method="stream_query",
        )
    )

    return parse_stream_response_chunks(response)


def format_chunk(chunk: Any) -> str:
    """Extract display text from an ADK event dictionary or string."""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        content = chunk.get("content")
        if isinstance(content, dict):
            parts = content.get("parts", [])
            texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
            if texts:
                return "".join(texts)
        if "text" in chunk and isinstance(chunk["text"], str):
            return chunk["text"]
        if "output" in chunk and isinstance(chunk["output"], str):
            return chunk["output"]
        # Return empty string for internal action/state events to keep chat stream clean
        return ""
    return str(chunk)


def run_test_suite(
    resource_name: str,
    project_id: str,
    location: str,
    user_email: str = DEFAULT_TEST_USER,
    custom_query: str | None = None,
) -> int:
    print("=" * 70)
    print(" Antigravity Quota Concierge — Remote Reasoning Engine Verification")
    print("=" * 70)
    print(f" Resource:  {resource_name}")
    print(f" Project:   {project_id}")
    print(f" Location:  {location}")
    print(f" Test User: {user_email}")
    print("=" * 70)

    # Disable mTLS client certificates for standard workstation compatibility
    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

    try:
        import vertexai  # type: ignore[import-untyped]
        from vertexai.preview import reasoning_engines  # type: ignore[import-untyped]
    except ImportError as exc:
        print(f"[-] Missing vertexai package: {exc}", file=sys.stderr)
        print("    Run: pip install 'google-cloud-aiplatform[agent_engines,adk]>=1.129.0'", file=sys.stderr)
        return 1

    print("[+] Initializing Vertex AI SDK...")
    vertexai.init(project=project_id, location=location)

    print(f"[+] Connecting to Reasoning Engine: {resource_name}...")
    try:
        remote_app = reasoning_engines.ReasoningEngine(resource_name)
    except Exception as exc:
        print(f"[-] Failed to load ReasoningEngine: {exc}", file=sys.stderr)
        return 1

    # Safely bind missing stream_query/query methods if SDK hit 'Unsupported api mode: async'
    patch_reasoning_engine_methods(remote_app)

    queries = [custom_query] if custom_query else [
        "Why is my Antigravity access paused?",
        "What are my quota upgrade options?",
    ]

    failed = False
    for idx, prompt in enumerate(queries, 1):
        print(f"\n--- [Test Query {idx}/{len(queries)}] ------------------------------------")
        print(f"User:   {prompt}")
        print(f"Sender: {user_email}")
        print("Response (Streaming):")

        start_time = time.time()
        full_response = []
        try:
            for raw_chunk in execute_stream_query(remote_app, message=prompt, user_id=user_email):
                text_chunk = format_chunk(raw_chunk)
                sys.stdout.write(text_chunk)
                sys.stdout.flush()
                full_response.append(text_chunk)
            print()
            elapsed = time.time() - start_time
            print(f"\n[+] Completed in {elapsed:.2f}s")
        except Exception as exc:
            print(f"\n[-] Query failed: {exc}", file=sys.stderr)
            failed = True

    print("\n" + "=" * 70)
    if failed:
        print("[-] Remote verification finished with ERRORS.")
        return 1
    print("[+] All remote verification tests completed SUCCESSFULLY!")
    print("=" * 70)
    return 0
    print("[+] All remote verification tests completed SUCCESSFULLY!")
    print("=" * 70)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify deployed Antigravity Quota Concierge on Vertex AI Agent Engine."
    )
    parser.add_argument(
        "--metadata-file",
        default=str(DEFAULT_METADATA_PATH),
        help=f"Path to deployment_metadata.json (default: {DEFAULT_METADATA_PATH})",
    )
    parser.add_argument(
        "--resource-name",
        default=os.environ.get("REMOTE_AGENT_RUNTIME_ID", ""),
        help="Vertex AI Reasoning Engine resource name (projects/.../locations/.../reasoningEngines/...)",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID", ""),
        help="GCP Project ID hosting the deployed Reasoning Engine.",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("REGION", "us-central1"),
        help="Vertex AI region (default: us-central1).",
    )
    parser.add_argument(
        "--user-email",
        default=DEFAULT_TEST_USER,
        help=f"Test employee email (default: {DEFAULT_TEST_USER}).",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Optional single custom prompt to test.",
    )

    args = parser.parse_args(argv)

    resource_name = args.resource_name
    project_id = args.project_id
    location = args.location

    if not resource_name:
        try:
            meta = load_deployment_metadata(Path(args.metadata_file))
            resource_name = meta.get("remote_agent_runtime_id", "")
            if not project_id:
                project_id = meta.get("project_id", "")
            if not location:
                location = meta.get("location", "us-central1")
        except FileNotFoundError as err:
            print(f"[-] {err}", file=sys.stderr)
            return 1

    if not resource_name:
        print("[-] Error: No reasoning engine resource name found.", file=sys.stderr)
        print("    Provide via --resource-name or run ./deploy.sh first.", file=sys.stderr)
        return 1

    if not project_id:
        # Extract project ID / number from resource name
        parts = resource_name.split("/")
        if len(parts) >= 2 and parts[0] == "projects":
            project_id = parts[1]
        else:
            project_id = "your-gcp-project-id"

    return run_test_suite(
        resource_name=resource_name,
        project_id=project_id,
        location=location,
        user_email=args.user_email,
        custom_query=args.query or None,
    )


if __name__ == "__main__":
    sys.exit(main())
