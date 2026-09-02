#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = "https://mapstools.googleapis.com/mcp"
OUT = Path("out/maps-grounding-probe")
QUERIES = [
    "Gibbins Law PLLC Tyler Texas",
    "Hager Law PLLC Texas",
    "Tate Accident Law Sherman Texas",
]


def dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return str(value)


async def main() -> None:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_API_KEY missing")
    OUT.mkdir(parents=True, exist_ok=True)

    http = httpx2.AsyncClient(
        headers={
            "X-Goog-Api-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        follow_redirects=True,
        timeout=httpx2.Timeout(30.0, read=180.0),
    )

    report = {"mcp_url": MCP_URL, "tools": [], "queries": []}
    try:
        async with http:
            async with streamable_http_client(MCP_URL, http_client=http, terminate_on_close=False) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    init = await session.initialize()
                    report["initialize"] = dump(init)
                    tools = await session.list_tools()
                    report["tools"] = [dump(t) for t in tools.tools]
                    search_tool = next((t for t in tools.tools if t.name == "search_places"), None)
                    if search_tool is None:
                        raise RuntimeError("search_places tool not exposed")

                    schema = getattr(search_tool, "inputSchema", None) or getattr(search_tool, "input_schema", None) or {}
                    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
                    required = schema.get("required", []) if isinstance(schema, dict) else []
                    # Official docs/examples refer to text_query. Fall back to first required string field.
                    query_key = "text_query" if "text_query" in props else None
                    if not query_key:
                        for key_name in required:
                            spec = props.get(key_name, {})
                            if spec.get("type") == "string":
                                query_key = key_name
                                break
                    if not query_key:
                        query_key = "text_query"

                    for text in QUERIES:
                        args = {query_key: text}
                        try:
                            result = await session.call_tool("search_places", arguments=args)
                            report["queries"].append({"query": text, "arguments": args, "result": dump(result)})
                        except Exception as exc:
                            report["queries"].append({"query": text, "arguments": args, "error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"

    (OUT / "grounding_probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    text = json.dumps(report, ensure_ascii=False).lower()
    report["contains_http_url_outside_google_maps"] = "http" in text and any(term in text for term in ["website", "official site", "homepage"])
    print(json.dumps(report, ensure_ascii=False, indent=2)[:30000])


if __name__ == "__main__":
    asyncio.run(main())
