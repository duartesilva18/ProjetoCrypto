import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number, decimals = 2): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatPercent(value: number, decimals = 4): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatRate(rateStr: string): string {
  const rate = parseFloat(rateStr);
  if (isNaN(rate)) return "—";
  return formatPercent(rate);
}

export function formatTimeAgo(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const seconds = Math.floor((now - then) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function formatCountdown(seconds: number | string): string {
  const s = typeof seconds === "string" ? parseFloat(seconds) : seconds;
  if (isNaN(s) || s <= 0) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "running":
      return "text-emerald-400";
    case "stopping":
      return "text-amber-400";
    case "stopped":
    case "emergency_stopped":
      return "text-red-400";
    case "idle":
      return "text-zinc-400";
    default:
      return "text-zinc-500";
  }
}
