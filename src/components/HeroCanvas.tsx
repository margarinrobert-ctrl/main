"use client";

import { useEffect, useRef } from "react";

/**
 * Animated hero backdrop: a living dealer-gamma landscape.
 * Layers — perspective floor grid · diverging call/put gamma bars · glowing net-gamma
 * curve with a traveling spot marker · sparse rising/falling flow prints.
 * Power-conscious: ~30fps cap, pauses off-screen & when the tab is hidden,
 * renders a single static frame under prefers-reduced-motion.
 */
export function HeroCanvas({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let visible = true;
    let last = 0;
    let w = 0;
    let h = 0;

    const N = 46; // gamma bars across the width
    const seeds = Array.from({ length: N }, (_, i) => ({
      // Deterministic pseudo-random per strike (stable across resizes).
      a: Math.sin(i * 12.9898) * 43758.5453 % 1,
      b: Math.sin(i * 78.233) * 12543.2634 % 1,
    }));
    const prints = Array.from({ length: 26 }, (_, i) => ({
      x: (Math.abs(Math.sin(i * 91.7)) * 1000) % 1,
      y: (Math.abs(Math.sin(i * 47.3)) * 1000) % 1,
      s: 0.4 + ((Math.abs(Math.sin(i * 13.1)) * 1000) % 1) * 0.8,
      up: i % 3 !== 0,
    }));

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);
      const horizon = h * 0.30;
      const floor = h * 0.86;

      // ── Perspective floor grid, drifting toward the viewer ──
      ctx.lineWidth = 1;
      const rows = 9;
      const drift = reduced ? 0 : (t * 0.02) % 1;
      for (let r = 0; r <= rows; r++) {
        const p = (r + drift) / rows;
        const y = horizon + (floor - horizon) * p * p; // ease — lines bunch at horizon
        ctx.strokeStyle = `rgba(255,255,255,${0.012 + p * 0.035})`;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      const cols = 16;
      for (let c = 0; c <= cols; c++) {
        const p = c / cols;
        const xTop = w * (0.5 + (p - 0.5) * 0.72);
        const xBot = w * (0.5 + (p - 0.5) * 1.25);
        const g = ctx.createLinearGradient(0, horizon, 0, floor);
        g.addColorStop(0, "rgba(255,255,255,0)");
        g.addColorStop(1, "rgba(255,255,255,0.045)");
        ctx.strokeStyle = g;
        ctx.beginPath();
        ctx.moveTo(xTop, horizon);
        ctx.lineTo(xBot, floor);
        ctx.stroke();
      }

      // ── Diverging gamma bars along a mid axis ──
      const axis = h * 0.62;
      const bw = w / N;
      const curve: [number, number][] = [];
      for (let i = 0; i < N; i++) {
        const x = i * bw + bw / 2;
        const u = i / (N - 1);
        // Twin-peaked gamma landscape: put wall left, call wall right.
        const callPeak = Math.exp(-((u - 0.68) ** 2) / 0.012);
        const putPeak = Math.exp(-((u - 0.34) ** 2) / 0.02);
        const wob = reduced ? 0.5 : 0.5 + 0.5 * Math.sin(t * 0.6 + seeds[i].a * 12);
        const call = callPeak * (0.55 + 0.45 * wob) * h * 0.20;
        const put = putPeak * (0.55 + 0.45 * (1 - wob)) * h * 0.16;
        if (call > 1.2) {
          ctx.fillStyle = `rgba(52,211,153,${0.05 + (call / (h * 0.2)) * 0.16})`;
          ctx.fillRect(x - bw * 0.26, axis - call, bw * 0.52, call);
        }
        if (put > 1.2) {
          ctx.fillStyle = `rgba(248,113,113,${0.04 + (put / (h * 0.16)) * 0.12})`;
          ctx.fillRect(x - bw * 0.26, axis, bw * 0.52, put);
        }
        curve.push([x, axis - call + put * 0.55]);
      }

      // Axis hairline
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.beginPath();
      ctx.moveTo(0, axis);
      ctx.lineTo(w, axis);
      ctx.stroke();

      // ── Net-gamma curve (emerald→cyan, soft glow) ──
      const grad = ctx.createLinearGradient(0, 0, w, 0);
      grad.addColorStop(0, "rgba(52,211,153,0.55)");
      grad.addColorStop(1, "rgba(34,211,238,0.55)");
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.6;
      ctx.shadowColor = "rgba(52,211,153,0.5)";
      ctx.shadowBlur = 10;
      ctx.beginPath();
      curve.forEach(([x, y], i) => {
        if (i === 0) ctx.moveTo(x, y);
        else {
          const [px, py] = curve[i - 1];
          ctx.quadraticCurveTo(px, py, (px + x) / 2, (py + y) / 2);
        }
      });
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Traveling spot marker on the curve
      const mu = reduced ? 0.52 : 0.5 + 0.42 * Math.sin(t * 0.22);
      const mi = Math.min(N - 1, Math.max(0, Math.round(mu * (N - 1))));
      const [mx, my] = curve[mi];
      ctx.fillStyle = "rgba(250,250,250,0.9)";
      ctx.shadowColor = "rgba(52,211,153,0.9)";
      ctx.shadowBlur = 12;
      ctx.beginPath();
      ctx.arc(mx, my, 2.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      // ── Sparse flow prints drifting vertically ──
      for (const p of prints) {
        const cycle = reduced ? 0.5 : ((t * 0.05 * p.s + p.y) % 1);
        const y = h * (p.up ? 1 - cycle : cycle);
        const alpha = Math.sin(cycle * Math.PI) * 0.22;
        ctx.fillStyle = p.up ? `rgba(52,211,153,${alpha})` : `rgba(248,113,113,${alpha * 0.8})`;
        ctx.beginPath();
        ctx.arc(w * p.x, y, p.s, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      if (now - last < 33) return; // ~30fps is plenty for ambience
      last = now;
      draw(now / 1000);
    };

    resize();
    const ro = new ResizeObserver(() => {
      resize();
      draw(performance.now() / 1000);
    });
    ro.observe(canvas);

    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
    });
    io.observe(canvas);

    if (reduced) {
      draw(0); // single static frame
    } else {
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={`pointer-events-none ${className}`} />;
}
