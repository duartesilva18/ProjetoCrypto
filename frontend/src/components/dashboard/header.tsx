"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { LogOut, Play, Square, OctagonX } from "lucide-react";

export function Header() {
  const router = useRouter();
  const setToken = useStore((s) => s.setToken);
  const botStatus = useStore((s) => s.botStatus);
  const setBotStatus = useStore((s) => s.setBotStatus);

  const status = botStatus?.status ?? "unknown";
  const isRunning = status === "running";

  async function handleStart() {
    await api.startBot();
    setBotStatus({ status: "running" });
  }

  async function handleStop() {
    await api.stopBot();
    setBotStatus({ status: "stopping" });
  }

  async function handleEmergency() {
    if (window.confirm("EMERGENCY STOP: This will immediately halt all trading. Continue?")) {
      await api.emergencyStop();
      setBotStatus({ status: "emergency_stopped" });
    }
  }

  function handleLogout() {
    setToken(null);
    router.push("/login");
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-zinc-800 bg-zinc-900/50 px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold text-white">Dashboard</h1>
        <Badge variant={isRunning ? "success" : "default"}>
          PAPER MODE
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        {isRunning ? (
          <Button variant="outline" size="sm" onClick={handleStop}>
            <Square className="h-3.5 w-3.5" />
            Stop
          </Button>
        ) : (
          <Button variant="primary" size="sm" onClick={handleStart}>
            <Play className="h-3.5 w-3.5" />
            Start
          </Button>
        )}

        <Button variant="destructive" size="sm" onClick={handleEmergency}>
          <OctagonX className="h-3.5 w-3.5" />
          E-Stop
        </Button>

        <div className="mx-2 h-6 w-px bg-zinc-800" />

        <Button variant="ghost" size="icon" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
