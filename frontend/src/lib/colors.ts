import { useEffect, useState } from "react";

const NAMES = ["critical", "high", "medium", "low", "info", "none"] as const;
type Name = (typeof NAMES)[number];

function read(): Record<Name | "ink3" | "line" | "ok", string> {
  const css = getComputedStyle(document.documentElement);
  const out = {} as Record<Name | "ink3" | "line" | "ok", string>;
  for (const n of NAMES) out[n] = css.getPropertyValue(`--sev-${n}`).trim();
  out.ink3 = css.getPropertyValue("--ink-3").trim();
  out.line = css.getPropertyValue("--line").trim();
  out.ok = css.getPropertyValue("--ok").trim();
  return out;
}

/** Resolved severity colours for chart libraries that need literal values; follows theme changes. */
export function useChartColors() {
  const [colors, setColors] = useState(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setColors(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return colors;
}
