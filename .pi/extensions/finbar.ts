/**
 * Pi extension that bridges to the finbar MCP server via HTTP.
 *
 * Expects the MCP server to be already running (e.g. started with
 * ``FINBAR_TRANSPORT=http python run_mcp.py`` or ``start_mcp.bat``).
 * Discovers MCP tools and registers them as pi custom tools.
 *
 * Set FINBAR_DEBUG=true to enable verbose request/response logging.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "typebox";

// ── debug toggle ──────────────────────────────────────────

const DEBUG = process.env.FINBAR_DEBUG === "true";

function debugLog(...args: unknown[]): void {
  if (DEBUG) console.error(...args);
}

// ── MCP JSON-RPC types ──────────────────────────────────────────

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

interface McpToolDef {
  name: string;
  description?: string;
  inputSchema: {
    type: "object";
    properties?: Record<string, { type?: string; description?: string }>;
    required?: string[];
  };
}

type PendingRequest = {
  resolve: (res: JsonRpcResponse) => void;
  reject: (err: Error) => void;
  method: string;
  startedAt: number;
  timeoutMs: number;
  timer: ReturnType<typeof setTimeout>;
  abortHandler?: () => void;
  signal?: AbortSignal;
};

// ── MCP Client over HTTP ───────────────────────────────────────

class McpHttpClient {
  private requestId = 0;
  private pending = new Map<number, PendingRequest>();
  private connected = false;
  private baseUrl: string;
  private sessionId: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async start(): Promise<void> {
    const initResponse = await fetch(this.baseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 0,
        method: "initialize",
        params: {
          protocolVersion: "2024-11-05",
          capabilities: {},
          clientInfo: { name: "pi-finbar", version: "1.0.0" },
        },
      }),
    });

    if (!initResponse.ok) {
      throw new Error(
        `MCP initialize failed: HTTP ${initResponse.status} ${initResponse.statusText}`
      );
    }

    const sid = initResponse.headers.get("mcp-session-id");
    if (sid) {
      this.sessionId = sid;
      debugLog(`finbar: captured session ID ${sid.slice(0, 8)}…`);
    }

    await initResponse.text();

    await this.sendNotification("notifications/initialized", {});
    this.connected = true;
  }

  isConnected(): boolean {
    return this.connected;
  }

  async listTools(): Promise<McpToolDef[]> {
    const res = await this.request("tools/list", {});
    return (res.result as { tools: McpToolDef[] })?.tools ?? [];
  }

  async callTool(
    name: string,
    args: Record<string, unknown>,
    signal?: AbortSignal
  ): Promise<string> {
    const res = await this.request(
      "tools/call",
      { name, arguments: args },
      signal
    );
    const content = (
      res.result as { content?: Array<{ type: string; text?: string }> }
    )?.content;
    if (content && content.length > 0) {
      return content.map((c) => c.text ?? "").join("\n");
    }
    return JSON.stringify(res.result);
  }

  private request(
    method: string,
    params: Record<string, unknown>,
    signal?: AbortSignal
  ): Promise<JsonRpcResponse> {
    const id = ++this.requestId;
    const timeoutMs = this.timeoutFor(method);
    const startedAt = Date.now();

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup();
        const elapsed = Date.now() - startedAt;
        reject(
          new Error(
            `MCP request timeout after ${elapsed}ms (configured ${timeoutMs}ms): ${method}`
          )
        );
      }, timeoutMs);

      const abortHandler = () => {
        cleanup();
        const elapsed = Date.now() - startedAt;
        reject(
          new Error(`MCP request cancelled after ${elapsed}ms: ${method}`)
        );
      };

      const cleanup = () => {
        this.pending.delete(id);
        clearTimeout(timer);
        if (signal && abortHandler) {
          signal.removeEventListener("abort", abortHandler);
        }
      };

      if (signal?.aborted) {
        clearTimeout(timer);
        reject(new Error(`MCP request cancelled before send: ${method}`));
        return;
      }

      if (signal) {
        signal.addEventListener("abort", abortHandler, { once: true });
      }

      this.pending.set(id, {
        resolve: (res: JsonRpcResponse) => {
          cleanup();
          if (res.error) reject(new Error(res.error.message));
          else resolve(res);
        },
        reject,
        method,
        startedAt,
        timeoutMs,
        timer,
        abortHandler: signal ? abortHandler : undefined,
        signal,
      });

      debugLog(`finbar MCP ${method} started (timeout ${timeoutMs}ms)`);

      this.sendHttp(id, method, params)
        .then((response) => {
          const pending = this.pending.get(id);
          if (pending) {
            const elapsed = Date.now() - pending.startedAt;
            debugLog(
              `finbar MCP ${pending.method} completed in ${elapsed}ms`
            );
            pending.resolve(response);
          }
        })
        .catch((err) => {
          const pending = this.pending.get(id);
          if (pending) {
            pending.reject(err);
          }
        });
    });
  }

  private requestHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    };
    if (this.sessionId) {
      headers["mcp-session-id"] = this.sessionId;
    }
    return headers;
  }

  private async sendHttp(
    id: number,
    method: string,
    params: Record<string, unknown>
  ): Promise<JsonRpcResponse> {
    const body: JsonRpcRequest = {
      jsonrpc: "2.0",
      id,
      method,
      params,
    };

    const response = await fetch(this.baseUrl, {
      method: "POST",
      headers: this.requestHeaders(),
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(
        `MCP HTTP error ${response.status}: ${response.statusText}`
      );
    }

    const text = await response.text();
    const sseBody = this.parseStreamableHttp(text);
    if (!sseBody) {
      return { jsonrpc: "2.0", id, result: {} };
    }
    return JSON.parse(sseBody) as JsonRpcResponse;
  }

  private parseStreamableHttp(text: string): string | null {
    if (text.startsWith("{")) {
      return text;
    }
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data:")) {
        return line.slice(5).trim();
      }
    }
    return null;
  }

  private async sendNotification(
    method: string,
    params: Record<string, unknown>
  ): Promise<void> {
    const body = { jsonrpc: "2.0", method, params };
    const response = await fetch(this.baseUrl, {
      method: "POST",
      headers: this.requestHeaders(),
      body: JSON.stringify(body),
    });
    if (!response.ok && response.status !== 202) {
      debugLog(
        `finbar: notification ${method} got HTTP ${response.status}`
      );
    }
  }

  private timeoutFor(method: string): number {
    if (method === "tools/call") return 300000;
    if (method === "initialize" || method === "tools/list") return 30000;
    return 30000;
  }
}

// ── JSON schema → TypeBox helper ───────────────────────────────

function jsonSchemaToTypeBox(schema: McpToolDef["inputSchema"]) {
  const shape: Record<string, unknown> = {};
  const props = schema.properties ?? {};

  for (const [key, prop] of Object.entries(props)) {
    const desc = prop.description ?? key;
    const typ = prop.type ?? "string";

    if (typ === "string") {
      shape[key] = Type.Optional(Type.String({ description: desc }));
    } else if (typ === "integer" || typ === "number") {
      shape[key] = Type.Optional(Type.Number({ description: desc }));
    } else if (typ === "boolean") {
      shape[key] = Type.Optional(Type.Boolean({ description: desc }));
    } else {
      shape[key] = Type.Optional(Type.String({ description: desc }));
    }
  }

  return Type.Object(shape);
}

// ── Extension entry point ──────────────────────────────────────

export default async function (pi: ExtensionAPI) {
  const baseUrl =
    process.env.FINBAR_MCP_URL || "http://127.0.0.1:8003/mcp";
  const client = new McpHttpClient(baseUrl);

  pi.registerTool({
    name: "finbar_start",
    label: "Finbar: Start MCP server",
    description:
      "Instructions for starting the finbar MCP server. Call this FIRST if you need OHLCV stock data.",
    parameters: Type.Object({}),
    execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      return {
        content: [
          {
            type: "text" as const,
            text:
              "To start the finbar MCP server, open a terminal and run:\n\n" +
              "  cd C:\\Github-kan\\yfin\n" +
              "  start_mcp.bat\n\n" +
              "Or manually:\n" +
              "  .venv\\Scripts\\python.exe run_mcp.py\n" +
              "  (set FINBAR_TRANSPORT=http first for HTTP mode on port 8003)\n\n" +
              "Once started, the finbar tools will be discovered automatically.",
          },
        ],
        details: {},
      };
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    try {
      ctx.ui.notify(
        `finbar: Connecting to MCP server at ${baseUrl}...`,
        "info"
      );
      if (!client.isConnected()) {
        await client.start();
      }
      const tools = await client.listTools();
      ctx.ui.notify(
        `finbar: Connected, ${tools.length} tools discovered`,
        "success"
      );

      for (const tool of tools) {
        const paramsSchema = jsonSchemaToTypeBox(tool.inputSchema);

        pi.registerTool({
          name: `finbar_${tool.name}`,
          label: `Finbar: ${tool.name}`,
          description:
            tool.description ?? `finbar tool: ${tool.name}`,
          parameters: paramsSchema,
          async execute(_toolCallId, params, signal, _onUpdate, _ctx) {
            try {
              const result = await client.callTool(
                tool.name,
                params as Record<string, unknown>,
                signal
              );
              return {
                content: [{ type: "text" as const, text: result }],
                details: {},
              };
            } catch (err) {
              return {
                content: [
                  {
                    type: "text" as const,
                    text: `finbar error: ${
                      err instanceof Error ? err.message : String(err)
                    }`,
                  },
                ],
                details: {},
              };
            }
          },
        });

        ctx.ui.notify(
          `finbar: Registered tool '${tool.name}'`,
          "info"
        );
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      ctx.ui.notify(
        `finbar: ${msg}. Is the server running? Start it with:\n` +
          `  .venv\\Scripts\\python.exe run_mcp.py`,
        "error"
      );
    }
  });
}
