"use strict";

const state = {
  receipts: [],
  recurring: [],
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
  capture: null,
  uploadPolicy: null,
  maintenance: null,
  dashboard: null,
};

const canAdministerHousehold = () =>
  state.user?.role === "owner" || Boolean(state.user?.is_global_admin);

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const today = () => new Date().toISOString().slice(0, 10);
const money = (value, currency = "EUR") => new Intl.NumberFormat("en-DE", { style: "currency", currency }).format(Number(value));
const formatDate = (value) => new Intl.DateTimeFormat("en-DE", { dateStyle: "medium" }).format(new Date(`${value}T00:00:00`));
const formatTime = (value) => new Intl.DateTimeFormat("en-DE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
const titleCase = (value) => String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const expenseCategories = ["groceries", "rent", "health_insurance", "transport", "university_fees", "utilities", "subscriptions", "dining", "shopping", "travel", "other"];
const incomeCategories = ["salary_payslip", "freelance", "interest", "gift", "refund", "benefits", "other"];
let selectedReceiptImage = null;

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body && !isFormData ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  if (!response.ok) {
    let message = response.status === 413
      ? "The selected image is too large. Choose a smaller image or reduce its resolution."
      : `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      if (body.error_id) message = `${message} (error ID: ${body.error_id})`;
      if (body.detail && typeof body.detail === "object" && body.detail.message) message = `${body.detail.message}${body.detail.reason ? `: ${body.detail.reason}` : ""}`;
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

function readableBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".0", "")} MB`;
}

function captureFileError(file) {
  if (!file) return "Choose or take a receipt image first.";
  const policy = state.uploadPolicy;
  if (policy?.allowed_media_types && !policy.allowed_media_types.includes(file.type)) return "Unsupported file type. Choose a JPEG, PNG or WebP image.";
  if (policy?.max_bytes && file.size > policy.max_bytes) return `“${file.name}” is ${readableBytes(file.size)}. The maximum upload size is ${readableBytes(policy.max_bytes)}.`;
  return "";
}

function showCaptureUploadError(message = "") {
  const error = $("#capture-upload-error");
  error.textContent = message;
  error.hidden = !message;
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
  state.capture = null;
  state.dashboard = null;
}

function resetCaptureUi() {
  selectedReceiptImage = null;
  state.capture = null;
  const captureForm = $("#receipt-capture-form");
  captureForm.reset();
  captureForm.hidden = true;
  $("#capture-review").hidden = true;
  $("#capture-preview").hidden = true;
  $("#capture-preview").removeAttribute("src");
  $("#capture-merchant-hint").hidden = true;
  $("#capture-duplicate-warning").hidden = true;
  $("#open-duplicate-receipt").hidden = true;
  $("#use-capture").disabled = false;
  $("#receipt-create-form").elements.capture_id.value = "";
}

function renderCaptureReview() {
  const capture = state.capture;
  if (!capture) return;
  $("#receipt-capture-form").hidden = true;
  $("#capture-review").hidden = false;
  $("#capture-image").src = `${capture.image_url}?v=${encodeURIComponent(capture.updated_at)}`;
  $("#capture-status").textContent = capture.ocr_status === "succeeded" ? `Text read with ${titleCase(capture.ocr_provider || "OCR")}. Verify every value before saving.` : "OCR could not finish. You can retry or continue with manual values.";
  $("#capture-suggestions").innerHTML = [
    ["Merchant", capture.suggested_merchant_name || "Not detected"],
    ["Address", capture.suggested_merchant_address || "Not detected"],
    ["Date", capture.suggested_purchase_date || "Not detected"],
    ["Total", capture.suggested_total ? money(capture.suggested_total, capture.suggested_currency || activeCurrency()) : "Not detected"],
    ["Payment", capture.suggested_payment_reason || "Not detected"],
    ["Receipt number", capture.suggested_receipt_number || "Not detected"],
  ].map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  const error = $("#capture-error");
  error.textContent = capture.ocr_error || "";
  error.hidden = !capture.ocr_error;
  $("#capture-raw-text").textContent = capture.ocr_raw_text || "No text was returned.";
  $("#capture-raw-details").hidden = !capture.ocr_raw_text;
  const duplicateWarning = $("#capture-duplicate-warning");
  const strongDuplicate = capture.duplicate_match_level === "strong";
  duplicateWarning.textContent = capture.duplicate_reason ? `${strongDuplicate ? "Duplicate detected" : "Possible duplicate"}: ${capture.duplicate_reason}` : "";
  duplicateWarning.hidden = !capture.duplicate_reason;
  $("#open-duplicate-receipt").hidden = !capture.possible_duplicate_receipt_id;
  $("#use-capture").disabled = strongDuplicate;
  $("#use-capture").textContent = strongDuplicate ? "Duplicate receipt blocked" : (capture.ocr_status === "succeeded" ? "Review and create draft" : "Enter values manually");
}

async function useCaptureSuggestions() {
  const capture = state.capture;
  if (!capture) return;
  const form = $("#receipt-create-form");
  form.hidden = false;
  form.elements.capture_id.value = capture.id;
  form.elements.purchase_date.value = capture.suggested_purchase_date || today();
  form.elements.stated_total.value = capture.suggested_total || "";
  form.elements.currency.value = capture.suggested_currency || activeCurrency();
  form.elements.payment_method_id.value = capture.suggested_payment_method_id || "";
  form.elements.receipt_number.value = capture.suggested_receipt_number || "";
  const ocrWords = `${capture.suggested_merchant_name || ""} ${capture.ocr_raw_text || ""}`.toLocaleLowerCase();
  form.elements.category.value = /aldi|lidl|rewe|edeka|penny|netto|kaufland|supermarkt|grocery/.test(ocrWords) ? "groceries" : "other";
  const normalizedMerchant = String(capture.suggested_merchant_name || "").trim().toLocaleLowerCase();
  const normalizedAddress = String(capture.suggested_merchant_address || "").trim().replace(/\s+/g, " ").toLocaleLowerCase();
  let merchant = state.merchants.find((entry) => entry.normalized_name === normalizedMerchant && entry.normalized_address === normalizedAddress);
  if (!merchant && capture.suggested_merchant_name) {
    merchant = await api("/merchants", {
      method: "POST",
      body: JSON.stringify({
        name: capture.suggested_merchant_name,
        address: capture.suggested_merchant_address || null,
      }),
    }).catch(async (error) => {
      if (error.status !== 409) throw error;
      state.merchants = await api("/merchants");
      return state.merchants.find((entry) => entry.normalized_name === normalizedMerchant && entry.normalized_address === normalizedAddress) || null;
    });
    if (merchant) {
      state.merchants = [merchant, ...state.merchants.filter((entry) => entry.id !== merchant.id)];
      state.merchants.sort((a, b) => String(a.normalized_name).localeCompare(String(b.normalized_name)));
    }
  }
  // Rebuild the options after an OCR merchant is created or reloaded. Assigning
  // select.value before its option exists leaves the dropdown unselected.
  renderSelects();
  form.elements.merchant_id.value = merchant?.id || "";
  const hint = $("#capture-merchant-hint");
  hint.textContent = capture.suggested_merchant_name && merchant
    ? `OCR read merchant “${capture.suggested_merchant_name}”. It was added to your household and preselected for this draft.`
    : capture.suggested_merchant_name
      ? `OCR read merchant “${capture.suggested_merchant_name}”. Select an existing merchant or add it under Settings.`
      : "This draft will retain the captured image and OCR evidence.";
  hint.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
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
  switchView("dashboard");
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
  if (name === "settings") {
    renderSettings();
    loadMaintenance().catch((error) => notify(error.message, true));
  }
  if (name === "income") renderIncome();
  if (name === "members") loadMembers().catch((error) => notify(error.message, true));
  if (name === "dashboard") loadDashboard().catch((error) => notify(error.message, true));
  if (name === "products") window.productIntelligence.load().catch((error) => notify(error.message, true));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadMaintenance() {
  const canAdminister = canAdministerHousehold();
  const card = $("#maintenance-card");
  card.hidden = !canAdminister;
  if (!canAdminister) return;
  state.maintenance = await api("/maintenance/preview");
  const counts = state.maintenance.counts;
  $("#maintenance-counts").innerHTML = [
    ["Receipts", counts.receipts],
    ["Receipt items", counts.receipt_items],
    ["Payments", counts.receipt_payments],
    ["Receipt images / OCR captures", counts.receipt_captures],
    ["Income entries", counts.income_entries],
    ["Audit events", counts.audit_events],
  ].map(([label, count]) => `<div class="setting-item"><span>${label}</span><strong>${count}</strong></div>`).join("");
  $("#reset-confirmation-phrase").textContent = state.maintenance.confirmation_phrase;
}

async function loadMembers() {
  [state.currentHousehold, state.members] = await Promise.all([
    api("/household"),
    api("/household/members"),
  ]);
  const canAdminister = canAdministerHousehold();
  $("#invitation-admin-card").hidden = !canAdminister;
  state.invitations = canAdminister ? await api("/household/invitations") : [];
  renderMembers();
}

function renderMembers() {
  const canAdminister = canAdministerHousehold();
  const isOwner = canAdministerHousehold();
  $("#member-count").textContent = `${state.members.length} member${state.members.length === 1 ? "" : "s"}`;
  $("#member-list").innerHTML = state.members.map((member) => {
    const isSelf = member.user_id === state.user.user_id;
    const canChange = canAdminister && (isOwner || (member.role !== "owner" && !isSelf));
    const canRemove = canAdminister && !isSelf && (isOwner || member.role !== "owner");
    const canResetPassword = state.user?.is_global_admin && !isSelf;
    const roleOptions = ["owner", "member"].map((role) => `<option value="${role}"${role === member.role ? " selected" : ""}>${titleCase(role)}</option>`).join("");
    return `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(member.display_name)}${isSelf ? " (you)" : ""}</strong><small>${escapeHtml(member.email || "No email")} · joined ${formatTime(member.joined_at)}</small></div><div class="member-actions">${canChange ? `<select data-member-role="${member.user_id}" aria-label="Role for ${escapeHtml(member.display_name)}">${roleOptions}</select>` : `<span class="status">${titleCase(member.role)}</span>`}${canResetPassword ? `<button class="icon-button" data-reset-password="${member.user_id}" data-member-name="${escapeHtml(member.display_name)}">Reset password</button>` : ""}${canRemove ? `<button class="icon-button delete" data-remove-member="${member.user_id}">Remove</button>` : ""}</div></div>`;
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
  $("#diagnostics-card").hidden = !canAdministerHousehold();
  if (canAdministerHousehold()) await loadDiagnostics();
}

async function loadDiagnostics() {
  const data = await api("/diagnostics/errors");
  $("#diagnostics-list").innerHTML = data.entries.map((entry) => `
    <details class="diagnostic-entry ${entry.level}">
      <summary><strong>${escapeHtml(entry.level.toUpperCase())} ${entry.status_code}</strong> <code>${escapeHtml(entry.id)}</code> · ${escapeHtml(entry.method || "APP")} ${escapeHtml(entry.path || "")} <small>${escapeHtml(formatTime(entry.timestamp))}</small></summary>
      <p>${escapeHtml(entry.message)}</p>
      ${entry.traceback ? `<pre>${escapeHtml(entry.traceback)}</pre>` : ""}
    </details>`).join("") || `<p class="muted">No warnings or errors have been recorded since this app instance started.</p>`;
}

function renderSelects() {
  $$('[data-expense-category]').forEach((select) => {
    const selected = select.value || "other";
    select.innerHTML = expenseCategories.map((category) => `<option value="${category}">${titleCase(category)}</option>`).join("");
    select.value = selected;
  });
  $$('[data-income-category]').forEach((select) => {
    const selected = select.value || "salary_payslip";
    select.innerHTML = incomeCategories.map((category) => `<option value="${category}">${category === "salary_payslip" ? "Salary / Payslip" : titleCase(category)}</option>`).join("");
    select.value = selected;
  });
  $$('[data-merchant-select]').forEach((select) => {
    const selected = select.value;
    select.innerHTML = `<option value="">No merchant</option>${state.merchants.map((merchant) => `<option value="${merchant.id}">${escapeHtml(merchant.name)}${merchant.address ? ` — ${escapeHtml(merchant.address)}` : ""}</option>`).join("")}`;
    select.value = selected;
  });
  $$('[data-payment-select]').forEach((select) => {
    const selected = select.value;
    const placeholder = select.name === "destination_payment_method_id" ? "Not specified" : (select.closest("#receipt-create-form") ? "Add payment later" : "Choose method");
    const allowsHouseholdMethods = Boolean(select.closest("#receipt-create-form, #payment-form"));
    const methods = state.methods.filter((method) => method.is_active && (allowsHouseholdMethods || method.user_id === state.user.user_id));
    select.innerHTML = `<option value="">${placeholder}</option>${methods.map((method) => `<option value="${method.id}">${escapeHtml(methodName(method.id))}${allowsHouseholdMethods && canAdministerHousehold() ? ` — ${escapeHtml(memberName(method.user_id))}` : ""}</option>`).join("")}`;
    select.value = selected;
  });
}

async function loadIncomes() {
  state.incomes = await api("/income?limit=100");
  renderIncome();
}

async function loadReceipts() {
  await api("/recurring-expenses/generate-due", { method: "POST" });
  state.recurring = await api("/recurring-expenses");
  const query = $("#receipt-search-form")?.elements.q.value.trim() || "";
  state.receipts = await api(`/receipts?limit=100${query ? `&q=${encodeURIComponent(query)}` : ""}`);
  renderReceiptIndex();
  renderRecurring();
}

function renderRecurring() {
  $("#recurring-list").innerHTML = state.recurring.map((entry) => `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(entry.name)}</strong><small>${money(entry.amount, entry.currency)} · ${titleCase(entry.category)} · ${titleCase(entry.frequency)} · next ${formatDate(entry.next_occurrence_date)} · ${entry.is_active ? "active" : "paused"}</small></div><div class="member-actions"><button class="icon-button" data-edit-recurring="${entry.id}">Edit</button><button class="icon-button delete" data-delete-recurring="${entry.id}">Delete</button></div></div>`).join("") || `<p class="muted">No recurring expenses.</p>`;
}

function resetRecurringForm() {
  const form = $("#recurring-form"); form.reset(); form.elements.edit_id.value = ""; form.elements.currency.value = activeCurrency(); form.elements.next_occurrence_date.value = today(); form.elements.is_active.checked = true; $("[data-cancel-recurring]").hidden = true;
}

function dashboardPeriod() {
  const form = $("#dashboard-period-form");
  return { year: Number(form.elements.year.value), month: Number(form.elements.month.value) };
}

async function loadDashboard() {
  const { year, month } = dashboardPeriod();
  if (!year || !month) return;
  $("#dashboard-view").setAttribute("aria-busy", "true");
  try {
    state.dashboard = await api(`/dashboard?year=${year}&month=${month}`);
    renderDashboard();
  } finally {
    $("#dashboard-view").removeAttribute("aria-busy");
  }
}

function renderDashboard() {
  const data = state.dashboard;
  if (!data) return;
  const monthName = new Intl.DateTimeFormat("en", { month: "long" }).format(new Date(data.year, data.month - 1, 1));
  $("#dashboard-subtitle").textContent = `${monthName} ${data.year} · approved receipts · ${data.currency}`;
  const change = data.month_change_percentage === null ? "No prior-month baseline" : `${Number(data.month_change_percentage) >= 0 ? "↑" : "↓"} ${Math.abs(Number(data.month_change_percentage))}% vs previous month`;
  $("#dashboard-kpis").innerHTML = [
    ["Spent this month", money(data.month_expense, data.currency), `${data.receipt_count} approved receipt${data.receipt_count === 1 ? "" : "s"} · ${change}`, "accent"],
    ["Monthly balance", money(data.month_balance, data.currency), `${money(data.month_income, data.currency)} income`, ""],
    ["Spent this year", money(data.year_expense, data.currency), `January to ${monthName}`, ""],
    ["Average purchase", money(data.average_receipt, data.currency), `Largest ${money(data.largest_receipt, data.currency)}`, ""],
  ].map(([label, value, meta, className]) => `<article class="kpi-card ${className}"><span class="kpi-label">${label}</span><strong class="kpi-value">${value}</strong><span class="kpi-meta">${meta}</span></article>`).join("");
  const alerts = [];
  if (data.draft_count) alerts.push(`${data.draft_count} draft receipt${data.draft_count === 1 ? " is" : "s are"} awaiting approval and not included.`);
  if (data.excluded_currency_count) alerts.push(`${data.excluded_currency_count} approved receipt${data.excluded_currency_count === 1 ? " uses" : "s use"} another currency and is not combined.`);
  const leadingCategory = data.categories[0];
  const leadingMerchant = data.top_merchants_month[0];
  const leadingProduct = data.top_products[0];
  const insights = [
    leadingCategory ? `<span><strong>${titleCase(leadingCategory.category)}</strong> is your largest category at ${money(leadingCategory.amount, data.currency)}.</span>` : "",
    leadingMerchant ? `<span><strong>${escapeHtml(leadingMerchant.name)}</strong> is this month's top merchant.</span>` : "",
    leadingProduct ? `<span><strong>${escapeHtml(titleCase(leadingProduct.description))}</strong> is your most frequently purchased product.</span>` : "",
  ].filter(Boolean);
  $("#dashboard-alerts").innerHTML = `${alerts.length ? `<div class="dashboard-note">${alerts.map(escapeHtml).join(" ")}</div>` : ""}${insights.length ? `<div class="insight-strip">${insights.join("")}</div>` : ""}`;
  renderTrendChart(data);
  renderCategoryChart(data);
  renderMerchantChart();
  renderProducts(data);
  renderGroceryFamilies(data);
  renderSpendingPattern(data);
}

function renderGroceryFamilies(data) {
  $("#grocery-family-chart").innerHTML = data.grocery_families.length ? data.grocery_families.map((entry, index) => `<div class="rank-item"><span class="rank-number">${index + 1}</span><span class="rank-copy"><strong>${escapeHtml(entry.label)}</strong><small>${entry.percentage}% of categorized groceries</small></span><strong>${money(entry.amount, data.currency)}</strong></div>`).join("") : `<div class="chart-empty">Confirm product matches to build Milk, Pizza and other grocery families.</div>`;
}

function renderSpendingPattern(data) {
  const period = $("#spending-pattern-period").value;
  const points = period === "day" ? data.daily_spending : period === "week" ? data.weekly_spending : data.monthly_trend.map((item) => ({ label: item.label, amount: item.expense }));
  const maximum = Math.max(1, ...points.map((point) => Number(point.amount)));
  $("#spending-pattern-chart").innerHTML = points.map((point) => `<div class="pattern-column" title="${escapeHtml(point.label)}: ${money(point.amount, data.currency)}"><i style="height:${Math.max(1, Number(point.amount) / maximum * 100)}%"></i><small>${escapeHtml(point.label)}</small></div>`).join("");
}

function renderTrendChart(data) {
  const maximum = Math.max(1, ...data.monthly_trend.flatMap((point) => [Number(point.expense), Number(point.income)]));
  $("#spending-trend-chart").innerHTML = `<div class="trend-bars">${data.monthly_trend.map((point) => `<div class="trend-month"><div class="trend-pair"><i class="trend-bar income" style="height:${Math.max(1, Number(point.income) / maximum * 100)}%" title="${point.label} income: ${money(point.income, data.currency)}"></i><i class="trend-bar expense" style="height:${Math.max(1, Number(point.expense) / maximum * 100)}%" title="${point.label} expense: ${money(point.expense, data.currency)}"></i></div><small>${point.label}</small></div>`).join("")}</div>`;
}

function renderCategoryChart(data) {
  const colors = ["#1d5a40", "#4f8c68", "#76b38c", "#d89962", "#b77b43", "#6f7e75", "#a6b7aa", "#cabd79", "#8d6f9f", "#557f9c", "#c7d8cb"];
  if (!data.categories.length) {
    $("#category-chart").innerHTML = `<div class="chart-empty">No approved spending for this month.</div>`;
    return;
  }
  let position = 0;
  const segments = data.categories.map((entry, index) => {
    const start = position; position += Number(entry.percentage);
    return `${colors[index % colors.length]} ${start}% ${position}%`;
  }).join(",");
  $("#category-chart").innerHTML = `<div class="donut" style="background:conic-gradient(${segments})" aria-label="Spending category chart"></div><div class="category-legend">${data.categories.map((entry, index) => `<div class="category-row"><i style="background:${colors[index % colors.length]}"></i><span>${titleCase(entry.category)} <small class="muted">${entry.percentage}%</small></span><strong>${money(entry.amount, data.currency)}</strong></div>`).join("")}</div>`;
}

function renderMerchantChart() {
  const data = state.dashboard;
  if (!data) return;
  const period = $("#merchant-period").value;
  const merchants = period === "year" ? data.top_merchants_year : data.top_merchants_month;
  $("#top-merchants-chart").innerHTML = merchants.length ? merchants.map((merchant, index) => `<div class="rank-item"><span class="rank-number">${index + 1}</span><span class="rank-copy"><strong>${escapeHtml(merchant.name)}</strong><small>${merchant.receipt_count} receipt${merchant.receipt_count === 1 ? "" : "s"}${merchant.address ? ` · ${escapeHtml(merchant.address)}` : ""}</small></span><strong>${money(merchant.amount, data.currency)}</strong></div>`).join("") : `<div class="chart-empty">No merchant spending in this period.</div>`;
}

function renderProducts(data) {
  $("#top-products-table").innerHTML = data.top_products.length ? `<div class="product-row header"><span>Product</span><span>Times bought</span><span>Quantity</span><span>Spend</span></div>${data.top_products.map((product) => `<div class="product-row"><strong>${escapeHtml(titleCase(product.description))}</strong><span>${product.purchase_count}</span><span>${Number(product.quantity).toLocaleString()}</span><strong>${money(product.amount, data.currency)}</strong></div>`).join("")}` : `<div class="chart-empty">Approve receipts with line items to see product insights.</div>`;
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
      <span class="line-copy"><strong>${escapeHtml(merchantName(receipt.merchant_id))}</strong><small>${titleCase(receipt.category)} · created by ${escapeHtml(receipt.created_by_display_name || memberName(receipt.created_by_user_id))}</small></span>
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
      <span class="line-copy"><strong>${escapeHtml(entry.source)}</strong><small>${entry.category === "salary_payslip" ? "Salary / Payslip" : titleCase(entry.category)} · received by ${escapeHtml(entry.received_by_display_name || memberName(entry.received_by_user_id))}${entry.destination_payment_method_id ? ` · ${escapeHtml(methodName(entry.destination_payment_method_id))}` : ""}</small></span>
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
  form.elements.category.value = receipt.category || "other";
  form.elements.receipt_number.value = receipt.receipt_number || "";
  form.elements.purchase_date.value = receipt.purchase_date;
  form.elements.stated_total.value = receipt.stated_total;
  form.elements.currency.value = receipt.currency;
  form.elements.notes.value = receipt.notes || "";
  [...form.elements].forEach((element) => { element.disabled = !editable; });
  $("#item-form").hidden = !editable;
  $("#payment-form").hidden = !editable;
  $("#approve-receipt").hidden = !editable;
  $("#reopen-receipt").hidden = receipt.status !== "approved";
  $("#void-receipt").hidden = receipt.status === "voided";
  const imageCard = $("#receipt-image-card");
  const storedImage = $("#receipt-stored-image");
  imageCard.hidden = !receipt.image_url;
  storedImage.hidden = true;
  storedImage.removeAttribute("src");
  $("#view-receipt-image").textContent = "View image";
  $("#download-receipt-image").href = receipt.image_url ? `${receipt.image_url}?download=true` : "#";
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
  $("#merchant-list").innerHTML = state.merchants.length ? state.merchants.map((merchant) => `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(merchant.name)}</strong><small>${escapeHtml(merchant.address || "No branch address")}</small></div><button type="button" class="secondary" data-edit-merchant="${merchant.id}">Edit</button></div>`).join("") : `<p class="muted">No merchants yet.</p>`;
  $("#method-list").innerHTML = state.methods.length ? state.methods.map((method) => `<div class="setting-item"><div class="line-copy"><strong>${escapeHtml(methodName(method.id))}</strong><small>${canAdministerHousehold() ? `${escapeHtml(memberName(method.user_id))} · ` : ""}${titleCase(method.method_type)}${method.provider ? ` · ${escapeHtml(method.provider)}` : ""}${method.is_active ? "" : " · Inactive"}</small></div><div class="line-actions"><button class="icon-button" data-edit-method="${method.id}">Edit</button>${method.is_active ? `<button class="icon-button delete" data-deactivate-method="${method.id}">Deactivate</button>` : ""}</div></div>`).join("") : `<p class="muted">No payment methods yet.</p>`;
}

function resetMethodForm() {
  const form = $("#method-form"); form.reset(); form.elements.edit_id.value = "";
  form.querySelector("button[type=submit]").textContent = "Add method";
  $("[data-cancel-method]").hidden = true;
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
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-toggle-password]");
    if (!toggle) return;
    const input = toggle.closest(".password-field").querySelector("input");
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    toggle.textContent = showing ? "Show" : "Hide";
    toggle.setAttribute("aria-label", `${showing ? "Show" : "Hide"} password`);
  });
  const dashboardNow = new Date();
  const periodForm = $("#dashboard-period-form");
  periodForm.elements.month.innerHTML = Array.from({ length: 12 }, (_, index) => `<option value="${index + 1}">${new Intl.DateTimeFormat("en", { month: "long" }).format(new Date(2026, index, 1))}</option>`).join("");
  periodForm.elements.year.innerHTML = Array.from({ length: 6 }, (_, index) => dashboardNow.getFullYear() + 1 - index).map((year) => `<option value="${year}">${year}</option>`).join("");
  periodForm.elements.month.value = dashboardNow.getMonth() + 1;
  periodForm.elements.year.value = dashboardNow.getFullYear();
  $(".brand").addEventListener("click", (event) => { event.preventDefault(); switchView("dashboard"); });
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
  $("#dashboard-period-form").addEventListener("change", () => loadDashboard().catch((error) => notify(error.message, true)));
  $("#merchant-period").addEventListener("change", renderMerchantChart);
  $("#spending-pattern-period").addEventListener("change", () => renderSpendingPattern(state.dashboard));
  $("#receipt-search-form").addEventListener("submit", async (event) => { event.preventDefault(); await loadReceipts(); });
  $("[data-clear-receipt-search]").addEventListener("click", async () => { $("#receipt-search-form").reset(); await loadReceipts(); });
  $("#export-dashboard-csv").addEventListener("click", () => {
    const { year, month } = dashboardPeriod();
    window.location.assign(`/dashboard/export.csv?year=${year}&month=${month}`);
  });
  $("#print-dashboard").addEventListener("click", () => window.print());
  $("#show-capture-receipt").addEventListener("click", () => {
    history.replaceState(null, "", `${location.pathname}#receipts/scan`);
    $("#receipt-create-form").hidden = true;
    $("#capture-review").hidden = true;
    $("#receipt-capture-form").hidden = false;
  });
  $("#show-create-receipt").addEventListener("click", () => {
    const form = $("#receipt-create-form");
    form.elements.capture_id.value = "";
    form.hidden = false;
    form.elements.purchase_date.value = today();
    form.elements.currency.value = activeCurrency();
    $("#capture-merchant-hint").hidden = true;
  });
  $("[data-cancel-create]").addEventListener("click", () => {
    $("#receipt-create-form").hidden = true;
    if (state.capture) $("#capture-review").hidden = false;
  });
  $("[data-cancel-capture]").addEventListener("click", () => {
    $("#receipt-capture-form").hidden = true;
    history.replaceState(null, "", location.pathname);
  });
  const receiptImageInputs = [...document.querySelectorAll("[data-receipt-image]")];
  receiptImageInputs.forEach((input) => input.addEventListener("change", (event) => {
    const file = event.currentTarget.files?.[0] || null;
    const error = captureFileError(file);
    showCaptureUploadError(error);
    if (error) {
      selectedReceiptImage = null;
      event.currentTarget.value = "";
      const preview = $("#capture-preview");
      preview.hidden = true; preview.removeAttribute("src");
      return;
    }
    selectedReceiptImage = file;
    receiptImageInputs.filter((item) => item !== event.currentTarget).forEach((item) => { item.value = ""; });
    const preview = $("#capture-preview");
    if (!file) { preview.hidden = true; preview.removeAttribute("src"); return; }
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  }));
  $("#receipt-capture-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const validationError = captureFileError(selectedReceiptImage);
    if (validationError) { showCaptureUploadError(validationError); notify(validationError, true); return; }
    showCaptureUploadError();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true; button.textContent = "Reading receipt…";
    try {
      const body = new FormData();
      body.append("file", selectedReceiptImage);
      const uploaded = await run(() => api("/receipt-captures", { method: "POST", body }), null);
      state.capture = uploaded.ocr_status === "succeeded"
        ? uploaded
        : await run(() => api(`/receipt-captures/${uploaded.id}/ocr`, { method: "POST" }), uploaded.ocr_status === "pending" ? "Receipt image uploaded" : null);
      if (uploaded.reused) notify("Recovered the earlier unfinished receipt capture");
      renderCaptureReview();
    } catch (error) { showCaptureUploadError(error.message || "The image could not be uploaded."); }
    finally { button.disabled = false; button.textContent = "Upload and read text"; }
  });
  $("#retry-ocr").addEventListener("click", async () => {
    if (!state.capture) return;
    const result = await run(() => api(`/receipt-captures/${state.capture.id}/ocr`, { method: "POST" }), "OCR retried").catch(() => null);
    if (result) { state.capture = result; renderCaptureReview(); }
  });
  $("#use-capture").addEventListener("click", useCaptureSuggestions);
  $("#open-duplicate-receipt").addEventListener("click", async () => {
    if (!state.capture?.possible_duplicate_receipt_id) return;
    const duplicateReceiptId = state.capture.possible_duplicate_receipt_id;
    resetCaptureUi();
    switchView("receipts");
    await openReceipt(duplicateReceiptId);
  });
  $("#discard-capture").addEventListener("click", async () => {
    if (!state.capture || !confirm("Discard this captured image and OCR text?")) return;
    const discarded = await run(() => api(`/receipt-captures/${state.capture.id}`, { method: "DELETE" }), "Capture discarded").catch(() => false);
    if (discarded !== false) resetCaptureUi();
  });
  $("#back-to-receipts").addEventListener("click", closeReceipt);
  $("[data-cancel-income]").addEventListener("click", resetIncomeForm);

  $("#receipt-list").addEventListener("click", (event) => {
    const target = event.target.closest("[data-open-receipt]");
    if (target) openReceipt(target.dataset.openReceipt);
  });

  $("#receipt-create-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const receipt = await run(() => api("/receipts", { method: "POST", body: JSON.stringify({ capture_id: data.get("capture_id") || null, merchant_id: data.get("merchant_id") || null, payment_method_id: data.get("payment_method_id") || null, category: data.get("category"), receipt_number: data.get("receipt_number") || null, purchase_date: data.get("purchase_date"), stated_total: data.get("stated_total"), currency: String(data.get("currency")).toUpperCase(), notes: data.get("notes") || null }) }), "Receipt created").catch(() => null);
    if (receipt) { form.reset(); form.hidden = true; resetCaptureUi(); await loadReceipts(); await openReceipt(receipt.id); }
  });

  $("#recurring-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const id = data.get("edit_id");
    const payload = { name: data.get("name"), merchant_id: data.get("merchant_id") || null, payment_method_id: data.get("payment_method_id") || null, category: data.get("category"), amount: data.get("amount"), currency: String(data.get("currency")).toUpperCase(), frequency: data.get("frequency"), day_of_month: data.get("day_of_month") ? Number(data.get("day_of_month")) : null, next_occurrence_date: data.get("next_occurrence_date"), notes: data.get("notes") || null, is_active: data.get("is_active") === "on" };
    const saved = await run(() => api(id ? `/recurring-expenses/${id}` : "/recurring-expenses", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) }), "Recurring expense saved").catch(() => null);
    if (saved) { resetRecurringForm(); await loadReceipts(); }
  });
  $("[data-cancel-recurring]").addEventListener("click", resetRecurringForm);
  $("#recurring-list").addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-recurring]"); const remove = event.target.closest("[data-delete-recurring]");
    if (edit) { const entry = state.recurring.find((item) => item.id === edit.dataset.editRecurring); const form = $("#recurring-form"); Object.entries(entry).forEach(([key, value]) => { if (form.elements[key] && form.elements[key].type !== "checkbox") form.elements[key].value = value ?? ""; }); form.elements.edit_id.value = entry.id; form.elements.is_active.checked = entry.is_active; $("[data-cancel-recurring]").hidden = false; form.scrollIntoView({ behavior: "smooth" }); }
    if (remove && confirm("Delete this recurring template? Existing drafts remain.")) { const deleted = await run(() => api(`/recurring-expenses/${remove.dataset.deleteRecurring}`, { method: "DELETE" }), "Recurring expense deleted").catch(() => false); if (deleted !== false) await loadReceipts(); }
  });

  $("#receipt-edit-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const receipt = await run(() => api(`/receipts/${state.receipt.id}`, { method: "PATCH", body: JSON.stringify({ merchant_id: data.get("merchant_id") || null, category: data.get("category"), receipt_number: data.get("receipt_number") || null, purchase_date: data.get("purchase_date"), stated_total: data.get("stated_total"), currency: String(data.get("currency")).toUpperCase(), notes: data.get("notes") || null }) }), "Receipt updated").catch(() => null);
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

  $("#approve-receipt").addEventListener("click", async () => { if (confirm("Approve this receipt? You can reopen it later if a correction is needed.")) { const result = await run(() => api(`/receipts/${state.receipt.id}/approve`, { method: "POST" }), "Receipt approved").catch(() => null); if (result) { closeReceipt(); switchView("receipts"); } } });
  $("#reopen-receipt").addEventListener("click", async () => {
    if (!confirm("Reopen this approved receipt for editing? It will temporarily leave approved dashboard totals.")) return;
    const result = await run(() => api(`/receipts/${state.receipt.id}/reopen`, { method: "POST" }), "Receipt reopened").catch(() => null);
    if (result) await refreshReceipt();
  });
  $("#view-receipt-image").addEventListener("click", () => {
    const image = $("#receipt-stored-image");
    const showing = !image.hidden;
    if (!showing && !image.getAttribute("src")) image.src = state.receipt.image_url;
    image.hidden = showing;
    $("#view-receipt-image").textContent = showing ? "View image" : "Hide image";
  });
  $("#void-receipt").addEventListener("click", async () => { const reason = prompt("Why is this receipt being voided? (optional)"); if (reason !== null) { const result = await run(() => api(`/receipts/${state.receipt.id}/void`, { method: "POST", body: JSON.stringify({ reason: reason || null }) }), "Receipt voided").catch(() => null); if (result) await refreshReceipt(); } });

  $("#merchant-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const result = await run(() => api("/merchants", { method: "POST", body: JSON.stringify({ name: data.get("name"), address: data.get("address") || null }) }), "Merchant added").catch(() => null); if (result) { form.reset(); await loadSetup(); await loadReceipts(); } });
  $("#merchant-list").addEventListener("click", async (event) => {
    const merchant = state.merchants.find((item) => item.id === event.target.closest("[data-edit-merchant]")?.dataset.editMerchant);
    if (!merchant) return;
    const name = window.prompt("Merchant name", merchant.name);
    if (name === null) return;
    const address = window.prompt("Branch address (leave blank for none)", merchant.address || "");
    if (address === null) return;
    const updated = await run(() => api(`/merchants/${merchant.id}`, { method: "PATCH", body: JSON.stringify({ name, address: address.trim() || null }) }), "Merchant updated").catch(() => null);
    if (updated) { await loadSetup(); await loadReceipts(); }
  });
  $("#method-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const editId = data.get("edit_id"); const path = editId ? `/payment-methods/${editId}` : "/payment-methods"; const result = await run(() => api(path, { method: editId ? "PATCH" : "POST", body: JSON.stringify({ name: data.get("name"), method_type: data.get("method_type"), provider: data.get("provider") || null, last_four: data.get("last_four") || null }) }), editId ? "Payment method updated" : "Payment method added").catch(() => null); if (result) { resetMethodForm(); await loadSetup(); } });
  $("[data-cancel-method]").addEventListener("click", resetMethodForm);
  $("#refresh-maintenance-button").addEventListener("click", () => loadMaintenance().catch((error) => notify(error.message, true)));
  $("#refresh-diagnostics").addEventListener("click", () => run(loadDiagnostics, "Diagnostics refreshed"));
  $("#clear-diagnostics").addEventListener("click", async () => {
    if (!confirm("Clear the in-memory diagnostic log?")) return;
    await run(() => api("/diagnostics/errors", { method: "DELETE" }), "Diagnostics cleared");
    await loadDiagnostics();
  });
  $("#download-archive-button").addEventListener("click", () => {
    window.location.assign("/maintenance/archive");
  });
  $("#household-reset-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const confirmation = String(new FormData(form).get("confirmation") || "");
    if (!state.maintenance || confirmation !== state.maintenance.confirmation_phrase) {
      notify("The confirmation phrase does not match", true);
      return;
    }
    if (!confirm("Permanently delete this household's receipts, images, OCR data, income and audit history? Download an archive first if needed.")) return;
    const result = await run(
      () => api("/maintenance/reset", { method: "POST", body: JSON.stringify({ confirmation }) }),
      "Household financial data reset",
    ).catch(() => null);
    if (result) {
      form.reset();
      clearHouseholdData();
      await loadAuthenticatedData();
      switchView("settings");
      if (result.image_delete_failures) notify(`Data reset; ${result.image_delete_failures} image object(s) could not be removed`, true);
    }
  });
  $("#method-list").addEventListener("click", async (event) => { const edit = event.target.closest("[data-edit-method]"); const target = event.target.closest("[data-deactivate-method]"); if (edit) { const method = state.methods.find((item) => item.id === edit.dataset.editMethod); const form = $("#method-form"); form.elements.edit_id.value = method.id; form.elements.name.value = method.name; form.elements.method_type.value = method.method_type; form.elements.provider.value = method.provider || ""; form.elements.last_four.value = method.last_four || ""; form.querySelector("button[type=submit]").textContent = "Save method"; $("[data-cancel-method]").hidden = false; form.scrollIntoView({ behavior: "smooth", block: "center" }); } if (target && confirm("Deactivate this payment method? Existing receipt payments stay unchanged.")) { const result = await run(() => api(`/payment-methods/${target.dataset.deactivateMethod}/deactivate`, { method: "POST" }), "Payment method deactivated").catch(() => null); if (result) await loadSetup(); } });

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
    const reset = event.target.closest("[data-reset-password]");
    if (reset) {
      const password = prompt(`Enter a temporary password for ${reset.dataset.memberName} (minimum 12 characters):`);
      if (password === null) return;
      if (password.length < 12) { notify("Password must contain at least 12 characters", true); return; }
      const confirmation = prompt("Enter the temporary password again:");
      if (confirmation !== password) { notify("Passwords do not match", true); return; }
      const changed = await run(
        () => api(`/household/members/${reset.dataset.resetPassword}/password`, { method: "PUT", body: JSON.stringify({ password }) }),
        "Password reset. The member must sign in again.",
      ).catch(() => false);
      if (changed !== false) await loadMembers();
      return;
    }
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
    const category = data.get("category");
    const payload = { source: data.get("source"), category, income_type: category === "salary_payslip" ? "salary" : (["freelance", "interest", "gift", "refund"].includes(category) ? category : "other"), received_date: data.get("received_date"), amount: data.get("amount"), currency: String(data.get("currency")).toUpperCase(), destination_payment_method_id: data.get("destination_payment_method_id") || null, notes: data.get("notes") || null };
    const result = await run(() => api(editId ? `/income/${editId}` : "/income", { method: editId ? "PATCH" : "POST", body: JSON.stringify(payload) }), editId ? "Income updated" : "Income added").catch(() => null);
    if (result) { resetIncomeForm(); await loadIncomes(); renderReceiptIndex(); }
  });

  $("#income-list").addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit-income]"); const remove = event.target.closest("[data-delete-income]");
    if (edit) { const entry = state.incomes.find((item) => item.id === edit.dataset.editIncome); const form = $("#income-form"); form.elements.edit_id.value = entry.id; form.elements.source.value = entry.source; form.elements.category.value = entry.category || "other"; form.elements.received_date.value = entry.received_date; form.elements.amount.value = entry.amount; form.elements.currency.value = entry.currency; form.elements.destination_payment_method_id.value = entry.destination_payment_method_id || ""; form.elements.notes.value = entry.notes || ""; $("#income-form-title").textContent = "Edit income"; form.querySelector("button[type=submit]").textContent = "Save income"; $("[data-cancel-income]").hidden = false; form.scrollIntoView({ behavior: "smooth", block: "start" }); }
    if (remove && confirm("Delete this income entry?")) { const result = await run(() => api(`/income/${remove.dataset.deleteIncome}`, { method: "DELETE" }), "Income deleted").catch(() => false); if (result !== false) { await loadIncomes(); renderReceiptIndex(); } }
  });
}

async function loadAuthenticatedData() {
  $("#receipt-create-form input[name=purchase_date]").value = today();
  $("#income-form input[name=received_date]").value = today();
  await loadHouseholds();
  state.uploadPolicy = await api("/receipt-captures/upload-policy");
  $("#capture-upload-policy").textContent = `JPEG, PNG or WebP. Maximum file size: ${readableBytes(state.uploadPolicy.max_bytes)}.`;
  $("#receipt-create-form input[name=currency]").value = activeCurrency();
  $("#income-form input[name=currency]").value = activeCurrency();
  state.members = await api("/household/members");
  await loadSetup();
  await loadIncomes();
  await loadReceipts();
  await loadDashboard();
  const match = location.hash.match(/^#receipt\/([0-9a-f-]+)$/i);
  if (match) {
    switchView("receipts");
    await openReceipt(match[1]);
  } else if (location.hash === "#receipts/scan") {
    switchView("receipts");
    $("#receipt-create-form").hidden = true;
    $("#capture-review").hidden = true;
    $("#receipt-capture-form").hidden = false;
  }
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

window.expenseApp = { api, escapeHtml, notify, refreshReceipt, state };
init();
