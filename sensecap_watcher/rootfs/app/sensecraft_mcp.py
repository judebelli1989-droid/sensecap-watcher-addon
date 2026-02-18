"""SenseCraft MCP Server — connects to SenseCraft Agent broker as MCP server.

SenseCraft Agent (DeepSeek LLM) calls our tools to control Home Assistant.
Protocol: MCP over WebSocket, reversed — broker is client, we are server.
"""

import asyncio
import json
import logging
import ssl
import websockets

from ha_tools import HA_TOOLS, HATools

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 10
PING_INTERVAL = 30


class SenseCraftMCP:
    """MCP server that exposes HA tools to SenseCraft Agent."""

    def __init__(self, mcp_url: str, ha_tools: HATools):
        self.mcp_url = mcp_url
        self.ha_tools = ha_tools
        self._ws = None
        self._running = False
        self._task = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._connection_loop())
        logger.info("SenseCraft MCP started")

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SenseCraft MCP stopped")

    async def _connection_loop(self):
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SenseCraft MCP error: {e}")
            if self._running:
                logger.info(f"Reconnecting in {RECONNECT_DELAY}s...")
                await asyncio.sleep(RECONNECT_DELAY)

    async def _connect(self):
        ssl_ctx = ssl.create_default_context()
        logger.info("Connecting to SenseCraft MCP broker...")

        async with websockets.connect(
            self.mcp_url,
            ssl=ssl_ctx,
            ping_interval=PING_INTERVAL,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            logger.info("Connected to SenseCraft MCP broker")
            await self._message_loop(ws)

    async def _message_loop(self, ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from broker: {raw[:200]}")
                continue

            method = msg.get("method")
            msg_id = msg.get("id")

            if method == "initialize":
                await self._handle_initialize(ws, msg_id, msg)
            elif method == "notifications/initialized":
                logger.info("SenseCraft MCP handshake complete")
            elif method == "tools/list":
                await self._handle_tools_list(ws, msg_id)
            elif method == "tools/call":
                await self._handle_tool_call(ws, msg_id, msg.get("params", {}))
            elif method == "ping":
                await self._send(ws, {"jsonrpc": "2.0", "id": msg_id, "result": {}})
            elif "result" in msg or "error" in msg:
                # Response to something we sent — ignore
                pass
            else:
                logger.debug(f"Unknown MCP method: {method}")

    async def _handle_initialize(self, ws, msg_id, msg):
        logger.info(
            f"MCP initialize from: {msg.get('params', {}).get('clientInfo', {})}"
        )
        await self._send(
            ws,
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "sensecap-ha-addon", "version": "1.0.0"},
                },
            },
        )

    async def _handle_tools_list(self, ws, msg_id):
        tools = []
        for t in HA_TOOLS:
            tools.append(
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["input_schema"],
                }
            )
        await self._send(
            ws,
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": tools},
            },
        )
        logger.info(f"Sent {len(tools)} HA tools to SenseCraft")

    async def _handle_tool_call(self, ws, msg_id, params):
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        logger.info(
            f"SenseCraft tool call: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:200]})"
        )

        try:
            result = await self.ha_tools.execute(tool_name, arguments)
            result_text = (
                json.dumps(result, ensure_ascii=False)
                if isinstance(result, (dict, list))
                else str(result)
            )
            await self._send(
                ws,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                },
            )
            logger.info(f"Tool {tool_name} result: {result_text[:200]}")
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            await self._send(
                ws,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    },
                },
            )

    async def _send(self, ws, msg):
        await ws.send(json.dumps(msg))
