function clamp(value) {
  return Math.min(1, Math.max(0, value));
}

function updateProgress(element, ratio) {
  element.style.transform = `scaleX(${clamp(ratio)})`;
}

export function articleProgress(article, viewportTop, viewportHeight) {
  if (!article) return 0;
  const articleTop = Number(article.offsetTop) || 0;
  const articleHeight = Math.max(0, Number(article.offsetHeight) || 0);
  const visibleHeight = Math.max(0, Number(viewportHeight) || 0);
  const travel = Math.max(0, articleHeight - visibleHeight);
  if (travel === 0) return viewportTop >= articleTop ? 1 : 0;
  return clamp(((Number(viewportTop) || 0) - articleTop) / travel);
}

export function bindReadingProgress(element, article) {
  if (!element) return () => {};
  if (!article) {
    element.removeAttribute("data-active");
    updateProgress(element, 0);
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
