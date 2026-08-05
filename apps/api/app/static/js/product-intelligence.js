"use strict";

const $p = (selector) => document.querySelector(selector);
let insightData = { counts: {}, items: [] };

async function load() {
  const app = window.expenseApp;
  const form = $p("#product-insight-filters");
  const params = new URLSearchParams();
  for (const [key, value] of new FormData(form)) if (value) params.set(key, value);
  insightData = await app.api(`/product-insights?${params}`);
  render(app);
}

function render(app) {
  const counts = insightData.counts;
  $p("#product-insight-counts").innerHTML = [
    ["Unmatched", counts.unmatched], ["Suggested", counts.suggested],
    ["Matched", counts.confirmed], ["Ignored", counts.ignored],
    ["Known products", counts.products],
    ["Food nutrition", `${counts.food_products_with_nutrition}/${counts.food_products}`],
  ].map(([label, value]) => `<div class="summary-card"><span>${label}</span><strong>${value}</strong></div>`).join("");
  const merchant = $p("#product-insight-filters [name=merchant_id]");
  const selected = merchant.value;
  merchant.innerHTML = `<option value="">All merchants</option>${app.state.merchants.map((item) => `<option value="${item.id}">${app.escapeHtml(item.name)}</option>`).join("")}`;
  merchant.value = selected;
  $p("#product-insight-list").innerHTML = insightData.items.map((item) => productRow(app, item)).join("") || `<div class="card chart-empty">No product items match these filters.</div>`;
}

function productRow(app, item) {
  const matched = item.product;
  const nutrition = matched?.nutrition && Object.keys(matched.nutrition).length;
  return `<article class="card insight-item" data-insight-row="${item.id}">
    <label class="insight-select"><input type="checkbox" data-product-select="${item.id}" ${matched ? "disabled" : ""} /><span class="status ${item.match_status}">${item.match_status === "rejected" ? "ignored" : item.match_status}</span></label>
    <div class="insight-copy"><strong>${app.escapeHtml(item.description)}</strong><small>${app.escapeHtml(item.merchant_name || "No merchant")} · ${item.purchase_date} · ${Number(item.line_total).toFixed(2)}</small>
      ${matched ? `<p><strong>Matched to:</strong> ${app.escapeHtml(matched.canonical_name)}${matched.family_name ? ` · ${app.escapeHtml(matched.family_name)}` : ""}</p><small>${app.escapeHtml(matched.brand || "No brand")} · ${nutrition ? "Nutrition available" : "Nutrition not available"}</small>` : ""}
    </div>
    <div class="insight-actions">
      ${matched ? `<button class="primary" data-view-knowledge="${matched.id}" data-item-id="${item.id}">View knowledge</button><button class="secondary" data-identify-product="${item.id}" data-refresh-product="true">Enrich details</button><button class="secondary" data-find-existing="${item.id}">Change match</button>` : `<button class="primary" data-identify-product="${item.id}">Identify</button><button class="secondary" data-find-existing="${item.id}">Link existing</button><button class="secondary" data-manual-product="${item.id}">Enter manually</button>`}
      ${item.match_status === "rejected" ? `<button class="text-button" data-product-status="unmatched" data-item-id="${item.id}">Restore</button>` : `<button class="text-button" data-product-status="rejected" data-item-id="${item.id}">Ignore</button>`}
    </div>
    <div id="product-work-${item.id}" class="product-match-panel insight-work" hidden></div>
  </article>`;
}

function workPanel(itemId) {
  const panel = $p(`#product-work-${itemId}`);
  panel.hidden = false;
  return panel;
}

async function viewKnowledge(app, productId, itemId) {
  const panel = workPanel(itemId);
  panel.textContent = "Loading retained knowledge…";
  const data = await app.api(`/products/${productId}/knowledge`);
  const product = data.product;
  const nutrition = Object.entries(product.nutrition || {});
  const nutritionTable = nutrition.length ? `<div class="knowledge-grid">${nutrition.map(([key, value]) => `<span>${app.escapeHtml(key.replaceAll("_", " "))}</span><strong>${app.escapeHtml(value)}</strong>`).join("")}</div>` : `<p class="muted">No nutritional values have been retained yet.</p>`;
  const documents = data.documents.map((document) => `<article class="knowledge-document"><div class="section-heading"><div><strong>${app.escapeHtml(document.title)}</strong><small>${app.escapeHtml(document.provider)} · ${new Date(document.retrieved_at).toLocaleString()}</small></div>${document.source_url ? `<a href="${app.escapeHtml(document.source_url)}" target="_blank" rel="noopener">Open source</a>` : ""}</div><div class="knowledge-facts">${document.facts.map((fact) => `<div><strong>${app.escapeHtml(fact.fact_type.replaceAll("_", " "))}</strong><span>${app.escapeHtml(JSON.stringify(fact.value))}</span><small>${app.escapeHtml(fact.extraction_method)} · ${Math.round(Number(fact.confidence) * 100)}% evidence score · ${app.escapeHtml(fact.confirmation_status)}</small></div>`).join("") || `<p class="muted">No structured facts extracted from this source.</p>`}</div>${document.content_text ? `<details><summary>Retained source text</summary><pre class="knowledge-source">${app.escapeHtml(document.content_text)}</pre></details>` : ""}</article>`).join("");
  panel.innerHTML = `<div class="section-heading"><div><p class="eyebrow">Product knowledge</p><h3>${app.escapeHtml(product.canonical_name)}</h3></div><span class="status confirmed">${data.documents.length} source${data.documents.length === 1 ? "" : "s"}</span></div><div class="knowledge-overview"><span><strong>Brand</strong>${app.escapeHtml(product.brand || "Unknown")}</span><span><strong>Manufacturer</strong>${app.escapeHtml(product.manufacturer || "Unknown")}</span><span><strong>Family</strong>${app.escapeHtml(product.family_name || "Unclassified")}</span><span><strong>Category</strong>${app.escapeHtml(product.category || "Unclassified")}</span></div><h4>Nutrition</h4>${nutritionTable}<h4>Evidence history</h4>${documents || `<p class="muted">No retained source documents yet. Use Enrich details and confirm a sourced candidate.</p>`}`;
}

async function identify(app, itemId, barcode = null, detection = null, description = null, refreshExisting = false) {
  const panel = workPanel(itemId);
  panel.textContent = barcode ? `Looking up barcode ${barcode}…` : "Searching product knowledge and enabled sources…";
  const result = await app.api(`/receipt-items/${itemId}/enrich`, { method: "POST", body: JSON.stringify({ barcode, description, refresh_existing: refreshExisting }) });
  if (result.match.product) { app.notify(`Matched ${result.match.product.canonical_name}`); await load(); return; }
  renderCandidates(app, panel, itemId, result, detection);
}

function renderCandidates(app, panel, itemId, result, detection) {
  const audit = `<div class="product-search-summary"><strong>Search audit</strong><small>Sources: ${app.escapeHtml(result.providers_queried.join(", ") || "local only")}</small><small>AI ranking: ${result.ai_used ? "used" : "not used"} · Retailer web search: ${result.retailer_web_search_performed ? "used" : "not used"}</small></div>`;
  const barcode = detection ? `<small>Decoded ${app.escapeHtml(detection.detected_barcode)} (${app.escapeHtml(detection.barcode_format || "barcode")}); image discarded.</small>` : "";
  const candidates = result.candidates.map((candidate, index) => {
    const evidence = candidate.evidence || {};
    const source = candidate.source_url ? `<a href="${app.escapeHtml(candidate.source_url)}" target="_blank" rel="noopener">View evidence</a>` : "No source page";
    return `<div class="product-candidate"><span><strong>${app.escapeHtml(candidate.canonical_name)}</strong><small>${app.escapeHtml(candidate.brand || "No brand")} · ${app.escapeHtml(candidate.family_name || "Unclassified")}</small><small>${Math.round(candidate.confidence * 100)}% ranking score—not probability · ${app.escapeHtml(evidence.reason || "No explanation")}</small><small>${app.escapeHtml(candidate.provider)} · ${source}</small></span><button class="secondary" data-confirm-candidate="${index}" data-run-id="${result.run_id}" data-item-id="${itemId}">Confirm</button></div>`;
  }).join("");
  panel.innerHTML = barcode + audit + (candidates || `<p>No reliable recommendation was found. Use <strong>Link existing</strong> or <strong>Enter manually</strong>.</p>`);
}

async function findExisting(app, itemId) {
  const panel = workPanel(itemId);
  panel.innerHTML = `<form class="inline-search" data-existing-search="${itemId}"><input name="query" maxlength="200" placeholder="Search known product name or barcode" required /><button class="secondary">Search</button></form><div data-existing-results></div>`;
  panel.querySelector("input").focus();
}

async function showExistingResults(app, form) {
  const products = await app.api(`/products?query=${encodeURIComponent(new FormData(form).get("query"))}`);
  form.parentElement.querySelector("[data-existing-results]").innerHTML = products.map((product) => `<div class="product-candidate"><span><strong>${app.escapeHtml(product.canonical_name)}</strong><small>${app.escapeHtml(product.brand || "No brand")} · ${app.escapeHtml(product.family_name || "Unclassified")}</small></span><button class="secondary" data-confirm-product="${product.id}" data-item-id="${form.dataset.existingSearch}">Link</button></div>`).join("") || `<p class="muted">No known product found. Enter it manually instead.</p>`;
}

function openManual(app, itemId) {
  const item = insightData.items.find((row) => row.id === itemId);
  const card = $p("#manual-product-card");
  const form = $p("#manual-product-form");
  form.reset();
  form.elements.item_id.value = itemId;
  form.elements.canonical_name.value = item.description;
  form.elements.description.value = item.description;
  $p("#manual-product-source").textContent = `Receipt text: ${item.description} · ${item.merchant_name || "No merchant"}`;
  card.hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function createManual(app, form) {
  const data = new FormData(form);
  const nutrition = Object.fromEntries(["energy_kcal", "fat_g", "carbohydrate_g", "protein_g", "salt_g"].flatMap((key) => data.get(key) ? [[key, Number(data.get(key))]] : []));
  if (Object.keys(nutrition).length) Object.assign(nutrition, { basis_quantity: 100, basis_unit: "g" });
  const optional = (name) => data.get(name)?.trim() || null;
  const payload = { canonical_name: data.get("canonical_name"), description: optional("description"), brand: optional("brand"), manufacturer: optional("manufacturer"), family_name: optional("family_name"), product_type: data.get("product_type"), category: optional("category"), barcode: optional("barcode"), metadata: {}, nutrition };
  const result = await app.api(`/product-insights/items/${data.get("item_id")}/manual`, { method: "POST", body: JSON.stringify(payload) });
  app.notify(`Created and matched ${result.product.canonical_name}`);
  $p("#manual-product-card").hidden = true;
  await load();
}

async function scanBarcode(app, itemId, file) {
  const panel = workPanel(itemId); panel.textContent = "Reading barcode…";
  const body = new FormData(); body.append("file", file);
  const detection = await app.api(`/receipt-items/${itemId}/barcode-detect`, { method: "POST", body });
  if (!detection.detected_barcode) { panel.textContent = detection.error_message || "No barcode detected."; return; }
  await identify(app, itemId, detection.detected_barcode, detection);
}

document.addEventListener("submit", async (event) => {
  const app = window.expenseApp;
  try {
    if (event.target.id === "product-insight-filters") { event.preventDefault(); await load(); }
    if (event.target.matches("[data-existing-search]")) { event.preventDefault(); await showExistingResults(app, event.target); }
    if (event.target.id === "manual-product-form") { event.preventDefault(); await createManual(app, event.target); }
  } catch (error) { app.notify(error.message || "Product action failed", true); }
});

document.addEventListener("click", async (event) => {
  const app = window.expenseApp;
  const button = event.target.closest("button");
  if (!button) return;
  try {
    if (button.dataset.identifyProduct) {
      const itemId = button.dataset.identifyProduct;
      const description = insightData.items.find((item) => item.id === itemId)?.description || "";
      const refresh = button.dataset.refreshProduct === "true";
      workPanel(itemId).innerHTML = `<label>Search phrase<input data-product-query="${itemId}" data-refresh-existing="${refresh}" maxlength="500" value="${app.escapeHtml(description)}" /></label><div class="action-row"><button class="secondary" data-search-description="${itemId}">Search web and product sources</button><label class="secondary product-file-button">Scan barcode<input data-barcode-image="${itemId}" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" /></label><button class="secondary" data-enter-barcode="${itemId}">Enter barcode</button></div>`;
    }
    if (button.dataset.viewKnowledge) await viewKnowledge(app, button.dataset.viewKnowledge, button.dataset.itemId);
    if (button.dataset.searchDescription) {
      const itemId = button.dataset.searchDescription;
      const input = document.querySelector(`[data-product-query="${itemId}"]`);
      const description = input.value.trim();
      if (description) await identify(app, itemId, null, null, description, input.dataset.refreshExisting === "true");
    }
    if (button.dataset.enterBarcode) { const value = prompt("Enter the 8–14 digit barcode:"); if (value) await identify(app, button.dataset.enterBarcode, value.trim()); }
    if (button.dataset.findExisting) await findExisting(app, button.dataset.findExisting);
    if (button.dataset.manualProduct) openManual(app, button.dataset.manualProduct);
    if (button.dataset.confirmProduct) { await app.api(`/receipt-items/${button.dataset.itemId}/product-match/confirm`, { method: "POST", body: JSON.stringify({ product_id: button.dataset.confirmProduct }) }); await load(); }
    if (button.dataset.confirmCandidate) { await app.api(`/receipt-items/${button.dataset.itemId}/enrich/${button.dataset.runId}/candidates/${button.dataset.confirmCandidate}/confirm`, { method: "POST" }); await load(); }
    if (button.dataset.productStatus) { await app.api(`/product-insights/items/${button.dataset.itemId}/status`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.productStatus }) }); await load(); }
    if (button.id === "match-known-products") {
      const ids = [...document.querySelectorAll("[data-product-select]:checked")].map((input) => input.dataset.productSelect);
      if (!ids.length) { app.notify("Select unmatched items first", true); return; }
      const result = await app.api("/product-insights/local-match", { method: "POST", body: JSON.stringify({ item_ids: ids }) });
      app.notify(`Matched ${result.matched} of ${result.processed} from confirmed household knowledge`); await load();
    }
    if (button.matches("[data-close-product-editor]")) $p("#manual-product-card").hidden = true;
  } catch (error) { app.notify(error.message || "Product action failed", true); }
});

document.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-barcode-image]");
  if (!input?.files?.[0]) return;
  try { await scanBarcode(window.expenseApp, input.dataset.barcodeImage, input.files[0]); }
  catch (error) { window.expenseApp.notify(error.message || "Barcode recognition failed", true); }
  finally { input.value = ""; }
});

window.productIntelligence = { load };
