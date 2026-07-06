"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { withBase } from "@/lib/paths";

const TICKERS = ["SPY", "QQQ", "NVDA", "TSLA"];

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  const p = pathname.replace(/\/$/, "");
  const h = href.replace(/\/$/, "");
  return h === "" ? p === "" : p.endsWith(h);
}

/** Desktop nav + mobile sheet with active-route awareness. */
export function NavLinks() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the mobile sheet on navigation and lock body scroll while open.
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const linkCls = (active: boolean) =>
    `rounded-lg px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wider transition ${
      active ? "bg-accent/10 text-accent-bright" : "text-neutral-400 hover:bg-white/5 hover:text-neutral-100"
    }`;

  const links = (
    <>
      <a href={withBase("/live")} className={`flex items-center gap-2 ${linkCls(isActive(pathname, "/live"))}`}>
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/70" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-400" />
        </span>
        Live
      </a>
      {TICKERS.map((s) => (
        <a key={s} href={withBase(`/ticker/${s}`)} className={linkCls(isActive(pathname, `/ticker/${s}`))}>
          {s}
        </a>
      ))}
    </>
  );

  return (
    <>
      <nav aria-label="Primary" className="hidden items-center gap-0.5 md:flex">
        {links}
      </nav>

      {/* Mobile trigger */}
      <button
        type="button"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] text-neutral-300 transition hover:border-white/20 hover:text-white md:hidden"
      >
        <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4">
          {open ? (
            <path stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="m3 3 10 10M13 3 3 13" />
          ) : (
            <path stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" d="M2 4.5h12M2 8h12M2 11.5h12" />
          )}
        </svg>
      </button>

      {/* Mobile sheet */}
      {open && (
        <div className="fixed inset-x-0 top-[57px] z-30 border-b border-white/10 bg-[#07080c]/95 backdrop-blur-xl md:hidden">
          <nav aria-label="Primary mobile" className="mx-auto grid max-w-7xl gap-1 px-5 py-4">
            <a
              href={withBase("/")}
              className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition ${isActive(pathname, "") ? "bg-accent/10 text-accent-bright" : "text-neutral-300 hover:bg-white/5"}`}
            >
              Overview
            </a>
            <a
              href={withBase("/live")}
              className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition ${isActive(pathname, "/live") ? "bg-accent/10 text-accent-bright" : "text-neutral-300 hover:bg-white/5"}`}
            >
              Live tape
            </a>
            <div className="lbl px-3 pb-1 pt-3">Terminals</div>
            <div className="grid grid-cols-2 gap-1">
              {TICKERS.map((s) => (
                <a
                  key={s}
                  href={withBase(`/ticker/${s}`)}
                  className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                    isActive(pathname, `/ticker/${s}`) ? "bg-accent/10 text-accent-bright" : "text-neutral-300 hover:bg-white/5"
                  }`}
                >
                  {s}
                </a>
              ))}
            </div>
          </nav>
        </div>
      )}
    </>
  );
}
