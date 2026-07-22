"use strict";

const state = {
  receipts: [],
  merchants: [],
  methods: [],
  receipt: null,
  items: [],
  payments: [],
  reconciliation: null,
  events: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const today = () => new Date().toISOString().slice(0, 10);
const money = (value, currency = "EUR") => new Intl.NumberFormat("en-DE", { style: "currency", currency }).format(Number(value));
const formatDate = (value) => new Intl.DateTimeFormat("en-DE", { dateStyle: "medium" }).format(new Date(`${value}T00:00:00`));
const formatTime = (value) => new Intl.DateTimeFormat("en-DE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
const titleCase = (value) => String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      if (Array.isArray(body.detail)) message = body.detail.map((item) => item.msg).join(", ");
    } catch (_) { /* Use the fallback message. */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

let noticeTimer;
function notify(message, error = false) {
  const notice = $("#notice");
  clearTimeout(noticeTimer);
  notice.textContent = message;
  notice.classList.toggle("error", error);
  notice.hidden = false;
  noticeTimer = setTimeout(() => { notice.hidden = true; }, 5000);
}

async function run(action, successMessage) {
  try {
    const result = await action();
    if (successMessage) notify(successMessage);
    return result;
  } catch (error) {
    notify(error.message || "Something went wrong", true);
    throw error;
  }
}

function merchantName(id) {
  return state.merchants.find((merchant) => merchant.id === id)?.name || "No merchant";
}

function methodName(id) {
  const method = state.methods.find((item) => item.id === id);
  if (!method) return "Removed payment method";
  return `${method.name}${method.last_four ? ` •••• ${method.last_four}` : ""}`;
}

function switchView(name) {
  $$(".view").forEach((view) => { view.hidden = view.id !== `${name}-view`; });
  $$(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  if (name === "settings") renderSettings();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadSetup() {
  [state.merchants, state.methods] = await Promise.all([
    api("/merchants"),
    api("/payment-methods?include_inactive=true"),
  ]);
  renderSelects();
  renderSettings();
}

function renderSelects() {
  $$('[data-merchant-select]').forEach((select) => {
    const selected = select.value;
    select.innerHTML = `<option value="">No merchant</option>${state.merchants.map((merchant) => `<option value="${merchant.id}">${escapeHtml(merchant.name)}</option>`).join("")}`;
    select.value = selected;
  });
  $$('[data-payment-select]').forEach((select) => {
    const selected = select.value;
    select.innerHTML = `<option value="">Choose method</option>${state.methods.filter((method) => method.is_active).map((method) => `<option value="${method.id}">${escapeHtml(methodName(method.id))}</option>`).join("")}`;
    select.value = selected;
  });
}

async function loadReceipts() {
  state.receipts = await api("/receipts?limit=100");
  renderReceiptIndex();
}

function renderReceiptIndex() {
  const drafts = state.receipts.filter((receipt) => receipt.status === "draft").length;
  const approved = state.receipts.filter((receipt) => receipt.status === "approved");
  const approvedTotal = approved.reduce((total, receipt) => total + Number(receipt.stated_total), 0);
  $("#receipt-summary").innerHTML = [
    ["Total receipts", state.receipts.length],
    ["Drafts", drafts],
    ["Approved", approved.length],
    ["Approved value", money(approvedTotal)],
  ].map(([label, value]) => `<div class="summary"><span>${label}</span><strong>${value}</strong></div>`).join("");

  $("#receipt-list").innerHTML = state.receipts.length ? state.receipts.map((receipt) => `
    <button class="receipt-row" data-open-receipt="${receipt.id}">
      <strong>${escapeHtml(merchantName(receipt.merchant_id))}</strong>
      <span class="receipt-date muted">${formatDate(receipt.purchase_date)}</span>
      <span class="receipt-amount">${money(receipt.stated_total, receipt.currency)}</span>
      <span class="status ${receipt.status}">${receipt.status}</span>
    </button>`).join("") : `<div class="empty">No receipts yet. Create your first one above.</div>`;
}

async function openReceipt(id) {
  $("#receipt-index").hidden = true;
  $("#receipt-detail").hidden = false;
  $("#receipt-detail").setAttribute("aria-busy", "true");
  try {
    [state.receipt, state.items, state.payments, state.reconciliation, state.events] = await Promise.all([
      api(`/receipts/${id}`), api(`/receipts/${id}/items`), api(`/receipts/${id}/payments`),
      api(`/receipts/${id}/reconciliation`), api(`/receipts/${id}/audit-events`),
    ]);
    renderReceiptDetail();
    location.hash = `receipt/${id}`;
  } catch (error) {
    notify(error.message, true);
    closeReceipt();
  } finally {
    $("#receipt-detail").removeAttribute("aria-busy");
  }
}

function closeReceipt() {
  state.receipt = null;
  $("#receipt-detail").hidden = true;
  $("#receipt-index").hidden = false;
  history.replaceState(null, "", location.pathname);
  loadReceipts().catch((error) => notify(error.message, true));
}

function renderReceiptDetail() {
  const receipt = state.receipt;
  const editable = receipt.status === "draft";
  $("#detail-merchant").textContent = merchantName(receipt.merchant_id);
  $("#detail-title").textContent = `${formatDate(receipt.purchase_date)} · ${money(receipt.stated_total, receipt.currency)}`;
  $("#detail-status").textContent = receipt.status;
  $("#detail-status").className = `status ${receipt.status}`;
  const form = $("#receipt-edit-form");
  form.elements.merchant_id.value = receipt.merchant_id || "";
  form.elements.purchase_date.value = receipt.purchase_date;
  form.elements.stated_total.value = receipt.stated_total;
  form.elements.currency.value = receipt.currency;
  form.elements.notes.value = receipt.notes || "";
  [...form.elements].forEach((element) => { element.disabled = !editable; });
  $("#item-form").hidden = !editable;
  $("#payment-form").hidden = !editable;
  $("#approve-receipt").hidden = !editable;
  $("#void-receipt").hidden = receipt.status === "voided";
  renderReconciliation();
  renderItems();
  renderPayments();
  renderAudit();
}

function renderReconciliation() {
  const data = state.reconciliation;
  $("#reconcile-badge").textContent = data.is_reconciled ? "Balanced" : "Needs attention";
  $("#reconcile-badge").className = `status ${data.is_reconciled ? "ok" : "bad"}`;
  $("#reconciliation").innerHTML = [
    ["Receipt total", money(data.stated_total, state.receipt.currency)],
    ["Items", money(data.item_total, state.receipt.currency)],
    ["Payments", money(data.payment_total, state.receipt.currency)],
    ["Difference", money(Math.abs(Number(data.payment_difference)), state.receipt.currency)],
  ].map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join("");
  $("#approve-receipt").disabled = !data.is_reconciled;
}

function renderItems() {
  $("#item-count").textContent = `${state.items.length} line${state.items.length === 1 ? "" : "s"}`;
  $("#item-list").innerHTML = state.items.length ? state.items.map((item) => `
    <div class="line-item"><div class="line-copy"><strong>${escapeHtml(item.description)}</strong><small>${titleCase(item.line_type)} · ${money(item.line_total, state.receipt.currency)}</small></div>
    ${state.receipt.status === "draft" ? `<div class="line-actions"><button class="icon-button" data-edit-item="${item.id}">Edit</button><button class="icon-button delete" data-delete-item="${item.id}">Delete</button></div>` : ""}</div>`).join("") : `<p class="muted">No items added.</p>`;
}

function renderPayments() {
  $("#payment-count").textContent = `${state.payments.length} payment${state.payments.length === 1 ? "" : "s"}`;
  $("#payment-list").innerHTML = state.payments.length ? state.payments.map((payment) => `
    <div class="line-item"><div class="line-copy"><strong>${escapeHtml(methodName(payment.payment_method_id))}</strong><small>${money(payment.amount, state.receipt.currency)}</small></div>
    ${state.receipt.status === "draft" ? `<div class="line-actions"><button class="icon-button" data-edit-payment="${payment.id}">Edit</button><button class="icon-button delete" data-delete-payment="${payment.id}">Delete</button></div>` : ""}</div>`).join("") : `<p class="muted">No payments added.</p>`;
}

function renderAudit() {
  $("#audit-list").innerHTML = state.events.length ? [...state.events].reverse().map((event) => `
    <div class="timeline-item"><span class="timeline-dot"></span><div><strong>${titleCase(event.event_type)}</strong><small class="muted">${formatTime(event.created_at)}</small><code>${escapeHtml(JSON.stringify(event.event_data))}</code></div></div>`).join("") : `<p class="muted">No history recorded.</p>`;
}

async function refreshReceipt() {
  await openReceipt(state.receipt.id);
  await loadReceipts();
}

function renderSettings() {
  $("#merchant-list").innerHTML = state.merchants.length ? state.merchants.map((merchant) => `<div class="setting-item"><strong>${escapeHtml(merchant.name)}</strong><small class="muted">${formatTime(merchant.created_at)}</small></div>`).join("") : `<p class="muted">No merchants yet.</p>`;
  $("#method-list").innerHTML = state.methods.length ? state.methods.map((method) => `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(methodName(method.id))}</strong><small>${titleCase(method.method_type)}${method.provider ? ` · ${escapeHtml(method.provider)}` : ""}${method.is_active ? "" : " · Inactive"}</small></div>${method.is_active ? `<button class="icon-button delete" data-deactivate-method="${method.id}">Deactivate</button>` : ""}</div>`).join("") : `<p class="muted">No payment methods yet.</p>`;
}

function resetItemForm() {
  const form = $("#item-form"); form.reset(); form.elements.edit_id.value = "";
  form.querySelector("button[type=submit]").textContent = "Add item";
  $("[data-cancel-item]").hidden = true;
}

function resetPaymentForm() {
  const form = $("#payment-form"); form.reset(); form.elements.edit_id.value = "";
  form.querySelector("button[type=submit]").textContent = "Add payment";
  $("[data-cancel-payment]").hidden = true;
}

function bindEvents() {
  $$(".nav-button").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $("#show-create-receipt").addEventListener("click", () => { $("#receipt-create-form").hidden = false; $("#receipt-create-form input[name=purchase_date]").value = today(); });
  $("[data-cancel-create]").addEventListener("click", () => { $("#receipt-create-form").hidden = true; });
  $("#back-to-receipts").addEventListener("click", closeReceipt);

  $("#receipt-list").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-receipt]");
    if (target) openReceipt(target.dataset.openReceipt);
  });

  $("#receipt-create-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const receipt = await run(() => api("/receipts", { method: "POST", body: JSON.stringify({ merchant_id: data.get("merchant_id") || null, purchase_date: data.get("purchase_date"), stated_total: data.get("stated_total"), currency: String(data.get("currency")).toUpperCase(), notes: data.get("notes") || null }) }), "Receipt created").catch(() => null);
    if (receipt) { form.reset(); form.hidden = true; await loadReceipts(); await openReceipt(receipt.id); }
  });

  $("#receipt-edit-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const receipt = await run(() => api(`/receipts/${state.receipt.id}`, { method: "PATCH", body: JSON.stringify({ merchant_id: data.get("merchant_id") || null, purchase_date: data.get("purchase_date"), stated_total: data.get("stated_total"), currency: String(data.get("currency")).toUpperCase(), notes: data.get("notes") || null }) }), "Receipt updated").catch(() => null);
    if (receipt) await refreshReceipt();
  });

  $("#item-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const editId = data.get("edit_id");
    const payload = { description: data.get("description"), line_type: data.get("line_type"), line_total: data.get("line_total") };
    if (!editId) payload.position = Math.max(0, ...state.items.map((item) => item.position)) + 1;
    const path = editId ? `/receipts/${state.receipt.id}/items/${editId}` : `/receipts/${state.receipt.id}/items`;
    const result = await run(() => api(path, { method: editId ? "PATCH" : "POST", body: JSON.stringify(payload) }), editId ? "Item updated" : "Item added").catch(() => null);
    if (result) { resetItemForm(); await refreshReceipt(); }
  });
  $("[data-cancel-item]").addEventListener("click", resetItemForm);

  $("#item-list").addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-item]"); const remove = event.target.closest("[data-delete-item]");
    if (edit) { const item = state.items.find((entry) => entry.id === edit.dataset.editItem); const form = $("#item-form"); form.elements.edit_id.value = item.id; form.elements.description.value = item.description; form.elements.line_type.value = item.line_type; form.elements.line_total.value = item.line_total; form.querySelector("button[type=submit]").textContent = "Save item"; $("[data-cancel-item]").hidden = false; form.scrollIntoView({ behavior: "smooth", block: "center" }); }
    if (remove && confirm("Delete this item?")) { const result = await run(() => api(`/receipts/${state.receipt.id}/items/${remove.dataset.deleteItem}`, { method: "DELETE" }), "Item deleted").catch(() => false); if (result !== false) await refreshReceipt(); }
  });

  $("#payment-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const editId = data.get("edit_id");
    const path = editId ? `/receipts/${state.receipt.id}/payments/${editId}` : `/receipts/${state.receipt.id}/payments`;
    const result = await run(() => api(path, { method: editId ? "PATCH" : "POST", body: JSON.stringify({ payment_method_id: data.get("payment_method_id"), amount: data.get("amount") }) }), editId ? "Payment updated" : "Payment added").catch(() => null);
    if (result) { resetPaymentForm(); await refreshReceipt(); }
  });
  $("[data-cancel-payment]").addEventListener("click", resetPaymentForm);

  $("#payment-list").addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-payment]"); const remove = event.target.closest("[data-delete-payment]");
    if (edit) { const payment = state.payments.find((entry) => entry.id === edit.dataset.editPayment); const form = $("#payment-form"); form.elements.edit_id.value = payment.id; form.elements.payment_method_id.value = payment.payment_method_id; form.elements.amount.value = payment.amount; form.querySelector("button[type=submit]").textContent = "Save payment"; $("[data-cancel-payment]").hidden = false; form.scrollIntoView({ behavior: "smooth", block: "center" }); }
    if (remove && confirm("Delete this payment?")) { const result = await run(() => api(`/receipts/${state.receipt.id}/payments/${remove.dataset.deletePayment}`, { method: "DELETE" }), "Payment deleted").catch(() => false); if (result !== false) await refreshReceipt(); }
  });

  $("#approve-receipt").addEventListener("click", async () => { if (confirm("Approve this receipt? It can no longer be edited.")) { const result = await run(() => api(`/receipts/${state.receipt.id}/approve`, { method: "POST" }), "Receipt approved").catch(() => null); if (result) await refreshReceipt(); } });
  $("#void-receipt").addEventListener("click", async () => { const reason = prompt("Why is this receipt being voided? (optional)"); if (reason !== null) { const result = await run(() => api(`/receipts/${state.receipt.id}/void`, { method: "POST", body: JSON.stringify({ reason: reason || null }) }), "Receipt voided").catch(() => null); if (result) await refreshReceipt(); } });

  $("#merchant-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const name = new FormData(form).get("name"); const result = await run(() => api("/merchants", { method: "POST", body: JSON.stringify({ name }) }), "Merchant added").catch(() => null); if (result) { form.reset(); await loadSetup(); await loadReceipts(); } });
  $("#method-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const result = await run(() => api("/payment-methods", { method: "POST", body: JSON.stringify({ name: data.get("name"), method_type: data.get("method_type"), provider: data.get("provider") || null, last_four: data.get("last_four") || null }) }), "Payment method added").catch(() => null); if (result) { form.reset(); await loadSetup(); } });
  $("#method-list").addEventListener("click", async (event) => { const target = event.target.closest("[data-deactivate-method]"); if (target && confirm("Deactivate this payment method? Existing receipt payments stay unchanged.")) { const result = await run(() => api(`/payment-methods/${target.dataset.deactivateMethod}/deactivate`, { method: "POST" }), "Payment method deactivated").catch(() => null); if (result) await loadSetup(); } });
}

async function init() {
  bindEvents();
  $("#receipt-create-form input[name=purchase_date]").value = today();
  try {
    await loadSetup();
    await loadReceipts();
    const match = location.hash.match(/^#receipt\/([0-9a-f-]+)$/i);
    if (match) await openReceipt(match[1]);
  } catch (error) {
    notify(`Cannot connect to the API: ${error.message}`, true);
  }
}

init();
