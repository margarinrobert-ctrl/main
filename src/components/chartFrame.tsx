"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Shared chart capabilities applied across every graph: fullscreen expand (Esc to close) and a PNG
 * snapshot download. Auto-detects the chart's renderer inside the framed container — canvas
 * (lightweight-charts / the 3D surface) is captured directly; recharts SVG is serialized and rasterized.
 */

function downloadPng(container: HTMLElement | null, name: string) {
  if (!container) return;
  const canvasEl = container.querySelector("canvas");
  if (canvasEl) {
    const a = document.createElement("a");
    a.href = canvasEl.toDataURL("image/png");
    a.download = `${name}.png`;
    a.click();
    return;
  }
  const svg = container.querySelector("svg");
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("width", String(rect.width));
  clone.setAttribute("height", String(rect.height));
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const data = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([data], { type: "image/svg+xml;charset=utf-8" }));
  const img = new Image();
  img.onload = () => {
    const scale = 2;
    const c = document.createElement("canvas");
    c.width = Math.max(1, rect.width * scale);
    c.height = Math.max(1, rect.height * scale);
    const cx = c.getContext("2d");
    if (cx) {
      cx.fillStyle = "#07080c";
      cx.fillRect(0, 0, c.width, c.height);
      cx.scale(scale, scale);
      cx.drawImage(img, 0, 0);
      const a = document.createElement("a");
      a.href = c.toDataURL("image/png");
      a.download = `${name}.png`;
      a.click();
    }
    URL.revokeObjectURL(url);
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}

const iconBtn = "flex h-7 w-7 items-center justify-center rounded-md border border-white/10 bg-white/[0.03] text-neutral-400 transition hover:border-white/20 hover:text-neutral-100";

export function useChartFrame(name: string): { ref: React.RefObject<HTMLDivElement>; expanded: boolean; expandedClass: string; controls: ReactNode } {
  const ref = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  // Use the Fullscreen API: the element is promoted to the top layer, so it fills the screen regardless of
  // any transformed ancestor that would otherwise trap position:fixed in a containing block. Esc exits
  // natively. Falls back to a CSS-fixed expand only if the API is unavailable.
  useEffect(() => {
    const onChange = () => {
      setExpanded(document.fullscreenElement === ref.current);
      setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggle = () => {
    const el = ref.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => setExpanded(false));
      return;
    }
    if (el.requestFullscreen) {
      el.requestFullscreen().catch(() => setExpanded((v) => !v));
    } else {
      setExpanded((v) => !v); // no Fullscreen API → CSS fallback
    }
  };

  const controls = (
    <div className="flex items-center gap-1">
      <button type="button" onClick={() => downloadPng(ref.current, name.replace(/\s+/g, "-"))} className={iconBtn} title="Download PNG" aria-label="Download chart as PNG">
        <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5">
          <path fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" d="M8 2.5v7m0 0 2.5-2.5M8 9.5 5.5 7M3 12.5h10" />
        </svg>
      </button>
      <button type="button" onClick={toggle} className={iconBtn} title={expanded ? "Exit fullscreen (Esc)" : "Fullscreen"} aria-label={expanded ? "Exit fullscreen" : "Fullscreen"} aria-pressed={expanded}>
        {expanded ? (
          <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5">
            <path fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" d="M6 2v4H2m8 8v-4h4M6 14v-4H2m8-8v4h4" />
          </svg>
        ) : (
          <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5">
            <path fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" d="M2 6V2h4M14 6V2h-4M2 10v4h4m8-4v4h-4" />
          </svg>
        )}
      </button>
    </div>
  );

  // In real fullscreen the element is promoted to the top layer (fills the screen); these just add a solid
  // ground, scroll and padding. The fixed/inset are a harmless belt-and-suspenders for the no-API fallback.
  return { ref, expanded, expandedClass: expanded ? "fixed inset-0 z-50 overflow-auto p-5 sm:p-6 !bg-[#07080c] !rounded-none" : "", controls };
}
