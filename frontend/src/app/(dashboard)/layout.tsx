"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/dashboard/sidebar";
import { Header } from "@/components/dashboard/header";
import { useWebSocket } from "@/hooks/use-websocket";
import { usePolling } from "@/hooks/use-polling";
import { useStore } from "@/lib/store";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const token = useStore((s) => s.token);

  useEffect(() => {
    if (!token) router.push("/login");
  }, [token, router]);

  useWebSocket();
  usePolling(10_000);

  if (!token) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
