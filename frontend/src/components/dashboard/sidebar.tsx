"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn, statusColor } from "@/lib/utils";
import { useStore } from "@/lib/store";
import {
  Activity,
  BarChart3,
  Layers,
  LineChart,
  ScrollText,
  Settings,
  Wifi,
  WifiOff,
} from "lucide-react";

const navigation = [
  { name: "Overview", href: "/", icon: BarChart3 },
  { name: "Analytics", href: "/analytics", icon: LineChart },
  { name: "Positions", href: "/positions", icon: Layers },
  { name: "Events", href: "/events", icon: ScrollText },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const botStatus = useStore((s) => s.botStatus);
  const wsConnected = useStore((s) => s.wsConnected);

  const statusText = botStatus?.status ?? "unknown";

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-zinc-800 bg-zinc-900/50">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-zinc-800 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600/10 ring-1 ring-emerald-600/30">
          <Activity className="h-4 w-4 text-emerald-400" />
        </div>
        <div>
          <span className="text-sm font-bold text-white">ProjetoCrypto</span>
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">
            Multi-Strategy Bot
          </p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Status footer */}
      <div className="border-t border-zinc-800 p-4 space-y-3">
        {/* Bot status */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500">Bot Status</span>
          <div className="flex items-center gap-1.5">
            <div
              className={cn(
                "h-2 w-2 rounded-full",
                statusText === "running"
                  ? "bg-emerald-400 animate-pulse-glow"
                  : statusText === "stopping"
                    ? "bg-amber-400"
                    : "bg-zinc-600"
              )}
            />
            <span
              className={cn(
                "text-xs font-medium capitalize",
                statusColor(statusText)
              )}
            >
              {statusText}
            </span>
          </div>
        </div>

        {/* WS connection */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500">WebSocket</span>
          <div className="flex items-center gap-1.5">
            {wsConnected ? (
              <Wifi className="h-3 w-3 text-emerald-400" />
            ) : (
              <WifiOff className="h-3 w-3 text-red-400" />
            )}
            <span
              className={cn(
                "text-xs",
                wsConnected ? "text-emerald-400" : "text-red-400"
              )}
            >
              {wsConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}
