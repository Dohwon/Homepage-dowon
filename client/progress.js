function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clamp(value) {
  const number = finiteNumber(value);
  if (number <= 0) return 0;
  if (number >= 1) return 1;
  return number;
}

function updateProgress(element, ratio) {
  element.style.transform = `scaleX(${clamp(ratio)})`;
}

function resetProgress(element) {
  if (!element) return;
  element.removeAttribute("data-active");
  updateProgress(element, 0);
}

function resolveReadingArticle(route, root) {
  if (!route || route.view !== "project" || route.tab !== "decisions") return null;
  if (!root || typeof root.querySelector !== "function") return null;
  return root.querySelector("[data-project-reader]");
}

export function articleProgress(article, viewportTop, viewportHeight) {
  if (!article) return 0;
  const articleTop = finiteNumber(article.offsetTop);
  const articleHeight = Math.max(0, finiteNumber(article.offsetHeight));
  const visibleHeight = Math.max(0, finiteNumber(viewportHeight));
  const scrollTop = finiteNumber(viewportTop);
  const travel = Math.max(0, articleHeight - visibleHeight);
  if (travel === 0) return scrollTop >= articleTop ? 1 : 0;
  return clamp((scrollTop - articleTop) / travel);
}

export function bindReadingProgress(element, article) {
  if (!element) return () => {};
  if (!article) {
    resetProgress(element);
    return () => {};
  }
  element.setAttribute("data-active", "");
  let frame = 0;
  const update = () => {
    frame = 0;
    updateProgress(element, articleProgress(article, window.scrollY, window.innerHeight));
  };
  const requestUpdate = () => {
    if (!frame) frame = requestAnimationFrame(update);
  };
  update();
  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", requestUpdate);
  return () => {
    window.removeEventListener("scroll", requestUpdate);
    window.removeEventListener("resize", requestUpdate);
    if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
    }
  };
}

export function createProgressLifecycle(element, { bind = bindReadingProgress } = {}) {
  let currentToken = null;
  let currentDispose = () => {};

  const clearBinding = () => {
    currentDispose();
    currentDispose = () => {};
  };

  return {
    begin(token) {
      currentToken = token;
      clearBinding();
      resetProgress(element);
      return token;
    },
    commit(token, route, root) {
      if (token !== currentToken) return false;
      clearBinding();
      currentDispose = bind(element, resolveReadingArticle(route, root));
      return true;
    },
    reset(token) {
      if (token !== currentToken) return false;
      clearBinding();
      resetProgress(element);
      return true;
    },
    dispose() {
      currentToken = null;
      clearBinding();
      resetProgress(element);
    }
  };
}
