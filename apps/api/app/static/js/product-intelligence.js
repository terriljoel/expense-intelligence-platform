"use strict";

const itemList = document.querySelector("#item-list");
new MutationObserver(decorateItems).observe(itemList, { childList: true });

document.addEventListener("click", async (event) => {
  const target = event.target;
  const action = target.closest("[data-enrich-item], [data-search-description], [data-manual-barcode], [data-confirm-product], [data-confirm-candidate]");
  if (!action) return;
  const app = window.expenseApp;
  try {
    if (action.dataset.enrichItem) showIdentifyOptions(action.dataset.enrichItem);
    if (action.dataset.searchDescription) await searchProduct(app, action.dataset.searchDescription, null);
    if (action.dataset.manualBarcode) await enterBarcode(app, action.dataset.manualBarcode);
    if (action.dataset.confirmProduct) await confirmMatch(app, action);
    if (action.dataset.confirmCandidate) await confirmCandidate(app, action);
  } catch (error) {
    app.notify(error.message || "Product matching failed", true);
  }
});

document.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-barcode-image]");
  if (!input?.files?.[0]) return;
  try {
    await scanBarcode(window.expenseApp, input.dataset.barcodeImage, input.files[0]);
  } catch (error) {
    window.expenseApp.notify(error.message || "Barcode recognition failed", true);
  } finally {
    input.value = "";
  }
});

function decorateItems() {
  const app = window.expenseApp;
  [...itemList.querySelectorAll(".line-item")].forEach((row, index) => {
    const item = app.state.items[index];
    if (!item || item.line_type !== "product" || row.querySelector("[data-enrich-item]")) return;
    const actions = row.querySelector(".line-actions") || row.appendChild(document.createElement("div"));
    actions.classList.add("line-actions");
    actions.insertAdjacentHTML("afterbegin", `<button class="icon-button" data-enrich-item="${item.id}">${item.product_id ? "Product details" : "Identify"}</button>`);
    const copy = row.querySelector(".line-copy");
    copy.insertAdjacentHTML("beforeend", `<div id="product-match-${item.id}" class="product-match-panel" hidden></div>`);
    if (item.product_id) copy.querySelector("small").insertAdjacentText("beforeend", " · Product matched");
  });
}

function showIdentifyOptions(itemId) {
  const panel = document.querySelector(`#product-match-${itemId}`);
  panel.hidden = false;
  panel.innerHTML = `<p><strong>How should this product be identified?</strong></p><div class="action-row">
    <button class="secondary" data-search-description="${itemId}">Search receipt text</button>
    <label class="secondary product-file-button">Take barcode photo<input data-barcode-image="${itemId}" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" /></label>
    <button class="secondary" data-manual-barcode="${itemId}">Enter barcode number</button>
  </div>`;
}

async function enterBarcode(app, itemId) {
  const barcode = prompt("Enter the 8–14 digit barcode:", "");
  if (barcode?.trim()) await searchProduct(app, itemId, barcode.trim());
}

async function scanBarcode(app, itemId, file) {
  const panel = document.querySelector(`#product-match-${itemId}`);
  panel.hidden = false;
  panel.textContent = "Reading barcode from image…";
  const body = new FormData();
  body.append("file", file);
  const detection = await app.api(`/receipt-items/${itemId}/barcode-detect`, { method: "POST", body });
  if (!detection.detected_barcode) {
    panel.innerHTML = `<p><strong>No barcode detected.</strong></p><p class="muted">${app.escapeHtml(detection.error_message || "Try a closer, sharper photo.")}</p><small>The photo was processed in memory and was not stored.</small>`;
    return;
  }
  app.notify(`Detected ${detection.detected_barcode} (${detection.barcode_format || "barcode"})`);
  await searchProduct(app, itemId, detection.detected_barcode, detection);
}

async function searchProduct(app, itemId, barcode, capture = null) {
  const panel = document.querySelector(`#product-match-${itemId}`);
  panel.hidden = false;
  panel.textContent = barcode ? `Looking up barcode ${barcode}…` : "Searching product knowledge…";
  const result = await app.api(`/receipt-items/${itemId}/enrich`, {
    method: "POST",
    body: JSON.stringify({ barcode }),
  });
  if (result.match.product) {
    app.notify(`Matched ${result.match.product.canonical_name}`);
    await app.refreshReceipt();
    return;
  }
  renderCandidates(app, panel, itemId, result, capture);
}

function renderCandidates(app, panel, itemId, result, detection) {
  if (!result.candidates.length) {
    panel.textContent = result.errors.length ? `No match. ${result.errors.join(", ")}` : "No product match found yet.";
    return;
  }
  const audit = `<div class="product-search-summary"><strong>Search audit</strong><small>Sources queried: ${app.escapeHtml(result.providers_queried.join(", ") || "local knowledge only")}</small><small>GitHub Models used: ${result.ai_used ? "Yes — ranking only" : "No"}</small><small>REWE/Aldi/Edeka searched: ${result.retailer_web_search_performed ? "Yes" : "No"}</small></div>`;
  const barcodeEvidence = detection ? `<p><small>Detected ${app.escapeHtml(detection.detected_barcode)} · ${app.escapeHtml(detection.barcode_format || "barcode")} · photo discarded after decoding</small></p>` : "";
  panel.innerHTML = barcodeEvidence + audit + result.candidates.map((candidate, index) => {
    const evidence = candidate.evidence || {};
    const source = candidate.source_url ? `· <a href="${app.escapeHtml(candidate.source_url)}" target="_blank" rel="noopener">View source</a>` : "· no external page";
    return `<div class="product-candidate"><span><strong>${app.escapeHtml(candidate.canonical_name)}</strong>
      <small>Brand: ${app.escapeHtml(candidate.brand || "Not provided")}</small>
      <small>Family: ${app.escapeHtml(candidate.family_name || "Not classified")}</small>
      <small>Category: ${app.escapeHtml(candidate.category || "Not classified")}</small>
      <small>Evidence: ${app.escapeHtml(evidence.level || "unknown")} · ${Math.round(candidate.confidence * 100)}% ranking score</small>
      <small>${app.escapeHtml(evidence.reason || "No explanation supplied")}</small>
      <small>${app.escapeHtml(evidence.score_formula || "No fuzzy formula used")}</small>
      <small>Source: ${app.escapeHtml(candidate.provider)} ${source}</small></span>
      <button class="secondary" data-confirm-candidate="${index}" data-run-id="${result.run_id}" data-item-id="${itemId}">Confirm</button></div>`;
  }).join("") + (result.agent_decision ? `<p class="muted">AI assessment: ${app.escapeHtml(result.agent_decision.explanation)}</p>` : "");
}

async function confirmMatch(app, button) {
  const result = await app.api(`/receipt-items/${button.dataset.itemId}/product-match/confirm`, { method: "POST", body: JSON.stringify({ product_id: button.dataset.confirmProduct }) });
  app.notify(`Confirmed ${result.product.canonical_name}`);
  await app.refreshReceipt();
}

async function confirmCandidate(app, button) {
  const result = await app.api(`/receipt-items/${button.dataset.itemId}/enrich/${button.dataset.runId}/candidates/${button.dataset.confirmCandidate}/confirm`, { method: "POST" });
  app.notify(`Confirmed ${result.product.canonical_name}`);
  await app.refreshReceipt();
}

async function recognizeAll(app) {
  const items = app.state.items.filter((item) => item.line_type === "product" && !item.product_id);
  if (!items.length) { app.notify("No unmatched product items to recognize"); return; }
  decorateItems();
  let suggestions = 0;
  for (const [index, item] of items.entries()) {
    const panel = document.querySelector(`#product-match-${item.id}`);
    if (!panel) continue;
    panel.hidden = false;
    panel.textContent = `Recognizing product ${index + 1} of ${items.length}…`;
    try {
      const result = await app.api(`/receipt-items/${item.id}/enrich`, {
        method: "POST",
        body: JSON.stringify({ barcode: null }),
      });
      if (result.match.product) {
        panel.innerHTML = `<p><strong>Matched from confirmed household knowledge:</strong> ${app.escapeHtml(result.match.product.canonical_name)}</p>`;
      } else {
        renderCandidates(app, panel, item.id, result, null);
        suggestions += result.candidates.length ? 1 : 0;
      }
    } catch (error) {
      panel.textContent = `Recognition failed: ${error.message || "unknown error"}`;
    }
  }
  app.notify(`Product recognition finished: ${suggestions} item${suggestions === 1 ? " has" : "s have"} recommendations`);
}

window.productIntelligence = { recognizeAll };
