import { createHash, timingSafeEqual } from "node:crypto";
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { ACTIONS, evaluate, ORGANIZATIONS, submit } from "./fabric";

const port = Number(process.env.PORT ?? "3000");
const token = process.env.INTERNAL_GATEWAY_TOKEN ?? "";
const maximumBodyBytes = 65_536;

function json(response: ServerResponse, status: number, body: unknown): void {
  const content = JSON.stringify(body);
  response.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(content) });
  response.end(content);
}

function authorized(request: IncomingMessage): boolean {
  const header = request.headers.authorization ?? "";
  const expected = `Bearer ${token}`;
  const receivedDigest = createHash("sha256").update(header).digest();
  const expectedDigest = createHash("sha256").update(expected).digest();
  return token.length >= 32 && timingSafeEqual(receivedDigest, expectedDigest);
}

async function body(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > maximumBodyBytes) throw new Error("request body exceeds 64 KiB");
    chunks.push(bytes);
  }
  const parsed: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("request body must be an object");
  return parsed as Record<string, unknown>;
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", "http://gateway.local");
    if (request.method === "GET" && url.pathname === "/health") return json(response, 200, { status: "healthy" });
    if (request.method === "GET" && url.pathname === "/ready") {
      await evaluate("OperatorOrg", "GetLedgerInfo");
      return json(response, 200, { status: "ready" });
    }
    if (!authorized(request)) return json(response, 401, { detail: "Unauthorized" });

    if (request.method === "POST" && url.pathname === "/internal/ledger/submit") {
      const input = await body(request);
      const organization = String(input.organization ?? "");
      const action = String(input.action ?? "");
      const operationId = String(input.operationId ?? "");
      if (!(organization in ORGANIZATIONS) || !(action in ACTIONS) || !operationId || operationId.length > 128) {
        return json(response, 422, { detail: "Invalid ledger request" });
      }
      if (input.payload === null || Array.isArray(input.payload) || typeof input.payload !== "object") {
        return json(response, 422, { detail: "Invalid ledger payload" });
      }
      return json(response, 200, await submit(organization, action, operationId, input.payload as Record<string, unknown>));
    }

    const documentMatch = request.method === "GET" && url.pathname.match(/^\/internal\/ledger\/documents\/([a-fA-F0-9]{64})$/);
    if (documentMatch) return json(response, 200, await evaluate("AuditorOrg", "GetDocumentByHash", documentMatch[1].toLowerCase()));

    const telemetryMatch = request.method === "GET" && url.pathname.match(/^\/internal\/ledger\/telemetry\/([a-zA-Z0-9_-]+)$/);
    if (telemetryMatch) return json(response, 200, await evaluate("AuditorOrg", "GetTelemetryBatch", telemetryMatch[1]));

    return json(response, 404, { detail: "Not found" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    console.error(message);
    return json(response, 502, { detail: "Fabric operation failed" });
  }
});

server.listen(port, "0.0.0.0", () => console.log(`Fabric gateway listening on ${port}`));
