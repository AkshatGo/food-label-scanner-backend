const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const state = {
  user: null,
  products: [],
  authMode: "login",
  afterAuth: null,
  pending: null,
  polling: false,
  current: null,
};
const paths = {
  scan: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M7 12h10"/>',
  home: '<path d="m3 10 9-7 9 7v10H3ZM9 20v-7h6v7"/>',
  book: '<path d="M3 4h6l3 2 3-2h6v16h-6l-3 2-3-2H3ZM12 6v16"/>',
  compare: '<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>',
  user: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  package: '<path d="m12 3 9 5v10l-9 4-9-4V8Zm-9 5 9 5 9-5M12 13v9M7 6l9 5"/>',
  list: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h6"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6ZM8 12l3 3 5-6"/>',
};
function icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.package}</svg>`;
}
$$("[data-icon]").forEach((el) => {
  el.innerHTML = icon(el.dataset.icon);
});
function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
}
function message(error) {
  return error.message || "We could not complete that. Please try again.";
}
let toastTimer;
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 4200);
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    options.timeout || 45000,
  );
  try {
    const headers = { ...options.headers };
    if (options.body && !(options.body instanceof FormData))
      headers["Content-Type"] = "application/json";
    const response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      if (response.status === 401 && !path.startsWith("/auth/")) {
        state.user = null;
        state.products = [];
        renderAccount();
        renderLibrary();
      }
      throw new Error(
        data.detail?.error?.message ||
          data.error?.message ||
          (response.status === 401
            ? "Please sign in to continue."
            : `Request failed (${response.status}). Please try again.`),
      );
    }
    return response;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "This is taking longer than expected. Check your connection and try again.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "Cannot connect. Check your internet connection and try again.",
      );
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
async function json(path, options) {
  return (await api(path, options)).json();
}
function navigate(view) {
  if (location.hash === `#${view}`) route();
  else location.hash = view;
}
function route() {
  const view = location.hash.slice(1) || "home";
  const chosen = $(`#${view.replace(/[^a-z]/g, "")}Screen`) ? view : "home";
  $$(".screen").forEach((el) =>
    el.classList.toggle("hidden", el.id !== `${chosen}Screen`),
  );
  $$("[data-nav]").forEach((el) => {
    if (el.dataset.nav === chosen) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  if (chosen === "library") renderLibrary();
  if (chosen === "compare") renderCompareOptions();
  if (chosen === "profile") renderAccount();
  if (chosen === "result" && !state.current) navigate("library");
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
document.addEventListener("click", (event) => {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) navigate(viewButton.dataset.view);
  const signIn = event.target.closest("[data-signin]");
  if (signIn) showAuth();
  const product = event.target.closest("[data-product]");
  if (product)
    openProduct(product.dataset.product).catch((error) =>
      toast(message(error)),
    );
  const close = event.target.closest("[data-close]");
  if (close) close.closest("dialog").close();
});
$$("dialog").forEach((dialog) =>
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (
        event.clientX < r.left ||
        event.clientX > r.right ||
        event.clientY < r.top ||
        event.clientY > r.bottom
      )
        dialog.close();
    }
  }),
);
function showAuth(callback = null) {
  state.afterAuth = callback;
  $("#authError").textContent = "";
  $("#authDialog").showModal();
}
function requireUser(callback) {
  if (state.user) return callback();
  showAuth(callback);
}
$$("[data-auth]").forEach(
  (button) =>
    (button.onclick = () => {
      state.authMode = button.dataset.auth;
      $$("[data-auth]").forEach((el) =>
        el.setAttribute("aria-pressed", String(el === button)),
      );
      $("#authTitle").innerHTML =
        state.authMode === "login"
          ? "Welcome <em>back.</em>"
          : "Make yourself <em>at home.</em>";
      $("#authSubmit").textContent =
        state.authMode === "login" ? "Sign in" : "Create account";
      $("#password").autocomplete =
        state.authMode === "login" ? "current-password" : "new-password";
      $("#authError").textContent = "";
    }),
);
$("#authForm").onsubmit = async (event) => {
  event.preventDefault();
  $("#authSubmit").disabled = true;
  $("#authError").textContent = "";
  try {
    await json(`/auth/${state.authMode}`, {
      method: "POST",
      body: JSON.stringify({
        email: $("#email").value,
        password: $("#password").value,
      }),
    });
    state.user = await json("/auth/me");
    $("#password").value = "";
    $("#authDialog").close();
    renderAccount();
    await loadLibrary();
    toast("Your shelf is ready.");
    const callback = state.afterAuth;
    state.afterAuth = null;
    if (callback) await callback();
  } catch (error) {
    $("#authError").textContent = message(error);
  } finally {
    $("#authSubmit").disabled = false;
  }
};
function renderAccount() {
  $("#avatar").textContent = state.user
    ? state.user.email.slice(0, 2).toUpperCase()
    : "You";
  $("#preferencesForm").classList.toggle("hidden", !state.user);
  $("#accountPanel").innerHTML = state.user
    ? `<div class="account-card"><div><span class="eyebrow">SIGNED IN AS</span><h2>${esc(state.user.email)}</h2><p>Your scans are saved to your account.</p></div><button class="button subtle" id="logoutButton">Sign out</button></div>`
    : '<div class="account-card"><div><h2>A shelf of your own.</h2><p>Sign in to keep your scans and dietary preferences together.</p></div><button class="button primary" data-signin>Sign in / join</button></div>';
  $$("#preferencesForm input").forEach((input) => {
    input.checked = (state.user?.conditions || []).includes(input.value);
  });
  if ($("#logoutButton"))
    $("#logoutButton").onclick = async () => {
      try {
        await json("/auth/logout", { method: "POST" });
        state.user = null;
        state.products = [];
        state.current = null;
        state.pending = null;
        sessionStorage.removeItem("ll_pending");
        $("#productResult").replaceChildren();
        $("#compareResult").replaceChildren();
        resetCapture();
        renderAccount();
        renderLibrary();
        toast("Signed out.");
      } catch (error) {
        toast(message(error));
      }
    };
  if (state.user) {
    const actions = document.createElement("div");
    actions.className = "data-actions";
    actions.innerHTML =
      '<button class="text-button" id="exportAccount">Export my data</button><button class="text-button" id="deleteAccount">Delete account</button>';
    $("#accountPanel").append(actions);
    $("#exportAccount").onclick = async () => {
      try {
        const response = await api("/account/export");
        const url = URL.createObjectURL(await response.blob());
        const a = document.createElement("a");
        a.href = url;
        a.download = "LabelLens-account.json";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      } catch (error) {
        toast(message(error));
      }
    };
    $("#deleteAccount").onclick = () => {
      info(
        "Leave no <em>shelf behind.</em>",
        '<p>This permanently deletes your account, uploaded photos and scans from live storage. Export your data first if you want to keep it. Backups follow the operator’s retention policy.</p><form id="deleteForm"><label>Confirm your password<input id="deletePassword" type="password" autocomplete="current-password" required maxlength="128"></label><p class="inline-error" id="deleteError" role="alert"></p><button class="button primary full">Permanently delete account</button></form>',
      );
      $("#deleteForm").onsubmit = async (event) => {
        event.preventDefault();
        event.submitter.disabled = true;
        try {
          await json("/account", {
            method: "DELETE",
            body: JSON.stringify({ password: $("#deletePassword").value }),
          });
          $("#infoDialog").close();
          sessionStorage.removeItem("ll_pending");
          location.replace("/ui");
        } catch (error) {
          $("#deleteError").textContent = message(error);
          event.submitter.disabled = false;
        }
      };
    };
  }
}
$("#preferencesForm").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $("#profileError").textContent = "";
  try {
    const conditions = $$("#preferencesForm input:checked").map(
      (input) => input.value,
    );
    const data = await json(`/users/${state.user.user_id}/conditions`, {
      method: "PUT",
      body: JSON.stringify({ conditions }),
    });
    state.user.conditions = data.conditions;
    toast("Preferences saved.");
  } catch (error) {
    $("#profileError").textContent = message(error);
  } finally {
    button.disabled = false;
  }
};
const previews = new Map();
function removePhoto(name) {
  if (previews.has(name)) URL.revokeObjectURL(previews.get(name));
  previews.delete(name);
  $(`#${name}Image`).value = "";
  const img = $(`#${name}Preview`);
  if (img) {
    img.hidden = true;
    img.removeAttribute("src");
    img.closest("label").classList.remove("has-photo");
  }
  $(`[data-remove="${name}"]`).classList.add("hidden");
}
for (const name of ["front", "back", "nutrition"]) {
  $(`#${name}Image`).onchange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (
      file.size > 10 * 1024 * 1024 ||
      !["image/jpeg", "image/png", "image/webp"].includes(file.type)
    ) {
      removePhoto(name);
      $("#scanError").textContent =
        "Choose a JPEG, PNG or WEBP image smaller than 10 MB. For HEIC photos, export as JPEG first.";
      return;
    }
    $("#scanError").textContent = "";
    if (previews.has(name)) URL.revokeObjectURL(previews.get(name));
    const url = URL.createObjectURL(file);
    previews.set(name, url);
    const img = $(`#${name}Preview`);
    if (img) {
      img.src = url;
      img.hidden = false;
      img.closest("label").classList.add("has-photo");
    }
    $(`[data-remove="${name}"]`).classList.remove("hidden");
  };
  $(`[data-remove="${name}"]`).onclick = () => removePhoto(name);
}
function resetCapture() {
  ["front", "back", "nutrition"].forEach(removePhoto);
  $("#scanForm").classList.remove("hidden");
  $("#scanProgress").classList.add("hidden");
  $("#scanSubmit").disabled = false;
  $("#scanError").textContent = "";
}
$("#scanForm").onsubmit = (event) => {
  event.preventDefault();
  requireUser(submitScan);
};
async function submitScan() {
  $("#scanError").textContent = "";
  $("#scanSubmit").disabled = true;
  try {
    const body = new FormData();
    for (const name of ["front", "back", "nutrition"]) {
      const file = $(`#${name}Image`).files[0];
      if (file) body.append(`${name}_image`, file);
    }
    const scan = await json("/scan", { method: "POST", body });
    state.pending = { id: scan.scan_id, user: state.user.user_id };
    sessionStorage.setItem("ll_pending", JSON.stringify(state.pending));
    $("#scanForm").classList.add("hidden");
    $("#scanProgress").classList.remove("hidden");
    await pollScan();
  } catch (error) {
    $("#scanError").textContent = message(error);
  } finally {
    $("#scanSubmit").disabled = false;
  }
}
async function pollScan() {
  if (state.polling || !state.pending || !state.user) return;
  state.polling = true;
  $("#resumeScan").disabled = true;
  const pending = state.pending;
  try {
    for (let attempt = 0; attempt < 120; attempt++) {
      if (!state.user || state.pending !== pending) return;
      const result = await json(`/scan/${encodeURIComponent(pending.id)}`);
      if (!state.user || state.pending !== pending) return;
      if (result.status === "failed") {
        state.pending = null;
        sessionStorage.removeItem("ll_pending");
        resetCapture();
        throw new Error(
          result.error?.message ||
            "The scan could not be completed. Please try again — most failures are temporary server load, not your photos.",
        );
      }
      if (result.status === "done") {
        state.pending = null;
        sessionStorage.removeItem("ll_pending");
        resetCapture();
        await loadLibrary();
        if (location.hash === "#scan")
          await openProduct(result.product.product_id);
        else toast("Your label is ready on your shelf.");
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    $("#progressText").textContent =
      "Your scan is still queued or processing. Check again shortly; your photos are saved.";
  } catch (error) {
    $("#progressText").textContent = message(error);
    $("#scanError").textContent = message(error);
    toast(message(error));
  } finally {
    state.polling = false;
    $("#resumeScan").disabled = false;
  }
}
$("#resumeScan").onclick = pollScan;
function trustworthy(p) {
  return !p.needs_review && p.inr?.eligible && p.inr?.status === "calculated";
}
// A rating computed from an incomplete panel INFLATES (missing negatives
// score zero), so the backend now withholds stars entirely for those —
// no number is safer than an unreliable number.
function withheld(p) {
  return Boolean(p.inr?.withheld);
}
function rating(p) {
  return trustworthy(p)
    ? `${p.inr.rating_stars} / 5`
    : withheld(p)
      ? "Retake needed"
      : typeof p.inr?.rating_stars === "number" && p.inr?.eligible
        ? `~${p.inr.rating_stars} / 5 (verify)`
        : p.inr?.eligible
          ? "Review needed"
          : "Not rated";
}
// Draft INR rating as a 0-10 half-star level. Shown whenever a trusted
// number exists — under review it renders as a clearly provisional meter
// (amber, "PROVISIONAL" tag). Withheld ratings (incomplete panel) have no
// number at all, so no meter.
function meterLevel(p) {
  if (withheld(p)) return null;
  if (!p.inr?.eligible || typeof p.inr.rating_stars !== "number") return null;
  return Math.max(0, Math.min(10, Math.round(p.inr.rating_stars * 2)));
}
function meterIsProvisional(p) {
  return meterLevel(p) !== null && !trustworthy(p);
}
// Display label for the measurement basis. Uses the unit the label itself
// declared ("per 100g" vs "per 100ml") when it was detected; the beverage
// category is only a fallback, not evidence — a powder classified in the
// drink category must not be labeled "per 100ml".
function panelBasisLabel(p) {
  const unit = p.nutrition_extraction?.basis_unit;
  if (unit === "g") return "100g";
  if (unit === "ml") return "100ml";
  return p.category === "II" ? "100ml" : "100g";
}
const STAR_PATH =
  "M10 1.2l2.4 4.9 5.4.8-3.9 3.8.9 5.4L10 13.6l-4.8 2.5.9-5.4L2.2 6.9l5.4-.8z";
function meterStars(level, extraClass = "") {
  // level is half-star units (0..10): 7 => 3.5 stars = 3 full + 1 half.
  const full = Math.floor(level / 2);
  const half = level % 2 === 1;
  const fill = level * 10;
  const star = (i) =>
    `<span class="star">`
    + `<svg class="bg" viewBox="0 0 20 20" aria-hidden="true"><path d="${STAR_PATH}"/></svg>`
    + (i < full
        ? `<svg class="fill" viewBox="0 0 20 20" aria-hidden="true"><path d="${STAR_PATH}"/></svg>`
        : i === full && half
          ? `<span class="fg"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="${STAR_PATH}"/></svg></span>`
          : "")
    + `</span>`;
  return `<span class="meter-stars ${extraClass}" role="img" aria-label="${fill}% of 5 stars">`
    + Array.from({ length: 5 }, (_, i) => star(i)).join("")
    + `</span>`;
}
function ratingBadge(p) {
  const level = meterLevel(p);
  if (level === null) {
    const chip = withheld(p)
      ? `<span class="score-chip chip-withheld">${esc(rating(p))}</span>`
      : `<span class="score-chip">${esc(rating(p))}</span>`;
    return chip;
  }
  const provisional = meterIsProvisional(p);
  const starClass = provisional ? "meter-chip meter-chip-provisional" : "meter-chip";
  return `<span class="score-chip ${starClass}">${meterStars(level, provisional ? "meter-provisional" : "")}<span>${esc(p.inr.rating_stars)}/5</span></span>`;
}
function productCard(p) {
  const date = p.created_at
    ? new Date(p.created_at).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
      })
    : "";
  return `<button class="product-card" data-product="${esc(p.product_id)}"><div class="product-card-top"><img class="product-thumb" loading="lazy" src="/api/v1/scan/${encodeURIComponent(p.scan_id)}/image/front" alt="">${ratingBadge(p)}</div><h3>${esc(p.product_name)}</h3><p>${esc(p.brand || "Brand not read")}</p><div class="product-card-foot"><span>${esc(date)}</span><span>Read label ↗</span></div></button>`;
}
function emptyShelf() {
  return `<div class="empty-shelf"><span>${icon("book")}</span><div><h3>${state.user ? "Your next discovery goes here." : "A shelf for your everyday discoveries."}</h3><p>${state.user ? "Scan your first label to start a personal food library." : "Sign in to save labels and pick up where you left off."}</p></div><button class="text-button" ${state.user ? 'data-view="scan"' : "data-signin"}>${state.user ? "Scan a label ↗" : "Make it yours ↗"}</button></div>`;
}
function renderLibrary() {
  $("#recentProducts").innerHTML = state.products.length
    ? state.products.slice(0, 3).map(productCard).join("")
    : emptyShelf();
  const query = $("#librarySearch").value.toLowerCase();
  const matches = state.products.filter((p) =>
    `${p.product_name} ${p.brand || ""}`.toLowerCase().includes(query),
  );
  $("#libraryProducts").innerHTML = matches.length
    ? matches.map(productCard).join("")
    : query
      ? '<div class="empty-shelf"><p>No products match that search.</p></div>'
      : emptyShelf();
}
async function loadLibrary() {
  if (!state.user) return renderLibrary();
  const userId = state.user.user_id;
  const data = await json("/products");
  if (state.user?.user_id !== userId) return;
  state.products = data.products;
  renderLibrary();
  renderCompareOptions();
}
$("#librarySearch").oninput = renderLibrary;
$("#refreshLibrary").onclick = () =>
  requireUser(() => loadLibrary().catch((error) => toast(message(error))));
function renderCompareOptions() {
  for (const id of ["compareA", "compareB"]) {
    const previous = $(`#${id}`).value;
    $(`#${id}`).innerHTML =
      '<option value="">Choose a product</option>' +
      state.products
        .map(
          (p) =>
            `<option value="${esc(p.product_id)}">${esc(p.product_name)}</option>`,
        )
        .join("");
    $(`#${id}`).value = previous;
  }
}
const nutrients = [
  ["energy_kcal", "Energy", "kcal"],
  ["protein_g", "Protein", "g"],
  ["carbohydrate_g", "Carbohydrate", "g"],
  ["total_sugar_g", "Total sugars", "g"],
  ["added_sugar_g", "Added sugars", "g"],
  ["total_fat_g", "Total fat", "g"],
  ["saturated_fat_g", "Saturated fat", "g"],
  ["trans_fat_g", "Trans fat", "g"],
  ["sodium_mg", "Sodium", "mg"],
  ["fibre_g", "Fibre", "g"],
];
function value(v, unit = "") {
  return v == null ? "Not read" : `${esc(v)} ${unit}`;
}
$("#compareForm").onsubmit = async (event) => {
  event.preventDefault();
  $("#compareError").textContent = "";
  requireUser(async () => {
    const a = state.products.find((p) => p.product_id === $("#compareA").value),
      b = state.products.find((p) => p.product_id === $("#compareB").value);
    if (!a || !b || a === b) {
      $("#compareError").textContent =
        "Choose two different products from your shelf.";
      return;
    }
    event.submitter.disabled = true;
    try {
      const data = await json("/compare", {
        method: "POST",
        body: JSON.stringify({
          product_id_a: a.product_id,
          product_id_b: b.product_id,
        }),
      });
      const rows = nutrients.filter(([key]) => key in data.product_a);
      $("#compareResult").innerHTML =
        `<div class="table-scroll"><table><caption>Values per ${esc(panelBasisLabel(a))} / ${esc(panelBasisLabel(b))}</caption><thead><tr><th scope="col">Measure</th><th scope="col">${esc(a.product_name)}</th><th scope="col">${esc(b.product_name)}</th></tr></thead><tbody><tr><th scope="row">Draft INR rating</th><td>${esc(rating(a))}</td><td>${esc(rating(b))}</td></tr>${rows.map(([key, label, unit]) => `<tr><th scope="row">${label}</th><td>${value(data.product_a[key], unit)}</td><td>${value(data.product_b[key], unit)}</td></tr>`).join("")}</tbody></table></div><p class="comparison-note">${a.category !== b.category ? "These products are in different categories; their ratings and measurement bases are not directly comparable." : "Compare foods in the same category. A single nutrient or rating does not describe an entire diet."}</p>`;
    } catch (error) {
      $("#compareError").textContent = message(error);
    } finally {
      event.submitter.disabled = false;
    }
  });
};
async function openProduct(id) {
  const userId = state.user?.user_id;
  const p = await json(`/product/${encodeURIComponent(id)}`);
  if (!userId || state.user?.user_id !== userId) return;
  state.current = p;
  const review =
    p.needs_review || p.inr?.status === "estimated_missing_as_zero";
  const nutrition = p.nutrition_per_100g || {};
  const ingredients =
    (p.ingredients || [])
      .map((i) => `<span>${esc(typeof i === "string" ? i : i.name)}</span>`)
      .join("") ||
    "<p>No ingredients were confidently read. Retake the back photo with the ingredient list filling the frame — a close-up reads far better than the full panel.</p>";
  const counts = p.compliance?.summary?.declarations || {};
  const meter = meterLevel(p);
  const provisional = meterIsProvisional(p);
  $("#productResult").innerHTML =
    `<div class="result-heading"><div><span class="eyebrow">YOUR LABEL, DECODED</span><h1>${esc(p.product_name)}</h1><p>${esc(p.brand || "Brand not read")} · ${esc(p.net_quantity || "Pack size not read")}</p></div><div class="result-score${meter !== null && provisional ? " score-provisional" : ""}"><strong>${p.inr?.eligible && typeof p.inr.rating_stars === "number" ? esc(p.inr.rating_stars) : "—"}</strong>${meter !== null ? meterStars(meter, provisional ? "result-meter meter-provisional" : "result-meter") : ""}<small>${withheld(p) ? "NOT ENOUGH READ · RETAKE" : provisional ? `PROVISIONAL · ~${esc(p.inr.rating_stars)}/5 · VERIFY LABEL` : trustworthy(p) ? "OUT OF 5 · DRAFT INR" : "NOT RATED"}</small></div></div>${review ? `<div class="review-notice"><strong>Check these readings against the pack.</strong><ul>${(p.review_reasons?.length ? p.review_reasons : ["Incomplete readings: the rating is withheld until values can be verified."]).map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>` : ""}<div class="result-columns"><div><section class="reading-block"><h2>The nutrition panel</h2><p>Per ${esc(panelBasisLabel(p))} · ${esc(p.nutrition_extraction?.basis || "Basis not read")}</p><table class="nutrition-table"><tbody>${nutrients.map(([key, label, unit]) => `<tr><td>${label}</td><td>${value(nutrition[key], unit)}</td></tr>`).join("")}</tbody></table></section><section class="reading-block"><h2>Inside the ingredients</h2><div class="ingredient-tags">${ingredients}</div><p>Allergens detected: ${esc((p.allergens?.detected || []).join(", ") || "None detected — this does not establish allergen safety.")}</p></section></div><div><section class="reading-block"><h2>In your context</h2><div id="guidanceResult">Loading your preferences…</div></section><section class="reading-block"><h2>The label checklist</h2><div class="compliance-counts">${Object.entries(
      counts,
    )
      .map(
        ([name, count]) => `<span><strong>${count}</strong>${esc(name)}</span>`,
      )
      .join(
        "",
      )}</div><p>${esc(p.compliance?.overall_note || "An automated assessment, not a legal certification.")}</p><div class="report-actions"><button class="button subtle" id="reportButton">Download report ↓</button></div></section><details class="disclosure"><summary>How this reading was made</summary><p>${esc(p.inr?.basis)}<br>Formula: ${esc(p.inr?.formula_version)}<br>OCR confidence: ${value(p.ocr_confidence_avg, "%")}<br>Photos can miss information. Always verify critical values against the original label.</p></details></div></div><button class="button primary" data-view="scan">Read another label ↗</button>`;
  navigate("result");
  $("#reportButton").onclick = async () => {
    const button = $("#reportButton");
    button.disabled = true;
    try {
      const response = await api(
        `/compliance-report/${encodeURIComponent(id)}`,
      );
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `LabelLens-${id}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      toast(message(error));
    } finally {
      button.disabled = false;
    }
  };
  if (review) {
    $("#guidanceResult").innerHTML =
      "<p>The label needs review. Personalized verdicts are withheld because missing values could change the guidance.</p>";
    return;
  }
  if (!state.user?.conditions?.length) {
    $("#guidanceResult").innerHTML =
      '<p>Add optional dietary preferences to see the rules that apply to you.</p><button class="text-button" data-view="profile">Choose preferences ↗</button>';
    return;
  }
  try {
    const result = await json("/personalize", {
      method: "POST",
      body: JSON.stringify({ product_id: id }),
    });
    if (state.current?.product_id !== id) return;
    $("#guidanceResult").innerHTML =
      result.verdicts
        .map(
          (v) =>
            `<div class="guidance ${v.verdict === "AVOID" ? "avoid" : v.verdict === "CAUTION" ? "caution" : ""}"><strong>${esc(v.condition)} · ${esc(v.verdict.replaceAll("_", " "))}</strong><ul>${v.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`,
        )
        .join("") + `<p class="fine-print">${esc(result.disclaimer)}</p>`;
  } catch (error) {
    $("#guidanceResult").textContent = message(error);
  }
}
function info(title, body) {
  $("#infoContent").innerHTML =
    `<span class="eyebrow">LABEL LENS / THE DETAILS</span><h2>${title}</h2>${body}`;
  $("#infoDialog").showModal();
}
$("#aboutButton").onclick = () =>
  info(
    "A clearer <em>reading.</em>",
    '<p>We read the text in your photos and apply transparent, versioned rules. Nutrition ratings use the FSSAI 2022 draft INR framework; they are estimates, not an official certification or endorsement.</p><p class="fine-print">OCR can misread or omit text. We withhold prominent ratings and personalized guidance when the scan needs review. Packaging, serving sizes and ingredients still matter. Compliance reports are preliminary checks; font sizes cannot be verified without a physical scale reference.</p>',
  );
$("#privacyButton").onclick = () =>
  info(
    "Your shelf.<br><em>Your data.</em>",
    '<p>Your account contains your email, password hash, optional dietary preferences, uploaded label photos and scan results. Photos and results are used to provide the service and are available through your authenticated account.</p><p class="fine-print">This browser stores a secure session cookie and, temporarily, an unfinished scan ID. The offline cache contains only the public app shell, never your scans, photos or preferences. Sign out on shared devices.</p><p class="fine-print">This is a development preview. Operator contact details, retention policy and account deletion must be configured before public launch.</p>',
  );
function updateConnection() {
  $("#connection").classList.toggle("hidden", navigator.onLine);
}
window.addEventListener("online", () => {
  updateConnection();
  if (state.pending) pollScan();
});
window.addEventListener("offline", updateConnection);
let installPrompt;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  $("#installButton").classList.remove("hidden");
});
$("#installButton").onclick = async () => {
  if (!installPrompt) return;
  await installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  $("#installButton").classList.add("hidden");
};
window.addEventListener("appinstalled", () => {
  $("#installButton").classList.add("hidden");
  toast("LabelLens is on your home screen.");
});
// Remove sensitive legacy browser storage; sessions now use HttpOnly cookies.
for (const key of [
  "ll_token",
  "ll_user",
  "ll_email",
  "ll_conditions",
  "ll_history",
])
  localStorage.removeItem(key);
renderAccount();
renderLibrary();
route();
updateConnection();
async function boot() {
  try {
    state.user = await json("/auth/me");
    renderAccount();
    await loadLibrary();
    try {
      const pending = JSON.parse(
        sessionStorage.getItem("ll_pending") || "null",
      );
      if (pending?.user === state.user.user_id) {
        state.pending = pending;
        $("#scanForm").classList.add("hidden");
        $("#scanProgress").classList.remove("hidden");
        pollScan();
      }
    } catch {
      sessionStorage.removeItem("ll_pending");
    }
  } catch {
    /* Public home stays usable; sign-in handles session recovery. */
  }
  if ("serviceWorker" in navigator)
    navigator.serviceWorker.register("/sw.js").catch(() => {});
}
boot();
