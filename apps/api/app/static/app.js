"use strict";

const state = {
  receipts: [],
  incomes: [],
  merchants: [],
  methods: [],
  receipt: null,
  items: [],
  payments: [],
  reconciliation: null,
  events: [],
  user: null,
  members: [],
  invitations: [],
  invitationToken: null,
  invitationExistingAccount: false,
  households: [],
  currentHousehold: null,
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
    const error = new Error(message);
    error.status = response.status;
    if (response.status === 401 && path !== "/auth/login") {
      showLogin("Your session has expired. Please sign in again.");
    }
    throw error;
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

function showLogin(message = "") {
  state.user = null;
  $("#app-shell").hidden = true;
  $("#invitation-view").hidden = true;
  $("#login-view").hidden = false;
  const error = $("#login-error");
  error.textContent = message;
  error.hidden = !message;
}

function showApp(user) {
  state.user = user;
  $("#login-view").hidden = true;
  $("#invitation-view").hidden = true;
  $("#app-shell").hidden = false;
  $("#login-error").hidden = true;
}

async function showInvitation(token) {
  state.invitationToken = token;
  state.invitationExistingAccount = false;
  $("#login-view").hidden = true;
  $("#app-shell").hidden = true;
  $("#invitation-view").hidden = false;
  $("#invitation-accept-form").hidden = true;
  $("#invitation-existing-form").hidden = true;
  $("#invitation-error").hidden = true;
  $("#invitation-summary").textContent = "Checking invitation…";
  try {
    const preview = await api("/invitations/preview", { method: "POST", body: JSON.stringify({ token }) });
    $("#invitation-summary").textContent = `${preview.email} was invited to join ${preview.household_name} as ${titleCase(preview.role)}.`;
    state.invitationExistingAccount = preview.existing_account;
    if (preview.existing_account) {
      const form = $("#invitation-existing-form");
      form.elements.email.value = preview.email;
      form.hidden = false;
    } else {
      $("#invitation-accept-form").hidden = false;
    }
  } catch (error) {
    $("#invitation-summary").textContent = "This invitation cannot be used.";
    $("#invitation-error").textContent = error.message;
    $("#invitation-error").hidden = false;
  }
}

function clearHouseholdData() {
  state.receipts = [];
  state.incomes = [];
  state.merchants = [];
  state.methods = [];
  state.receipt = null;
  state.items = [];
  state.payments = [];
  state.reconciliation = null;
  state.events = [];
  state.members = [];
  state.invitations = [];
  state.currentHousehold = null;
}

async function loadHouseholds() {
  state.households = await api("/auth/households");
  const selector = $("#household-selector");
  selector.innerHTML = state.households.map((household) => `<option value="${household.household_id}">${escapeHtml(household.name)} · ${titleCase(household.role)}</option>`).join("");
  selector.value = state.user.household_id;
  const active = state.households.find((household) => household.household_id === state.user.household_id);
  $("#active-household-name").textContent = active?.name || "Household";
  selector.disabled = state.households.length < 2;
}

async function activateHousehold(householdId) {
  const user = await api(`/auth/switch-household/${householdId}`, { method: "POST" });
  clearHouseholdData();
  history.replaceState(null, "", location.pathname);
  showApp(user);
  switchView("receipts");
  await loadAuthenticatedData();
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

function memberName(id) {
  return state.members.find((member) => member.user_id === id)?.display_name || "Former member";
}

function activeCurrency() {
  return state.households.find((household) => household.is_active)?.default_currency || "EUR";
}

function switchView(name) {
  $$(".view").forEach((view) => { view.hidden = view.id !== `${name}-view`; });
  $$(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  if (name === "settings") renderSettings();
  if (name === "income") renderIncome();
  if (name === "members") loadMembers().catch((error) => notify(error.message, true));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadMembers() {
  [state.currentHousehold, state.members] = await Promise.all([
    api("/household"),
    api("/household/members"),
  ]);
  const canAdminister = ["owner", "admin"].includes(state.user?.role);
  $("#invitation-admin-card").hidden = !canAdminister;
  state.invitations = canAdminister ? await api("/household/invitations") : [];
  renderMembers();
}

function renderMembers() {
  const canAdminister = ["owner", "admin"].includes(state.user?.role);
  const isOwner = state.user?.role === "owner";
  $("#member-count").textContent = `${state.members.length} member${state.members.length === 1 ? "" : "s"}`;
  $("#member-list").innerHTML = state.members.map((member) => {
    const isSelf = member.user_id === state.user.user_id;
    const canChange = canAdminister && (isOwner || (member.role !== "owner" && !isSelf));
    const canRemove = canAdminister && !isSelf && (isOwner || member.role !== "owner");
    const roleOptions = (isOwner ? ["owner", "admin", "member"] : ["admin", "member"]).map((role) => `<option value="${role}"${role === member.role ? " selected" : ""}>${titleCase(role)}</option>`).join("");
    return `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(member.display_name)}${isSelf ? " (you)" : ""}</strong><small>${escapeHtml(member.email || "No email")} · joined ${formatTime(member.joined_at)}</small></div><div class="member-actions">${canChange ? `<select data-member-role="${member.user_id}" aria-label="Role for ${escapeHtml(member.display_name)}">${roleOptions}</select>` : `<span class="status">${titleCase(member.role)}</span>`}${canRemove ? `<button class="icon-button delete" data-remove-member="${member.user_id}">Remove</button>` : ""}</div></div>`;
  }).join("") || `<p class="muted">No members found.</p>`;
  $("#pending-invitation-list").innerHTML = state.invitations.map((invitation) => `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(invitation.email)}</strong><small>${titleCase(invitation.role)} · expires ${formatTime(invitation.expires_at)}</small></div><button class="icon-button delete" data-cancel-invitation="${invitation.id}">Cancel</button></div>`).join("") || `<p class="muted">No pending invitations.</p>`;
  $("#household-settings-card").hidden = !canAdminister;
  const form = $("#household-settings-form");
  form.elements.name.value = state.currentHousehold.name;
  form.elements.default_currency.value = state.currentHousehold.default_currency;
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
    const placeholder = select.name === "destination_payment_method_id" ? "Not specified" : "Choose method";
    select.innerHTML = `<option value="">${placeholder}</option>${state.methods.filter((method) => method.is_active).map((method) => `<option value="${method.id}">${escapeHtml(methodName(method.id))}</option>`).join("")}`;
    select.value = selected;
  });
}

async function loadIncomes() {
  state.incomes = await api("/income?limit=100");
  renderIncome();
}

async function loadReceipts() {
  state.receipts = await api("/receipts?limit=100");
  renderReceiptIndex();
}

function renderReceiptIndex() {
  const drafts = state.receipts.filter((receipt) => receipt.status === "draft").length;
  const approved = state.receipts.filter((receipt) => receipt.status === "approved");
  const approvedTotal = approved.filter((receipt) => receipt.currency === "EUR").reduce((total, receipt) => total + Number(receipt.stated_total), 0);
  const incomeTotal = state.incomes.filter((entry) => entry.currency === "EUR").reduce((total, entry) => total + Number(entry.amount), 0);
  $("#receipt-summary").innerHTML = [
    ["Income (EUR)", money(incomeTotal)],
    ["Approved expenses (EUR)", money(approvedTotal)],
    ["Balance (EUR)", money(incomeTotal - approvedTotal)],
    ["Drafts", drafts],
  ].map(([label, value]) => `<div class="summary"><span>${label}</span><strong>${value}</strong></div>`).join("");

  $("#receipt-list").innerHTML = state.receipts.length ? state.receipts.map((receipt) => `
    <button class="receipt-row" data-open-receipt="${receipt.id}">
      <span class="line-copy"><strong>${escapeHtml(merchantName(receipt.merchant_id))}</strong><small>Created by ${escapeHtml(receipt.created_by_display_name || memberName(receipt.created_by_user_id))}</small></span>
      <span class="receipt-date muted">${formatDate(receipt.purchase_date)}</span>
      <span class="receipt-amount">${money(receipt.stated_total, receipt.currency)}</span>
      <span class="status ${receipt.status}">${receipt.status}</span>
    </button>`).join("") : `<div class="empty">No receipts yet. Create your first one above.</div>`;
}

function renderIncome() {
  const total = state.incomes.filter((entry) => entry.currency === "EUR").reduce((sum, entry) => sum + Number(entry.amount), 0);
  $("#income-total").textContent = `${money(total)} total`;
  $("#income-list").innerHTML = state.incomes.length ? state.incomes.map((entry) => `
    <div class="receipt-row">
      <span class="line-copy"><strong>${escapeHtml(entry.source)}</strong><small>${titleCase(entry.income_type)} · received by ${escapeHtml(entry.received_by_display_name || memberName(entry.received_by_user_id))}${entry.destination_payment_method_id ? ` · ${escapeHtml(methodName(entry.destination_payment_method_id))}` : ""}</small></span>
      <span class="receipt-date muted">${formatDate(entry.received_date)}</span>
      <span class="receipt-amount">${money(entry.amount, entry.currency)}</span>
      <span class="line-actions"><button class="icon-button" data-edit-income="${entry.id}">Edit</button><button class="icon-button delete" data-delete-income="${entry.id}">Delete</button></span>
    </div>`).join("") : `<div class="empty">No income recorded yet.</div>`;
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
  $("#detail-title").textContent = `${formatDate(receipt.purchase_date)} · ${money(receipt.stated_total, receipt.currency)} · created by ${receipt.created_by_display_name || memberName(receipt.created_by_user_id)}`;
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
    <div class="line-item"><div class="line-copy"><strong>${escapeHtml(payment.payment_method_name || methodName(payment.payment_method_id))}${payment.payment_method_last_four ? ` •••• ${payment.payment_method_last_four}` : ""}</strong><small>${money(payment.amount, state.receipt.currency)} · paid by ${escapeHtml(payment.payer_display_name || memberName(payment.user_id))}</small></div>
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

function resetIncomeForm() {
  const form = $("#income-form");
  form.reset();
  form.elements.edit_id.value = "";
  form.elements.received_date.value = today();
  form.elements.currency.value = activeCurrency();
  $("#income-form-title").textContent = "Add income";
  form.querySelector("button[type=submit]").textContent = "Add income";
  $("[data-cancel-income]").hidden = true;
}

function bindEvents() {
  $("#invitation-back").addEventListener("click", () => { history.replaceState(null, "", location.pathname); showLogin(); });
  $("#invitation-accept-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    if (data.get("password") !== data.get("password_confirm")) { $("#invitation-error").textContent = "Passwords do not match"; $("#invitation-error").hidden = false; return; }
    const errorBox = $("#invitation-error"); const button = form.querySelector("button[type=submit]");
    errorBox.hidden = true; button.disabled = true;
    try {
      const result = await api("/invitations/accept", { method: "POST", body: JSON.stringify({ token: state.invitationToken, display_name: data.get("display_name"), password: data.get("password") }) });
      history.replaceState(null, "", location.pathname); form.reset(); showLogin(result.message); $("#login-form input[name=email]").value = result.email;
    } catch (error) {
      errorBox.textContent = error.message; errorBox.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
  $("#invitation-existing-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const errorBox = $("#invitation-error"); const button = form.querySelector("button[type=submit]");
    errorBox.hidden = true; button.disabled = true;
    try {
      await api("/auth/login", { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) });
      const accepted = await api("/invitations/accept-existing", { method: "POST", body: JSON.stringify({ token: state.invitationToken }) });
      form.reset();
      await activateHousehold(accepted.household_id);
      notify("Household joined");
    } catch (error) {
      errorBox.textContent = error.message; errorBox.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form); const button = form.querySelector("button[type=submit]");
    button.disabled = true; $("#login-error").hidden = true;
    try {
      const user = await api("/auth/login", { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) });
      form.reset(); showApp(user); await loadAuthenticatedData();
    } catch (error) {
      showLogin(error.message);
    } finally {
      button.disabled = false;
    }
  });
  $("#logout-button").addEventListener("click", async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => null);
    clearHouseholdData(); state.households = [];
    showLogin("You have signed out.");
  });
  $("#household-selector").addEventListener("change", async (event) => {
    const selector = event.currentTarget; selector.disabled = true;
    try {
      await activateHousehold(selector.value);
      notify("Household switched");
    } catch (error) {
      selector.value = state.user.household_id;
      notify(error.message, true);
    } finally {
      selector.disabled = state.households.length < 2;
    }
  });
  $("#create-household-button").addEventListener("click", async () => {
    const name = prompt("Name for the new household:");
    if (!name?.trim()) return;
    const active = state.households.find((household) => household.is_active);
    const created = await run(
      () => api("/auth/households", { method: "POST", body: JSON.stringify({ name: name.trim(), default_currency: active?.default_currency || "EUR" }) }),
      "Household created",
    ).catch(() => null);
    if (created) await activateHousehold(created.household_id);
  });
  $$(".nav-button[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  $("#show-create-receipt").addEventListener("click", () => { $("#receipt-create-form").hidden = false; $("#receipt-create-form input[name=purchase_date]").value = today(); $("#receipt-create-form input[name=currency]").value = activeCurrency(); });
  $("[data-cancel-create]").addEventListener("click", () => { $("#receipt-create-form").hidden = true; });
  $("#back-to-receipts").addEventListener("click", closeReceipt);
  $("[data-cancel-income]").addEventListener("click", resetIncomeForm);

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

  $("#invitation-create-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const result = await run(() => api("/household/invitations", { method: "POST", body: JSON.stringify({ email: data.get("email"), role: data.get("role") }) }), "Invitation created").catch(() => null);
    if (result) { const link = `${location.origin}${location.pathname}#invite/${result.invitation_token}`; $("#invitation-link").value = link; $("#invitation-link-box").hidden = false; form.reset(); await loadMembers(); }
  });
  $("#copy-invitation-link").addEventListener("click", async () => {
    const input = $("#invitation-link");
    try { await navigator.clipboard.writeText(input.value); }
    catch (_) { input.select(); document.execCommand("copy"); }
    notify("Invitation link copied");
  });
  $("#pending-invitation-list").addEventListener("click", async (event) => {
    const target = event.target.closest("[data-cancel-invitation]");
    if (target && confirm("Cancel this invitation?")) { const result = await run(() => api(`/household/invitations/${target.dataset.cancelInvitation}`, { method: "DELETE" }), "Invitation cancelled").catch(() => false); if (result !== false) await loadMembers(); }
  });
  $("#household-settings-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const updated = await run(
      () => api("/household", { method: "PATCH", body: JSON.stringify({ name: data.get("name"), default_currency: String(data.get("default_currency")).toUpperCase() }) }),
      "Household settings saved",
    ).catch(() => null);
    if (updated) {
      state.currentHousehold = updated;
      await loadHouseholds();
      renderMembers();
    }
  });
  $("#member-list").addEventListener("change", async (event) => {
    const selector = event.target.closest("[data-member-role]");
    if (!selector) return;
    selector.disabled = true;
    const updated = await run(
      () => api(`/household/members/${selector.dataset.memberRole}`, { method: "PATCH", body: JSON.stringify({ role: selector.value }) }),
      "Member role updated",
    ).catch(() => null);
    if (updated) {
      if (updated.user_id === state.user.user_id) state.user = await api("/auth/me");
      await loadHouseholds();
      await loadMembers();
    } else {
      await loadMembers();
    }
  });
  $("#member-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-remove-member]");
    if (!button || !confirm("Remove this person from the household? Their historical records will be kept.")) return;
    const removed = await run(
      () => api(`/household/members/${button.dataset.removeMember}`, { method: "DELETE" }),
      "Member removed",
    ).catch(() => false);
    if (removed !== false) await loadMembers();
  });
  $("#leave-household-button").addEventListener("click", async () => {
    if (!confirm("Leave this household? You will need another invitation to rejoin.")) return;
    const left = await run(
      () => api("/household/leave", { method: "POST" }),
      null,
    ).catch(() => false);
    if (left !== false) {
      clearHouseholdData(); state.households = [];
      showLogin("You left the household. Sign in to access your other households.");
    }
  });

  $("#income-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const editId = data.get("edit_id");
    const payload = { source: data.get("source"), income_type: data.get("income_type"), received_date: data.get("received_date"), amount: data.get("amount"), currency: String(data.get("currency")).toUpperCase(), destination_payment_method_id: data.get("destination_payment_method_id") || null, notes: data.get("notes") || null };
    const result = await run(() => api(editId ? `/income/${editId}` : "/income", { method: editId ? "PATCH" : "POST", body: JSON.stringify(payload) }), editId ? "Income updated" : "Income added").catch(() => null);
    if (result) { resetIncomeForm(); await loadIncomes(); renderReceiptIndex(); }
  });

  $("#income-list").addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-income]"); const remove = event.target.closest("[data-delete-income]");
    if (edit) { const entry = state.incomes.find((item) => item.id === edit.dataset.editIncome); const form = $("#income-form"); form.elements.edit_id.value = entry.id; form.elements.source.value = entry.source; form.elements.income_type.value = entry.income_type; form.elements.received_date.value = entry.received_date; form.elements.amount.value = entry.amount; form.elements.currency.value = entry.currency; form.elements.destination_payment_method_id.value = entry.destination_payment_method_id || ""; form.elements.notes.value = entry.notes || ""; $("#income-form-title").textContent = "Edit income"; form.querySelector("button[type=submit]").textContent = "Save income"; $("[data-cancel-income]").hidden = false; form.scrollIntoView({ behavior: "smooth", block: "start" }); }
    if (remove && confirm("Delete this income entry?")) { const result = await run(() => api(`/income/${remove.dataset.deleteIncome}`, { method: "DELETE" }), "Income deleted").catch(() => false); if (result !== false) { await loadIncomes(); renderReceiptIndex(); } }
  });
}

async function loadAuthenticatedData() {
  $("#receipt-create-form input[name=purchase_date]").value = today();
  $("#income-form input[name=received_date]").value = today();
  await loadHouseholds();
  $("#receipt-create-form input[name=currency]").value = activeCurrency();
  $("#income-form input[name=currency]").value = activeCurrency();
  state.members = await api("/household/members");
  await loadSetup();
  await loadIncomes();
  await loadReceipts();
  const match = location.hash.match(/^#receipt\/([0-9a-f-]+)$/i);
  if (match) await openReceipt(match[1]);
}

async function init() {
  bindEvents();
  const invitationMatch = location.hash.match(/^#invite\/([A-Za-z0-9_-]+)$/);
  if (invitationMatch) { await showInvitation(invitationMatch[1]); return; }
  try {
    const user = await api("/auth/me");
    showApp(user);
    await loadAuthenticatedData();
  } catch (error) {
    if (error.status === 401) showLogin();
    else showLogin(`Cannot connect to the API: ${error.message}`);
  }
}

init();
