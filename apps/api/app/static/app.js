"use strict";

const state = {
  token: sessionStorage.getItem("fieldledger_token"),
  user: null,
  assets: [],
  events: [],
  operations: [],
  telemetryReadings: [],
  telemetryBatches: [],
  selectedAsset: null,
  activeEventId: null,
  refreshing: false,
  timer: null,
};

const roles = {
  createAsset: new Set(["ADMIN", "OPERATOR"]),
  decommission: new Set(["ADMIN", "OPERATOR"]),
  propose: new Set(["CONTRACTOR"]),
  review: new Set(["ADMIN", "OPERATOR"]),
  upload: new Set(["ADMIN", "OPERATOR", "CONTRACTOR", "AUDITOR"]),
  verify: new Set(["ADMIN", "OPERATOR", "AUDITOR"]),
  telemetry: new Set(["ADMIN", "OPERATOR", "CONTRACTOR", "AUDITOR", "VIEWER"]),
};

const labels = {
  roles: { ADMIN: "ADMIN", OPERATOR: "OPERADORA", CONTRACTOR: "CONTRATISTA", AUDITOR: "AUDITOR", VIEWER: "LECTURA" },
  status: {
    ACTIVE: "Activo",
    MAINTENANCE: "En mantenimiento",
    OUT_OF_SERVICE: "Fuera de servicio",
    DECOMMISSIONED: "Desafectado",
    PROPOSED: "Propuesto",
    APPROVED: "Aprobado",
    REJECTED: "Rechazado",
    PENDING: "Pendiente",
    SUBMITTED: "Enviado",
    COMMITTED: "Confirmado",
    FAILED: "Fallido",
  },
  actions: {
    REGISTER_ASSET: "Alta de activo",
    PROPOSE_EVENT: "Propuesta",
    REGISTER_DOCUMENT: "Evidencia",
    REVIEW_EVENT: "Decisión",
    DECOMMISSION_ASSET: "Baja formal",
    REGISTER_TELEMETRY_BATCH: "Lote telemetría",
  },
  types: {
    PREVENTIVE_MAINTENANCE: "Preventivo",
    CORRECTIVE_MAINTENANCE: "Correctivo",
    PART_REPLACEMENT: "Reemplazo de componente",
    INSPECTION: "Inspección de integridad",
    PRESSURE_TEST: "Prueba hidrostática",
    CALIBRATION: "Calibración",
    CERTIFICATION: "Certificación de aptitud",
    DECOMMISSION: "Baja y abandono",
  },
  categories: {
    WORK_ORDER: "Orden de Trabajo (PTW)",
    CALIBRATION_CERT: "Certificado Calibración",
    INSPECTION_PHOTO: "Foto de Inspección",
    NDT_REPORT: "Ensayo No Destructivo (NDT)",
    LAB_ANALYSIS: "Análisis de Laboratorio",
    DECOMMISSION_RECORD: "Acta de Desafectación",
    OTHER: "Evidencia General",
  },
  timelineMarks: {
    CREATION: "ALTA",
    EVENT: "MANT",
    DOCUMENT: "DOC",
    REVIEW: "REV",
    TELEMETRY_BATCH: "IOT",
    DECOMMISSION: "BAJA",
  },
};

const errors = {
  "Could not validate credentials": "Usuario o contraseña incorrectos.",
  "Too many login attempts": "Demasiados intentos. Esperá un minuto y volvé a probar.",
  "Role is not allowed to perform this action": "Tu rol no permite realizar esta acción.",
  "Asset already exists": "Ya existe un activo con ese ID.",
  "Asset is already decommissioned": "El activo ya fue desafectado formalmente.",
  "Event or idempotency key already exists": "El evento ya existe. Generá una nueva propuesta.",
  "Reviewed events cannot accept documents": "Un evento revisado ya no acepta documentos.",
  "Event has already been reviewed": "El evento ya fue revisado.",
  "No unbatched telemetry readings available to anchor": "No hay nuevas lecturas sin anclar para este activo.",
  "Fabric verification failed": "No fue posible consultar Fabric. Intentá nuevamente.",
};

const $ = (selector) => document.querySelector(selector);
const loginView = $("#login-view");
const appView = $("#app-view");

function element(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined && text !== null) item.textContent = String(text);
  return item;
}

function translated(group, value) {
  return labels[group]?.[value] || value || "—";
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function cleanId(prefix) {
  const suffix = globalThis.crypto?.randomUUID?.().slice(0, 8) || Date.now().toString(36);
  return `${prefix}-${suffix.toUpperCase()}`;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.hidden = false;
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => { toast.hidden = true; }, 4500);
}

function readableError(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === "string") return errors[detail] || detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" · ");
  return `La operación no pudo completarse (HTTP ${status}).`;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { ...options, headers });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.endsWith("/auth/login")) logout(false);
    throw new Error(readableError(payload, response.status));
  }
  return payload;
}

async function health() {
  try {
    const response = await fetch("/ready", { cache: "no-store" });
    const payload = await response.json();
    return response.ok && payload.status === "ready";
  } catch {
    return false;
  }
}

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    button.textContent = label || "Procesando…";
  } else if (button.dataset.originalLabel) {
    button.textContent = button.dataset.originalLabel;
    delete button.dataset.originalLabel;
  }
  button.disabled = busy;
}

async function login(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const error = $("#login-error");
  error.textContent = "";
  setBusy(button, true, "Validando…");
  try {
    const form = new FormData(event.currentTarget);
    const payload = await request("/api/v1/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username: form.get("username"), password: form.get("password") }),
    });
    state.token = payload.access_token;
    sessionStorage.setItem("fieldledger_token", state.token);
    event.currentTarget.reset();
    await startSession();
  } catch (problem) {
    error.textContent = problem.message;
  } finally {
    setBusy(button, false);
  }
}

async function demoLogin() {
  const button = $("#demo-login-button");
  const error = $("#login-error");
  error.textContent = "";
  setBusy(button, true, "Ingresando…");
  try {
    const payload = await request("/api/v1/auth/demo", { method: "POST" });
    state.token = payload.access_token;
    sessionStorage.setItem("fieldledger_token", state.token);
    await startSession();
  } catch (problem) {
    error.textContent = problem.message;
  } finally {
    setBusy(button, false);
  }
}

async function configureDemoAccess() {
  try {
    const response = await fetch("/api/v1/auth/demo", { cache: "no-store" });
    const payload = await response.json();
    $("#demo-login-button").hidden = payload.enabled !== true;
  } catch {
    $("#demo-login-button").hidden = true;
  }
}

function logout(notify = true) {
  sessionStorage.removeItem("fieldledger_token");
  state.token = null;
  state.user = null;
  state.assets = [];
  state.events = [];
  state.operations = [];
  state.telemetryReadings = [];
  state.telemetryBatches = [];
  state.selectedAsset = null;
  clearInterval(state.timer);
  state.timer = null;
  appView.hidden = true;
  loginView.hidden = false;
  $("#username").focus();
  if (notify) showToast("Sesión cerrada.");
}

async function startSession() {
  try {
    state.user = await request("/api/v1/auth/me");
    loginView.hidden = true;
    appView.hidden = false;
    $("#user-name").textContent = state.user.username;
    $("#user-role").textContent = translated("roles", state.user.role);
    $("#user-organization").textContent = state.user.organization_id;
    applyPermissions();
    await refreshAll();
    clearInterval(state.timer);
    state.timer = setInterval(() => {
      if (!document.hidden) refreshAll(true);
    }, 30000);
  } catch (problem) {
    logout(false);
    $("#login-error").textContent = problem.message;
  }
}

function applyPermissions() {
  const role = state.user.role;
  const canCreate = roles.createAsset.has(role);
  $("#create-asset-button").hidden = !canCreate;
  $("#propose-button").hidden = !roles.propose.has(role);
  $("#simulate-telemetry-btn").disabled = !roles.telemetry.has(role);
  $("#anchor-batch-btn").disabled = !roles.telemetry.has(role);
  $("#verify-form").querySelector("button").disabled = !roles.verify.has(role);
  $("#verify-file").disabled = !roles.verify.has(role);

  const hero = $("#hero-primary");
  hero.hidden = false;
  if (canCreate) {
    hero.textContent = "Registrar activo";
    hero.dataset.action = "asset";
  } else if (roles.propose.has(role)) {
    hero.textContent = "Proponer mantenimiento";
    hero.dataset.action = "maintenance";
  } else if (roles.verify.has(role)) {
    hero.textContent = "Verificar evidencia";
    hero.dataset.action = "verify";
  } else {
    hero.textContent = "Explorar activos";
    hero.dataset.action = "assets";
  }
}

async function refreshAll(quiet = false) {
  if (state.refreshing || !state.user) return;
  state.refreshing = true;
  const refreshButton = $("#refresh-button");
  refreshButton.classList.add("loading");
  try {
    const selectedId = state.selectedAsset?.asset_id;
    const [assets, operations, isHealthy] = await Promise.all([
      request("/api/v1/assets?limit=500"),
      request("/api/v1/ledger/operations?limit=50"),
      health(),
    ]);
    state.assets = assets;
    state.operations = operations;
    state.selectedAsset = assets.find((asset) => asset.asset_id === selectedId) || assets[0] || null;

    if (state.selectedAsset) {
      const [events, readings, batches] = await Promise.all([
        request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/events?limit=500`),
        request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/telemetry?limit=20`),
        request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/telemetry/batches`),
      ]);
      state.events = events;
      state.telemetryReadings = readings;
      state.telemetryBatches = batches;
    } else {
      state.events = [];
      state.telemetryReadings = [];
      state.telemetryBatches = [];
    }

    render(isHealthy);
    if (!quiet) showToast("Datos actualizados.");
  } catch (problem) {
    if (!quiet) showToast(problem.message, true);
  } finally {
    state.refreshing = false;
    refreshButton.classList.remove("loading");
  }
}

function render(isHealthy) {
  $("#asset-count").textContent = state.assets.length;
  $("#event-count").textContent = state.events.length;
  $("#commit-count").textContent = state.operations.filter((item) => item.status === "COMMITTED").length;
  const healthLabel = $("#health-status");
  healthLabel.textContent = isHealthy ? "Listo" : "Atención";
  healthLabel.classList.toggle("not-ready", !isHealthy);
  renderAssets();
  renderAssetDetail();
  renderEvents();
  renderTelemetry();
  renderLedger();
}

function renderAssets() {
  const query = $("#asset-search").value.trim().toLocaleLowerCase("es");
  const filtered = state.assets.filter((asset) =>
    [asset.asset_id, asset.name, asset.site, asset.asset_type].some((value) => value?.toLocaleLowerCase("es").includes(query))
  );
  $("#asset-list-count").textContent = `${filtered.length} ${filtered.length === 1 ? "activo" : "activos"}`;
  const list = $("#asset-list");
  list.replaceChildren();
  if (!filtered.length) {
    list.append(element("div", "table-empty", query ? "No hay coincidencias." : "Todavía no hay activos."));
    return;
  }
  filtered.forEach((asset) => {
    const button = element("button", `asset-row${asset.asset_id === state.selectedAsset?.asset_id ? " active" : ""}`);
    button.type = "button";
    button.append(
      element("strong", null, asset.name),
      element("span", `criticality ${asset.criticality}`, asset.criticality),
      element("span", null, `${asset.asset_type} · ${asset.site}`),
      element("span", "asset-id", `${asset.asset_id} · ${translated("status", asset.status)}`),
    );
    button.addEventListener("click", () => selectAsset(asset));
    list.append(button);
  });
}

async function selectAsset(asset) {
  state.selectedAsset = asset;
  try {
    const [events, readings, batches] = await Promise.all([
      request(`/api/v1/assets/${encodeURIComponent(asset.asset_id)}/events?limit=500`),
      request(`/api/v1/assets/${encodeURIComponent(asset.asset_id)}/telemetry?limit=20`),
      request(`/api/v1/assets/${encodeURIComponent(asset.asset_id)}/telemetry/batches`),
    ]);
    state.events = events;
    state.telemetryReadings = readings;
    state.telemetryBatches = batches;

    renderAssets();
    renderAssetDetail();
    renderEvents();
    renderTelemetry();
    $("#event-count").textContent = state.events.length;
    $("#current-context").textContent = asset.name;
  } catch (problem) {
    showToast(problem.message, true);
  }
}

function renderAssetDetail() {
  const panel = $("#asset-detail");
  panel.replaceChildren();
  if (!state.selectedAsset) {
    panel.className = "panel asset-detail empty-state";
    panel.append(element("div", "empty-mark", "FL"), element("h3", null, "Seleccioná un activo"), element("p", null, "Vas a ver sus datos, mantenimiento y estado de confirmación."));
    return;
  }
  panel.className = "panel asset-detail";
  const asset = state.selectedAsset;
  const headerCopy = element("div");
  headerCopy.append(element("p", "eyebrow", asset.asset_id), element("h3", null, asset.name), element("p", null, `${asset.asset_type} · ${asset.site}`));
  const header = element("div", "detail-header");
  header.append(headerCopy, element("span", "status-pill", translated("status", asset.status)));

  const grid = element("div", "detail-grid");
  [
    ["Ubicación / Pozo", asset.location], ["Criticidad", asset.criticality],
    ["Fabricante", asset.manufacturer], ["Número de serie", asset.serial_number],
    ["Operadora", asset.operator], ["Instalación", asset.installation_date],
    ["Creado", formatDate(asset.created_at)], ["Estado", translated("status", asset.status)],
  ].forEach(([name, value]) => {
    const field = element("div", "detail-field");
    field.append(element("span", null, name), element("strong", null, value || "No informado"));
    grid.append(field);
  });

  // Action buttons bar
  const actionsBar = element("div", "detail-actions-bar");
  const timelineBtn = element("button", "button button-secondary", "Ver trazabilidad e historial");
  timelineBtn.type = "button";
  timelineBtn.addEventListener("click", () => openTimeline(asset.asset_id));
  actionsBar.append(timelineBtn);

  if (asset.status !== "DECOMMISSIONED" && roles.decommission.has(state.user.role)) {
    const decomBtn = element("button", "button button-ghost", "Desafectar activo");
    decomBtn.type = "button";
    decomBtn.addEventListener("click", () => openDecommission(asset.asset_id));
    actionsBar.append(decomBtn);
  }

  panel.append(header, grid, actionsBar, element("p", "detail-note", "PostgreSQL conserva el estado relacional operativo. La identidad, sus evidencias y sus lotes de telemetría se anclan de manera inmutable en Hyperledger Fabric."));
}

function statusBadge(value) {
  return element("span", `status-badge ${value}`, translated("status", value));
}

function renderEvents() {
  const body = $("#event-table");
  const empty = $("#event-empty");
  body.replaceChildren();
  empty.hidden = state.events.length > 0;
  empty.textContent = state.selectedAsset ? "Este activo todavía no tiene eventos registrados." : "Seleccioná un activo para consultar su mantenimiento.";

  state.events.forEach((event) => {
    const row = document.createElement("tr");
    const identity = element("div", "table-primary");
    identity.append(element("strong", null, event.event_id), element("span", null, formatDate(event.timestamp)));
    const eventCell = document.createElement("td"); eventCell.append(identity);
    const typeCell = element("td", null, translated("types", event.event_type));
    const ownerCell = element("td", null, `${event.performed_by} · ${event.organization}`);

    // Evidencias (Multi-document list)
    const docCell = document.createElement("td");
    const docList = element("div", "doc-list");
    if (event.documents && event.documents.length > 0) {
      event.documents.forEach((doc) => {
        const pill = element("button", "doc-pill");
        pill.type = "button";
        pill.append(
          element("span", "doc-cat", translated("categories", doc.category)),
          element("span", null, `${doc.original_filename} (${roundKb(doc.size_bytes)} KB)`),
        );
        pill.addEventListener("click", () => openPreview(doc));
        docList.append(pill);
      });
    } else if (event.document_hash) {
      const pill = element("span", "doc-pill", `Hash: ${event.document_hash.slice(0, 10)}…`);
      docList.append(pill);
    } else {
      docList.append(element("span", "muted", "Sin evidencias"));
    }
    docCell.append(docList);

    const decisionCell = document.createElement("td"); decisionCell.append(statusBadge(event.status));
    const ledgerCell = document.createElement("td");
    const ledgerStack = element("div", "table-stack");
    ledgerStack.append(statusBadge(event.ledger_status));
    if (event.ledger_tx_id) {
      const tx = element("span", "tx-id", event.ledger_tx_id);
      tx.title = event.ledger_tx_id;
      ledgerStack.append(tx);
    }
    ledgerCell.append(ledgerStack);

    const actionsCell = document.createElement("td");
    const actions = element("div", "row-actions");
    if (event.status === "PROPOSED" && roles.upload.has(state.user.role)) {
      actions.append(actionButton("Adjuntar evidencia", () => openDocument(event.event_id)));
    }
    if (event.status === "PROPOSED" && roles.review.has(state.user.role)) {
      actions.append(actionButton("Aprobar", () => approveEvent(event.event_id), "approve"));
      actions.append(actionButton("Rechazar", () => openReject(event.event_id), "reject"));
    }
    if (!actions.children.length) actions.append(element("span", "muted", "Completado"));
    actionsCell.append(actions);

    row.append(eventCell, typeCell, ownerCell, docCell, decisionCell, ledgerCell, actionsCell);
    body.append(row);
  });
}

function roundKb(bytes) {
  return (bytes / 1024).toFixed(1);
}

function renderTelemetry() {
  // 1. Gauges
  const latest = state.telemetryReadings[0];
  $("#val-pressure").textContent = latest?.pressure_psi !== undefined && latest?.pressure_psi !== null ? latest.pressure_psi.toFixed(1) : "—";
  $("#val-temperature").textContent = latest?.temperature_c !== undefined && latest?.temperature_c !== null ? latest.temperature_c.toFixed(1) : "—";
  $("#val-vibration").textContent = latest?.vibration_mms !== undefined && latest?.vibration_mms !== null ? latest.vibration_mms.toFixed(2) : "—";
  $("#val-flow").textContent = latest?.flow_rate_bpd !== undefined && latest?.flow_rate_bpd !== null ? latest.flow_rate_bpd.toFixed(1) : "—";

  // 2. Batches Table
  const body = $("#telemetry-batches-table");
  const empty = $("#telemetry-empty");
  body.replaceChildren();
  empty.hidden = state.telemetryBatches.length > 0;

  state.telemetryBatches.forEach((batch) => {
    const row = document.createElement("tr");
    row.append(
      element("td", null, batch.batch_id),
      element("td", null, `${formatDate(batch.period_start)} → ${formatDate(batch.period_end)}`),
      element("td", null, `${batch.reading_count} lecturas`),
      element("td", "tx-id", batch.merkle_root),
      element("td", null, statusBadge(batch.ledger_status)),
      element("td", "tx-id", batch.ledger_tx_id || "Pendiente Fabric"),
    );
    const actionsCell = document.createElement("td");
    actionsCell.append(actionButton("Auditar Merkle", () => verifyTelemetryBatch(batch.batch_id)));
    row.append(actionsCell);
    body.append(row);
  });
}

async function simulateTelemetry() {
  if (!state.selectedAsset && state.assets.length > 0) {
    await selectAsset(state.assets[0]);
  }
  if (!state.selectedAsset) return showToast("No hay activos disponibles para simular.", true);
  const btn = $("#simulate-telemetry-btn");
  setBusy(btn, true, "Generando lecturas…");
  try {
    await request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/telemetry/simulate?count=15`, { method: "POST" });
    await refreshAll(true);
    showToast(`15 lecturas de sensores generadas para ${state.selectedAsset.asset_id}.`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setBusy(btn, false);
  }
}

async function anchorTelemetryBatch() {
  if (!state.selectedAsset && state.assets.length > 0) {
    await selectAsset(state.assets[0]);
  }
  if (!state.selectedAsset) return showToast("No hay activos disponibles para anclar.", true);
  const btn = $("#anchor-batch-btn");
  setBusy(btn, true, "Calculando Merkle Root…");
  try {
    const batch = await request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/telemetry/batch`, {
      method: "POST",
      body: { max_readings: 100 },
    });
    await refreshAll(true);
    showToast(`Lote ${batch.batch_id} anclado en Fabric. Merkle Root: ${batch.merkle_root.slice(0, 12)}…`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setBusy(btn, false);
  }
}

async function verifyTelemetryBatch(batchId) {
  try {
    const result = await request("/api/v1/telemetry/verify-batch", {
      method: "POST",
      body: { batch_id: batchId },
    });
    if (result.verified) {
      showToast(`Lote ${batchId} auditado: el Merkle Root coincide con el registro inmutable.`);
    } else {
      showToast(`Error de integridad en lote ${batchId}: Merkle root no coincide.`, true);
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

async function openTimeline(assetId) {
  const dialog = $("#timeline-dialog");
  const title = $("#timeline-title");
  const subtitle = $("#timeline-subtitle");
  const body = $("#timeline-body");
  title.textContent = `Trazabilidad y línea de tiempo: ${assetId}`;
  subtitle.textContent = "Consultando historial certificado desde PostgreSQL y Hyperledger Fabric…";
  body.replaceChildren(element("div", "table-empty", "Consultando eventos y transacciones…"));
  openDialog("timeline-dialog");

  try {
    const response = await request(`/api/v1/assets/${encodeURIComponent(assetId)}/timeline`);
    subtitle.textContent = `${response.asset_name} · ${response.timeline.length} hitos auditados`;
    body.replaceChildren();

    response.timeline.forEach((item, idx) => {
      const node = element("div", "timeline-node");
      const markLabel = translated("timelineMarks", item.item_type) || String(idx + 1).padStart(2, "0");
      const mark = element("div", `timeline-mark ${item.item_type}`, markLabel);
      const card = element("div", "timeline-card");

      const head = element("div", "timeline-card-head");
      head.append(element("strong", null, item.title), element("span", "timeline-time", formatDate(item.timestamp)));

      const desc = element("p", "timeline-desc", item.description);

      const meta = element("div", "timeline-meta-bar");
      meta.append(element("span", null, `Por: ${item.author} (${item.organization})`));
      if (item.ledger_tx_id) {
        const tx = element("span", "timeline-tx", `Tx: ${item.ledger_tx_id}`);
        tx.title = item.ledger_tx_id;
        meta.append(tx);
      }
      if (item.block_number) meta.append(element("span", null, `Bloque #${item.block_number}`));
      if (item.document_hash) meta.append(element("span", "hash-tag", `SHA-256: ${item.document_hash.slice(0, 16)}…`));

      card.append(head, desc, meta);
      node.append(mark, card);
      body.append(node);
    });
  } catch (err) {
    body.replaceChildren(element("div", "table-empty", `Error al cargar timeline: ${err.message}`));
  }
}

function openPreview(doc) {
  $("#preview-filename").textContent = doc.original_filename;
  const content = $("#preview-content");
  content.replaceChildren();

  const details = [
    ["Categoría Técnica", translated("categories", doc.category)],
    ["Tipo MIME", doc.content_type],
    ["Tamaño", `${roundKb(doc.size_bytes)} KB`],
    ["Subido por", doc.uploaded_by],
    ["Fecha de registro", formatDate(doc.created_at)],
    ["Estado en Ledger", translated("status", doc.ledger_status)],
    ["Notas de campo", doc.notes || "Sin observaciones"],
  ];

  details.forEach(([k, v]) => {
    const row = element("div", "preview-meta-row");
    row.append(element("span", "muted", k), element("strong", null, v));
    content.append(row);
  });

  const hashRow = element("div", null);
  hashRow.append(
    element("p", "muted", "Huella Digital SHA-256 certificada en Fabric:"),
    element("p", "hash-tag", doc.sha256_hash),
  );
  content.append(hashRow);

  openDialog("preview-dialog");
}

function actionButton(text, action, kind = "") {
  const button = element("button", `mini-button ${kind}`, text);
  button.type = "button";
  button.addEventListener("click", action);
  return button;
}

function renderLedger() {
  const body = $("#ledger-table");
  const empty = $("#ledger-empty");
  body.replaceChildren();
  empty.hidden = state.operations.length > 0;
  state.operations.forEach((operation) => {
    const row = document.createElement("tr");
    const identity = element("div", "table-primary");
    identity.append(element("strong", null, translated("actions", operation.action)), element("span", null, `${operation.aggregate_type} · ${operation.aggregate_id}`));
    const operationCell = document.createElement("td"); operationCell.append(identity);
    const organizationCell = element("td", null, operation.organization);
    const statusCell = document.createElement("td"); statusCell.append(statusBadge(operation.status));
    const txCell = document.createElement("td");
    const tx = element("span", "tx-id", operation.ledger_tx_id || "Pendiente de confirmación");
    if (operation.ledger_tx_id) tx.title = operation.ledger_tx_id;
    txCell.append(tx);
    row.append(operationCell, organizationCell, statusCell, txCell, element("td", null, operation.block_number || "—"));
    body.append(row);
  });
}

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (!dialog.open) dialog.showModal();
}

function closeDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog.open) dialog.close();
}

function openAsset() {
  if (!roles.createAsset.has(state.user.role)) return showToast("Ingresá como operadora para registrar activos.", true);
  $("#asset-form").reset();
  openDialog("asset-dialog");
}

function openMaintenance() {
  if (!roles.propose.has(state.user.role)) return showToast("Solo la contratista puede proponer mantenimiento.", true);
  if (!state.selectedAsset) return showToast("Seleccioná primero un activo.", true);
  const form = $("#maintenance-form");
  form.reset();
  form.elements.event_id.value = cleanId("EVT");
  form.elements.idempotency_key.value = `ui-${globalThis.crypto?.randomUUID?.() || Date.now()}`;
  $("#maintenance-asset-label").textContent = `${state.selectedAsset.asset_id} · ${state.selectedAsset.name}`;
  openDialog("maintenance-dialog");
}

function openDocument(eventId) {
  state.activeEventId = eventId;
  $("#document-form").reset();
  $("#document-file-name").textContent = "PDF, JPEG o PNG · máximo 10 MiB";
  $("#document-event-label").textContent = `Evento ${eventId}`;
  openDialog("document-dialog");
}

function openReject(eventId) {
  state.activeEventId = eventId;
  $("#reject-form").reset();
  $("#reject-event-label").textContent = `Evento ${eventId}`;
  openDialog("reject-dialog");
}

function openDecommission(assetId) {
  if (!roles.decommission.has(state.user.role)) return showToast("Solo la operadora puede dar de baja activos.", true);
  const form = $("#decommission-form");
  form.reset();
  $("#decommission-asset-label").textContent = `Activo: ${assetId}`;
  openDialog("decommission-dialog");
}

async function createAsset(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  setBusy(button, true);
  try {
    const values = Object.fromEntries(new FormData(event.currentTarget));
    Object.keys(values).forEach((key) => { if (values[key] === "") delete values[key]; });
    const asset = await request("/api/v1/assets", { method: "POST", body: values });
    closeDialog("asset-dialog");
    state.selectedAsset = asset;
    await refreshAll(true);
    showToast(`Activo ${asset.asset_id} registrado y encolado para Fabric.`);
  } catch (problem) {
    showToast(problem.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function createMaintenance(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  setBusy(button, true);
  try {
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const created = await request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/maintenance`, { method: "POST", body: values });
    closeDialog("maintenance-dialog");
    await refreshAll(true);
    showToast(`Propuesta ${created.event_id} creada. Esperando confirmación del ledger.`);
  } catch (problem) {
    showToast(problem.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  setBusy(button, true);
  try {
    const payload = new FormData(event.currentTarget);
    const documentRecord = await request(`/api/v1/events/${encodeURIComponent(state.activeEventId)}/documents`, { method: "POST", body: payload });
    closeDialog("document-dialog");
    await refreshAll(true);
    showToast(`Evidencia guardada (${translated("categories", documentRecord.category)}). SHA-256 ${documentRecord.sha256_hash.slice(0, 12)}…`);
  } catch (problem) {
    showToast(problem.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function approveEvent(eventId) {
  try {
    await request(`/api/v1/events/${encodeURIComponent(eventId)}/approve`, { method: "POST", body: {} });
    await refreshAll(true);
    showToast(`Evento ${eventId} aprobado y encolado para Fabric.`);
  } catch (problem) {
    showToast(problem.message, true);
  }
}

async function rejectEvent(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  setBusy(button, true);
  try {
    const reason = new FormData(event.currentTarget).get("reason");
    await request(`/api/v1/events/${encodeURIComponent(state.activeEventId)}/reject`, { method: "POST", body: { reason } });
    closeDialog("reject-dialog");
    await refreshAll(true);
    showToast(`Evento ${state.activeEventId} rechazado.`);
  } catch (problem) {
    showToast(problem.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function decommissionAsset(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  setBusy(button, true);
  try {
    const reason = new FormData(event.currentTarget).get("reason");
    const updated = await request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/decommission`, {
      method: "POST",
      body: { reason },
    });
    closeDialog("decommission-dialog");
    state.selectedAsset = updated;
    await refreshAll(true);
    showToast(`Activo ${updated.asset_id} desafectado formalmente en Fabric.`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function verifyDocument(event) {
  event.preventDefault();
  if (!roles.verify.has(state.user.role)) return showToast("Tu rol no puede verificar evidencia.", true);
  const button = event.currentTarget.querySelector("button[type=submit]");
  const resultBox = $("#verification-result");
  resultBox.replaceChildren();
  setBusy(button, true, "Consultando Fabric…");
  try {
    const result = await request("/api/v1/documents/verify", { method: "POST", body: new FormData(event.currentTarget) });
    const box = element("div", `verification-message${result.verified ? "" : " failed"}`);
    box.append(
      element("strong", null, result.verified ? "Evidencia verificada en Ledger" : "No existe una huella coincidente"),
      element("span", null, result.verified ? "Hyperledger Fabric confirmó que los bytes coinciden exactamente con el registro inmutable." : "El archivo fue modificado o nunca se registró en el consorcio."),
      element("code", null, result.sha256_hash),
    );
    resultBox.append(box);
  } catch (problem) {
    const box = element("div", "verification-message failed");
    box.append(element("strong", null, "No fue posible verificar"), element("span", null, problem.message));
    resultBox.append(box);
  } finally {
    setBusy(button, false);
  }
}

$("#login-form").addEventListener("submit", login);
$("#demo-login-button").addEventListener("click", demoLogin);
$("#logout-button").addEventListener("click", () => logout());
$("#refresh-button").addEventListener("click", () => refreshAll());
$("#asset-search").addEventListener("input", renderAssets);
$("#create-asset-button").addEventListener("click", openAsset);
$("#propose-button").addEventListener("click", openMaintenance);
$("#simulate-telemetry-btn").addEventListener("click", simulateTelemetry);
$("#anchor-batch-btn").addEventListener("click", anchorTelemetryBatch);
$("#asset-form").addEventListener("submit", createAsset);
$("#maintenance-form").addEventListener("submit", createMaintenance);
$("#document-form").addEventListener("submit", uploadDocument);
$("#reject-form").addEventListener("submit", rejectEvent);
$("#decommission-form").addEventListener("submit", decommissionAsset);
$("#verify-form").addEventListener("submit", verifyDocument);
$("#verify-file").addEventListener("change", (event) => { $("#verify-file-name").textContent = event.target.files[0]?.name || "PDF, JPEG o PNG"; });
$("#document-file").addEventListener("change", (event) => { $("#document-file-name").textContent = event.target.files[0]?.name || "PDF, JPEG o PNG · máximo 10 MiB"; });
$("#hero-primary").addEventListener("click", (event) => {
  const action = event.currentTarget.dataset.action;
  if (action === "asset") openAsset();
  if (action === "maintenance") openMaintenance();
  if (action === "verify") $("#verify").scrollIntoView();
  if (action === "assets") $("#assets").scrollIntoView();
});

document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeDialog(button.dataset.close)));
document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
}));

configureDemoAccess();
if (state.token) startSession();
else $("#username").focus();
