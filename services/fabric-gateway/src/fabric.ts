import * as grpc from "@grpc/grpc-js";
import {
  connect,
  Contract,
  Gateway,
  hash,
  Identity,
  signers,
} from "@hyperledger/fabric-gateway";
import { promises as fs } from "node:fs";
import path from "node:path";

export const ORGANIZATIONS = {
  OperatorOrg: { mspId: "Org1MSP", domain: "org1.example.com" },
  ContractorOrg: { mspId: "Org2MSP", domain: "org2.example.com" },
  AuditorOrg: { mspId: "Org3MSP", domain: "org3.example.com" },
} as const;

export type Organization = keyof typeof ORGANIZATIONS;

export const ACTIONS = {
  REGISTER_ASSET: "CreateAsset",
  PROPOSE_EVENT: "ProposeEvent",
  REVIEW_EVENT: "ReviewEvent",
  REGISTER_DOCUMENT: "RegisterDocument",
} as const;

export type Action = keyof typeof ACTIONS;

const cryptoRoot = process.env.FABRIC_CRYPTO_ROOT ?? "/fabric/organizations";
const channelName = process.env.FABRIC_CHANNEL ?? "fieldledgerchannel";
const chaincodeName = process.env.FABRIC_CHAINCODE ?? "fieldledger";
const peerEndpoint = process.env.FABRIC_PEER_ENDPOINT ?? "peer0.org1.example.com:7051";
const peerHostAlias = process.env.FABRIC_PEER_HOST_ALIAS ?? "peer0.org1.example.com";

function deadline(seconds: number): () => Date {
  return () => new Date(Date.now() + seconds * 1000);
}

function organizationConfig(organization: string) {
  const config = ORGANIZATIONS[organization as Organization];
  if (!config) throw new Error("unsupported organization");
  return config;
}

async function firstFile(directory: string): Promise<string> {
  const files = (await fs.readdir(directory)).sort();
  if (files.length !== 1) throw new Error(`expected one identity file in ${directory}`);
  return path.join(directory, files[0]);
}

async function connection(organization: string): Promise<{ gateway: Gateway; client: grpc.Client }> {
  const config = organizationConfig(organization);
  const orgRoot = path.join(cryptoRoot, "peerOrganizations", config.domain);
  const userMsp = path.join(orgRoot, "users", `User1@${config.domain}`, "msp");
  const certificate = await fs.readFile(await firstFile(path.join(userMsp, "signcerts")));
  const privateKeyPem = await fs.readFile(await firstFile(path.join(userMsp, "keystore")));
  const operatorRoot = path.join(cryptoRoot, "peerOrganizations", "org1.example.com");
  const tlsRootCert = await fs.readFile(
    path.join(operatorRoot, "peers", "peer0.org1.example.com", "tls", "ca.crt"),
  );
  const privateKey = await import("node:crypto").then(({ createPrivateKey }) => createPrivateKey(privateKeyPem));
  const identity: Identity = { mspId: config.mspId, credentials: certificate };
  const credentials = grpc.credentials.createSsl(tlsRootCert);
  const client = new grpc.Client(peerEndpoint, credentials, {
    "grpc.ssl_target_name_override": peerHostAlias,
  });
  const gateway = connect({
    client,
    identity,
    signer: signers.newPrivateKeySigner(privateKey),
    hash: hash.sha256,
    evaluateOptions: () => ({ deadline: deadline(10)() }),
    endorseOptions: () => ({ deadline: deadline(30)() }),
    submitOptions: () => ({ deadline: deadline(10)() }),
    commitStatusOptions: () => ({ deadline: deadline(90)() }),
  });
  return { gateway, client };
}

async function withContract<T>(organization: string, callback: (contract: Contract) => Promise<T>): Promise<T> {
  const { gateway, client } = await connection(organization);
  try {
    return await callback(gateway.getNetwork(channelName).getContract(chaincodeName));
  } finally {
    gateway.close();
    client.close();
  }
}

export async function submit(
  organization: string,
  action: string,
  operationId: string,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const transactionName = ACTIONS[action as Action];
  if (!transactionName) throw new Error("unsupported ledger action");
  return withContract(organization, async (contract) => {
    const proposal = contract.newProposal(transactionName, {
      arguments: [operationId, JSON.stringify(payload)],
    });
    const transaction = await proposal.endorse();
    const submitted = await transaction.submit();
    const status = await submitted.getStatus();
    if (!status.successful) throw new Error(`transaction committed with status ${status.code}`);
    const resultText = Buffer.from(transaction.getResult()).toString("utf8");
    return {
      transactionId: submitted.getTransactionId(),
      blockNumber: status.blockNumber.toString(),
      result: resultText ? JSON.parse(resultText) : null,
    };
  });
}

export async function evaluate(
  organization: string,
  transactionName: string,
  ...args: string[]
): Promise<unknown> {
  const allowed = new Set(["GetAsset", "GetEvent", "GetDocumentByHash", "GetAssetTimeline", "GetAssetHistory", "GetEventHistory", "GetLedgerInfo"]);
  if (!allowed.has(transactionName)) throw new Error("unsupported ledger query");
  return withContract(organization, async (contract) => {
    const result = await contract.evaluateTransaction(transactionName, ...args);
    const text = Buffer.from(result).toString("utf8");
    return text ? JSON.parse(text) : null;
  });
}
