function themeIcon(theme) {
  return theme === "dark" ? "sun" : "moon";
}

function paintThemeButton(button, theme) {
  const icon = button.querySelector("[data-theme-icon]");
  if (icon) icon.setAttribute("data-lucide", themeIcon(theme));
  button.setAttribute("aria-label", theme === "dark" ? "라이트 모드" : "다크 모드");
  button.title = button.getAttribute("aria-label");
  window.lucide?.createIcons();
}

export function bindTheme(button) {
  if (!button) return () => {};
  const apply = (theme) => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("atlas-theme", theme);
    paintThemeButton(button, theme);
  };
  paintThemeButton(button, document.documentElement.dataset.theme || "light");
  const onClick = () => apply(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  button.addEventListener("click", onClick);
  return () => button.removeEventListener("click", onClick);
}
