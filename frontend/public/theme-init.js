// Applies the saved or system colour theme before first paint (no flash).
try {
  const t = localStorage.getItem("rm-theme");
  if (t === "dark" || (!t && matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  }
} catch {}
