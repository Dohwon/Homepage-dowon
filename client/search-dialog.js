function resultMarkup(items) {
  if (!items.length) return '<p class="empty-state">검색 결과가 없습니다.</p>';
  return items.map((item) => `
    <a class="search-result" data-search-result data-route-link href="${escapeAttribute(item.url || `/projects/${encodeURIComponent(item.project_id || item.id)}`)}">
      <strong>${escapeHtml(item.title || item.name || item.project_id || item.id)}</strong>
      <span>${escapeHtml(item.summary || item.body || "")}</span>
    </a>
  `).join("");
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[character]));
}

function escapeAttribute(value) {
  const href = String(value || "");
  return href.startsWith("/") && !href.startsWith("//") ? escapeHtml(href) : "/";
}

export function bindSearchDialog(dialog, api) {
  if (!dialog) return () => {};
  const input = dialog.querySelector("#atlas-search-input");
  const results = dialog.querySelector("#search-results");
  const closeButton = dialog.querySelector("[data-search-close]");
  const triggers = [...document.querySelectorAll("[data-search-trigger]")];
  let requestId = 0;
  let timer = 0;

  const open = () => {
    if (!dialog.open) dialog.showModal();
    input?.focus();
  };
  const close = () => {
    if (dialog.open) dialog.close();
  };
  const runSearch = async () => {
    const query = input?.value.trim() || "";
    const current = ++requestId;
    if (!query) {
      results.innerHTML = '<p class="empty-state">검색어를 입력하세요.</p>';
      return;
    }
    results.setAttribute("aria-busy", "true");
    try {
      const response = await api.search(query);
      if (current !== requestId) return;
      const items = Array.isArray(response) ? response : (response.items || []);
      results.innerHTML = resultMarkup(items.slice(0, 20));
    } catch {
      if (current === requestId) results.innerHTML = '<p class="empty-state">검색 결과를 불러오지 못했습니다.</p>';
    } finally {
      if (current === requestId) results.removeAttribute("aria-busy");
    }
  };
  const onInput = () => {
    clearTimeout(timer);
    timer = window.setTimeout(runSearch, 120);
  };
  const onKeydown = (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      open();
      return;
    }
    if (event.key === "Escape" && dialog.open) close();
    if (event.key !== "Tab" || !dialog.open) return;
    const focusable = [...dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), a[href]')];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  const onDialogClick = (event) => {
    if (event.target === dialog || event.target.closest("[data-search-result]")) close();
  };

  triggers.forEach((trigger) => trigger.addEventListener("click", open));
  closeButton?.addEventListener("click", close);
  input?.addEventListener("input", onInput);
  document.addEventListener("keydown", onKeydown);
  dialog.addEventListener("click", onDialogClick);
  results.innerHTML = '<p class="empty-state">검색어를 입력하세요.</p>';

  return () => {
    clearTimeout(timer);
    triggers.forEach((trigger) => trigger.removeEventListener("click", open));
    closeButton?.removeEventListener("click", close);
    input?.removeEventListener("input", onInput);
    document.removeEventListener("keydown", onKeydown);
    dialog.removeEventListener("click", onDialogClick);
  };
}
