import { Context, Contract, Info, Returns, Transaction } from "fabric-contract-api";
import { createHash } from "node:crypto";
import {
  JsonRecord,
  optionalString,
  parsePayload,
  requireInteger,
  requireSha256,
  requireString,
} from "./validation";

const ORGANIZATIONS: Record<string, string> = {
  Org1MSP: "OperatorOrg",
  Org2MSP: "ContractorOrg",
  Org3MSP: "AuditorOrg",
};

@Info({ title: "FieldLedgerContract", description: "Asset integrity ledger" })
export class FieldLedgerContract extends Contract {
  private organization(ctx: Context, allowed?: string[]): string {
    const msp = ctx.clientIdentity.getMSPID();
    const organization = ORGANIZATIONS[msp];
    if (!organization || (allowed && !allowed.includes(msp))) {
      throw new Error(`organization ${msp} is not authorized`);
    }
    return organization;
  }

  private timestamp(ctx: Context): string {
    const timestamp = ctx.stub.getTxTimestamp();
    return new Date(Number(timestamp.seconds) * 1000 + Math.floor(timestamp.nanos / 1e6)).toISOString();
  }

  private async get(ctx: Context, key: string): Promise<JsonRecord | null> {
    const value = await ctx.stub.getState(key);
    return value.length ? (JSON.parse(Buffer.from(value).toString("utf8")) as JsonRecord) : null;
  }

  private async put(ctx: Context, key: string, value: JsonRecord): Promise<void> {
    await ctx.stub.putState(key, Buffer.from(JSON.stringify(value)));
  }

  private key(ctx: Context, type: string, id: string): string {
    return ctx.stub.createCompositeKey(type, [id]);
  }

  private async idempotent(
    ctx: Context,
    operationId: string,
    payloadJson: string,
    apply: () => Promise<JsonRecord>,
  ): Promise<string> {
    const operationKey = this.key(ctx, "operation", requireString(operationId, "operationId", 128));
    const digest = createHash("sha256").update(payloadJson).digest("hex");
    const existing = await this.get(ctx, operationKey);
    if (existing) {
      if (existing.payloadDigest !== digest) throw new Error("operationId was reused with another payload");
      return JSON.stringify(existing.result);
    }
    const result = await apply();
    await this.put(ctx, operationKey, { payloadDigest: digest, result });
    return JSON.stringify(result);
  }

  @Transaction()
  @Returns("string")
  public async CreateAsset(ctx: Context, operationId: string, payloadJson: string): Promise<string> {
    const organization = this.organization(ctx, ["Org1MSP"]);
    return this.idempotent(ctx, operationId, payloadJson, async () => {
      const payload = parsePayload(payloadJson);
      const assetId = requireString(payload.assetId, "assetId", 64);
      const key = this.key(ctx, "asset", assetId);
      if (await this.get(ctx, key)) throw new Error(`asset ${assetId} already exists`);
      const record: JsonRecord = {
        recordType: "ASSET",
        assetId,
        assetType: requireString(payload.assetType, "assetType", 64),
        name: requireString(payload.name, "name", 160),
        site: requireString(payload.site, "site", 160),
        serialNumber: optionalString(payload.serialNumber, "serialNumber", 128),
        organization,
        createdAt: this.timestamp(ctx),
        ledgerTxId: ctx.stub.getTxID(),
      };
      await this.put(ctx, key, record);
      return record;
    });
  }

  @Transaction()
  @Returns("string")
  public async ProposeEvent(ctx: Context, operationId: string, payloadJson: string): Promise<string> {
    const organization = this.organization(ctx, ["Org2MSP"]);
    return this.idempotent(ctx, operationId, payloadJson, async () => {
      const payload = parsePayload(payloadJson);
      const eventId = requireString(payload.eventId, "eventId", 64);
      const assetId = requireString(payload.assetId, "assetId", 64);
      if (!(await this.get(ctx, this.key(ctx, "asset", assetId)))) throw new Error(`asset ${assetId} does not exist`);
      const key = this.key(ctx, "event", eventId);
      if (await this.get(ctx, key)) throw new Error(`event ${eventId} already exists`);
      const record: JsonRecord = {
        recordType: "EVENT",
        eventId,
        assetId,
        eventType: requireString(payload.eventType, "eventType", 64),
        description: requireString(payload.description, "description", 4000),
        performedBy: requireString(payload.performedBy, "performedBy", 64),
        performedAt: requireString(payload.performedAt, "performedAt", 64),
        organization,
        status: "PROPOSED",
        documentHash: null,
        proposedAt: this.timestamp(ctx),
        ledgerTxId: ctx.stub.getTxID(),
      };
      await this.put(ctx, key, record);
      return record;
    });
  }

  @Transaction()
  @Returns("string")
  public async ReviewEvent(ctx: Context, operationId: string, payloadJson: string): Promise<string> {
    const organization = this.organization(ctx, ["Org1MSP"]);
    return this.idempotent(ctx, operationId, payloadJson, async () => {
      const payload = parsePayload(payloadJson);
      const eventId = requireString(payload.eventId, "eventId", 64);
      const key = this.key(ctx, "event", eventId);
      const event = await this.get(ctx, key);
      if (!event) throw new Error(`event ${eventId} does not exist`);
      if (event.status !== "PROPOSED") throw new Error(`event ${eventId} was already reviewed`);
      if (event.organization === organization) throw new Error("proposer organization cannot review its event");
      const decision = requireString(payload.decision, "decision", 16);
      if (!["APPROVED", "REJECTED"].includes(decision)) throw new Error("decision must be APPROVED or REJECTED");
      const reason = optionalString(payload.reason, "reason", 2000);
      if (decision === "REJECTED" && reason === null) throw new Error("rejection reason is required");
      const updated: JsonRecord = {
        ...event,
        status: decision,
        reviewedBy: requireString(payload.reviewedBy, "reviewedBy", 64),
        reviewedByOrganization: organization,
        reviewedAt: this.timestamp(ctx),
        rejectionReason: decision === "REJECTED" ? reason : null,
        reviewLedgerTxId: ctx.stub.getTxID(),
      };
      await this.put(ctx, key, updated);
      return updated;
    });
  }

  @Transaction()
  @Returns("string")
  public async RegisterDocument(ctx: Context, operationId: string, payloadJson: string): Promise<string> {
    const organization = this.organization(ctx);
    return this.idempotent(ctx, operationId, payloadJson, async () => {
      const payload = parsePayload(payloadJson);
      const hash = requireSha256(payload.sha256Hash);
      const eventId = requireString(payload.eventId, "eventId", 64);
      const assetId = requireString(payload.assetId, "assetId", 64);
      const eventKey = this.key(ctx, "event", eventId);
      const event = await this.get(ctx, eventKey);
      if (!event || event.assetId !== assetId) throw new Error("document event/asset relationship is invalid");
      const hashKey = this.key(ctx, "documentHash", hash);
      if (await this.get(ctx, hashKey)) throw new Error("document hash is already registered");
      const record: JsonRecord = {
        recordType: "DOCUMENT_HASH",
        documentId: requireString(payload.documentId, "documentId", 64),
        eventId,
        assetId,
        category: optionalString(payload.category, "category", 64) ?? "OTHER",
        sha256Hash: hash,
        contentType: requireString(payload.contentType, "contentType", 100),
        sizeBytes: requireInteger(payload.sizeBytes, "sizeBytes"),
        uploadedBy: requireString(payload.uploadedBy, "uploadedBy", 64),
        organization,
        registeredAt: this.timestamp(ctx),
        ledgerTxId: ctx.stub.getTxID(),
      };
      await this.put(ctx, hashKey, record);
      await ctx.stub.putState(this.key(ctx, "document", String(record.documentId)), Buffer.from(JSON.stringify(record)));
      event.documentHash = hash;
      await this.put(ctx, eventKey, event);
      return record;
    });
  }

  @Transaction()
  @Returns("string")
  public async DecommissionAsset(ctx: Context, operationId: string, payloadJson: string): Promise<string> {
    const organization = this.organization(ctx, ["Org1MSP"]);
    return this.idempotent(ctx, operationId, payloadJson, async () => {
      const payload = parsePayload(payloadJson);
      const assetId = requireString(payload.assetId, "assetId", 64);
      const reason = requireString(payload.reason, "reason", 2000);
      const key = this.key(ctx, "asset", assetId);
      const asset = await this.get(ctx, key);
      if (!asset) throw new Error(`asset ${assetId} does not exist`);
      if (asset.status === "DECOMMISSIONED") throw new Error(`asset ${assetId} is already decommissioned`);

      const updated: JsonRecord = {
        ...asset,
        status: "DECOMMISSIONED",
        decommissionReason: reason,
        decommissionedBy: requireString(payload.decommissionedBy, "decommissionedBy", 64),
        decommissionedAt: this.timestamp(ctx),
        decommissionLedgerTxId: ctx.stub.getTxID(),
      };
      await this.put(ctx, key, updated);
      return updated;
    });
  }

  @Transaction()
  @Returns("string")
  public async RegisterTelemetryBatch(ctx: Context, operationId: string, payloadJson: string): Promise<string> {
    const organization = this.organization(ctx, ["Org1MSP"]);
    return this.idempotent(ctx, operationId, payloadJson, async () => {
      const payload = parsePayload(payloadJson);
      const batchId = requireString(payload.batchId, "batchId", 64);
      const assetId = requireString(payload.assetId, "assetId", 64);
      const merkleRoot = requireSha256(payload.merkleRoot, "merkleRoot");
      const readingCount = requireInteger(payload.readingCount, "readingCount");
      const periodStart = requireString(payload.periodStart, "periodStart", 64);
      const periodEnd = requireString(payload.periodEnd, "periodEnd", 64);

      if (!(await this.get(ctx, this.key(ctx, "asset", assetId)))) {
        throw new Error(`asset ${assetId} does not exist`);
      }

      const batchKey = this.key(ctx, "telemetryBatch", batchId);
      if (await this.get(ctx, batchKey)) throw new Error(`batch ${batchId} already exists`);

      const record: JsonRecord = {
        recordType: "TELEMETRY_BATCH",
        batchId,
        assetId,
        merkleRoot,
        readingCount,
        periodStart,
        periodEnd,
        organization,
        registeredAt: this.timestamp(ctx),
        ledgerTxId: ctx.stub.getTxID(),
      };

      await this.put(ctx, batchKey, record);
      await this.put(ctx, this.key(ctx, "telemetryMerkle", merkleRoot), record);
      return record;
    });
  }

  @Transaction(false)
  @Returns("string")
  public async GetAsset(ctx: Context, assetId: string): Promise<string> {
    this.organization(ctx);
    const record = await this.get(ctx, this.key(ctx, "asset", requireString(assetId, "assetId", 64)));
    if (!record) throw new Error(`asset ${assetId} does not exist`);
    return JSON.stringify(record);
  }

  @Transaction(false)
  @Returns("string")
  public async GetEvent(ctx: Context, eventId: string): Promise<string> {
    this.organization(ctx);
    const record = await this.get(ctx, this.key(ctx, "event", requireString(eventId, "eventId", 64)));
    if (!record) throw new Error(`event ${eventId} does not exist`);
    return JSON.stringify(record);
  }

  @Transaction(false)
  @Returns("string")
  public async GetDocumentByHash(ctx: Context, sha256Hash: string): Promise<string> {
    this.organization(ctx);
    const hash = requireSha256(sha256Hash);
    const record = await this.get(ctx, this.key(ctx, "documentHash", hash));
    return JSON.stringify(record ? { found: true, document: record } : { found: false, sha256Hash: hash });
  }

  @Transaction(false)
  @Returns("string")
  public async GetTelemetryBatch(ctx: Context, batchId: string): Promise<string> {
    this.organization(ctx);
    const record = await this.get(ctx, this.key(ctx, "telemetryBatch", requireString(batchId, "batchId", 64)));
    return JSON.stringify(record ? { found: true, batch: record } : { found: false, batchId });
  }

  private async history(ctx: Context, key: string): Promise<JsonRecord[]> {
    const entries: JsonRecord[] = [];
    const iterator = await ctx.stub.getHistoryForKey(key);
    try {
      for (let next = await iterator.next(); !next.done; next = await iterator.next()) {
        const item = next.value;
        entries.push({
          txId: item.txId,
          timestamp: new Date(Number(item.timestamp.seconds) * 1000 + Math.floor(item.timestamp.nanos / 1e6)).toISOString(),
          isDelete: item.isDelete,
          value: item.value.length ? JSON.parse(Buffer.from(item.value).toString("utf8")) : null,
        });
      }
    } finally {
      await iterator.close();
    }
    return entries;
  }

  @Transaction(false)
  @Returns("string")
  public async GetAssetHistory(ctx: Context, assetId: string): Promise<string> {
    this.organization(ctx);
    return JSON.stringify(await this.history(ctx, this.key(ctx, "asset", requireString(assetId, "assetId", 64))));
  }

  @Transaction(false)
  @Returns("string")
  public async GetEventHistory(ctx: Context, eventId: string): Promise<string> {
    this.organization(ctx);
    return JSON.stringify(await this.history(ctx, this.key(ctx, "event", requireString(eventId, "eventId", 64))));
  }

  @Transaction(false)
  @Returns("string")
  public async GetAssetTimeline(ctx: Context, assetId: string): Promise<string> {
    this.organization(ctx);
    const normalized = requireString(assetId, "assetId", 64);
    const iterator = await ctx.stub.getStateByPartialCompositeKey("event", []);
    const events: JsonRecord[] = [];
    try {
      for (let next = await iterator.next(); !next.done; next = await iterator.next()) {
        const event = JSON.parse(Buffer.from(next.value.value).toString("utf8")) as JsonRecord;
        if (event.assetId === normalized) events.push(event);
      }
    } finally {
      await iterator.close();
    }
    events.sort((a, b) => String(a.performedAt).localeCompare(String(b.performedAt)));
    return JSON.stringify(events);
  }

  @Transaction(false)
  @Returns("string")
  public async GetLedgerInfo(ctx: Context): Promise<string> {
    const organization = this.organization(ctx);
    return JSON.stringify({ channel: ctx.stub.getChannelID(), chaincode: "fieldledger", organization });
  }
}
