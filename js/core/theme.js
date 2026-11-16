"use strict";
/* ---------- Dark Mode Toggle ---------- */
function initTheme(){
  const saved = localStorage.getItem("cw_theme"); const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches; const isDark = saved ? saved === "dark" : prefersDark;
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light"); $("#themeToggle")?.setAttribute("aria-pressed", isDark); }
function toggleTheme(){
  const root = document.documentElement; const isDark = root.getAttribute("data-theme") === "dark"; const newTheme = isDark ? "light" : "dark"; root.setAttribute("data-theme", newTheme);
  localStorage.setItem("cw_theme", newTheme); $("#themeToggle")?.setAttribute("aria-pressed", !isDark); }
$("#themeToggle")?.addEventListener("click", toggleTheme);
// Initialize theme early
initTheme(); 