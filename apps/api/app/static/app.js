"use strict";

const state = {
  token: sessionStorage.getItem("fieldledger_token"),
  user: null,
  assets: [],
  events: [],
  operations: [],
  selectedAsset: null,
  activeEventId: null,
  refreshing: false,
  timer: null,
};

const roles = {
  createAsset: new Set(["ADMIN", "OPERATOR"]),
  propose: new Set(["CONTRACTOR"]),
  review: new Set(["ADMIN", "OPERATOR"]),
  upload: new Set(["ADMIN", "OPERATOR", "CONTRACTOR", "AUDITOR"]),
  verify: new Set(["ADMIN", "OPERATOR", "AUDITOR"]),
};

const labels = {
  roles: { ADMIN: "ADMIN", OPERATOR: "OPERADORA", CONTRACTOR: "CONTRATISTA", AUDITOR: "AUDITOR", VIEWER: "LECTURA" },
  status: { ACTIVE: "Activo", MAINTENANCE: "En mantenimiento", OUT_OF_SERVICE: "Fuera de servicio", DECOMMISSIONED: "Dado de baja", PROPOSED: "Propuesto", APPROVED: "Aprobado", REJECTED: "Rechazado", PENDING: "Pendiente", SUBMITTED: "Enviado", COMMITTED: "Confirmado", FAILED: "Fallido" },
  actions: { REGISTER_ASSET: "Alta de activo", PROPOSE_EVENT: "Propuesta", REGISTER_DOCUMENT: "Evidencia", REVIEW_EVENT: "Decisión" },
  types: { PREVENTIVE_MAINTENANCE: "Preventivo", CORRECTIVE_MAINTENANCE: "Correctivo", PART_REPLACEMENT: "Reemplazo" },
};

const errors = {
  "Could not validate credentials": "Usuario o contraseña incorrectos.",
  "Too many login attempts": "Demasiados intentos. Esperá un minuto y volvé a probar.",
  "Role is not allowed to perform this action": "Tu rol no permite realizar esta acción.",
  "Asset already exists": "Ya existe un activo con ese ID.",
  "Event or idempotency key already exists": "El evento ya existe. Generá una nueva propuesta.",
  "This event already has a document": "Este evento ya tiene una evidencia primaria.",
  "Reviewed events cannot accept documents": "Un evento revisado ya no acepta documentos.",
  "Event has already been reviewed": "El evento ya fue revisado.",
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
    }, 8000);
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
    state.events = state.selectedAsset
      ? await request(`/api/v1/assets/${encodeURIComponent(state.selectedAsset.asset_id)}/events?limit=500`)
      : [];
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
      element("span", "asset-id", asset.asset_id),
    );
    button.addEventListener("click", () => selectAsset(asset));
    list.append(button);
  });
}

async function selectAsset(asset) {
  state.selectedAsset = asset;
  try {
    state.events = await request(`/api/v1/assets/${encodeURIComponent(asset.asset_id)}/events?limit=500`);
    renderAssets();
    renderAssetDetail();
    renderEvents();
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
    ["Ubicación", asset.location], ["Criticidad", asset.criticality],
    ["Fabricante", asset.manufacturer], ["Número de serie", asset.serial_number],
    ["Operadora", asset.operator], ["Instalación", asset.installation_date],
    ["Creado", formatDate(asset.created_at)], ["Actualizado", formatDate(asset.updated_at)],
  ].forEach(([name, value]) => {
    const field = element("div", "detail-field");
    field.append(element("span", null, name), element("strong", null, value || "No informado"));
    grid.append(field);
  });
  panel.append(header, grid, element("p", "detail-note", "PostgreSQL conserva el detalle operativo. La identidad compacta del activo se entrega a Fabric mediante la outbox."));
}

function statusBadge(value) {
  return element("span", `status-badge ${value}`, translated("status", value));
}

function renderEvents() {
  const body = $("#event-table");
  const empty = $("#event-empty");
  body.replaceChildren();
  empty.hidden = state.events.length > 0;
  empty.textContent = state.selectedAsset ? "Este activo todavía no tiene eventos." : "Seleccioná un activo para consultar su mantenimiento.";
  state.events.forEach((event) => {
    const row = document.createElement("tr");
    const identity = element("div", "table-primary");
    identity.append(element("strong", null, event.event_id), element("span", null, formatDate(event.timestamp)));
    const eventCell = document.createElement("td"); eventCell.append(identity);
    const typeCell = element("td", null, translated("types", event.event_type));
    const ownerCell = element("td", null, `${event.performed_by} · ${event.organization}`);
    const decisionCell = document.createElement("td"); decisionCell.append(statusBadge(event.status));
    const ledgerCell = document.createElement("td");
    ledgerCell.append(statusBadge(event.ledger_status));
    if (event.ledger_tx_id) {
      const tx = element("span", "tx-id", event.ledger_tx_id);
      tx.title = event.ledger_tx_id;
      ledgerCell.append(tx);
    }
    const actionsCell = document.createElement("td");
    const actions = element("div", "row-actions");
    if (event.status === "PROPOSED" && !event.document_hash && roles.upload.has(state.user.role)) {
      actions.append(actionButton("Adjuntar", () => openDocument(event.event_id)));
    }
    if (event.status === "PROPOSED" && roles.review.has(state.user.role)) {
      actions.append(actionButton("Aprobar", () => approveEvent(event.event_id), "approve"));
      actions.append(actionButton("Rechazar", () => openReject(event.event_id), "reject"));
    }
    if (!actions.children.length) actions.append(element("span", "muted", "Sin acciones"));
    actionsCell.append(actions);
    row.append(eventCell, typeCell, ownerCell, decisionCell, ledgerCell, actionsCell);
    body.append(row);
  });
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
    showToast(`Evidencia guardada. SHA-256 ${documentRecord.sha256_hash.slice(0, 12)}…`);
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
      element("strong", null, result.verified ? "Evidencia verificada" : "No existe una huella coincidente"),
      element("span", null, result.verified ? "Fabric confirmó que los bytes coinciden con el registro." : "El archivo fue modificado o nunca se registró."),
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
$("#asset-form").addEventListener("submit", createAsset);
$("#maintenance-form").addEventListener("submit", createMaintenance);
$("#document-form").addEventListener("submit", uploadDocument);
$("#reject-form").addEventListener("submit", rejectEvent);
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
