"use client";

import { useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import { formatCurrency } from "@/lib/utils";
import { StatCard } from "@/components/dashboard/stat-card";
import { EquityChart } from "@/components/charts/equity-chart";
import { FundingTable } from "@/components/dashboard/funding-table";
import { api } from "@/lib/api";
import type { Position } from "@/types/api";
import { DollarSign, TrendingUp, Layers, Zap, Grid3X3, ArrowLeftRight } from "lucide-react";

export default function OverviewPage() {
  const pnl = useStore((s) => s.pnl);
  const rates = useStore((s) => s.fundingRates);
  const [positions, setPositions] = useState<Position[]>([]);

  const dailyPnl = pnl?.funding_pnl.daily ?? 0;
  const weeklyPnl = pnl?.funding_pnl.weekly ?? 0;
  const activeRates = Object.keys(rates).length;

  useEffect(() => {
    api.getPositions({ status: "OPEN" })
      .then((res) => setPositions(res.data))
      .catch(() => {});
    const interval = setInterval(() => {
      api.getPositions({ status: "OPEN" })
        .then((res) => setPositions(res.data))
        .catch(() => {});
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  const fundingCount = positions.filter((p) => !p.strategy || p.strategy === "funding_arb").length;
  const gridCount = positions.filter((p) => p.strategy === "grid").length;
  const carryCount = positions.filter((p) => p.strategy === "carry").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          title="Daily P&L"
          value={formatCurrency(dailyPnl)}
          subtitle={dailyPnl >= 0 ? "Profitable" : "Loss"}
          trend={dailyPnl >= 0 ? "up" : "down"}
          icon={DollarSign}
          accentColor="emerald"
        />
        <StatCard
          title="Weekly P&L"
          value={formatCurrency(weeklyPnl)}
          subtitle={weeklyPnl >= 0 ? "Profitable" : "Loss"}
          trend={weeklyPnl >= 0 ? "up" : "down"}
          icon={TrendingUp}
          accentColor="blue"
        />
        <StatCard
          title="Funding Arb"
          value={String(fundingCount)}
          subtitle="Funding rate positions"
          icon={Zap}
          accentColor="emerald"
        />
        <StatCard
          title="Grid Trading"
          value={String(gridCount)}
          subtitle="Grid positions"
          icon={Grid3X3}
          accentColor="amber"
        />
        <StatCard
          title="Cash & Carry"
          value={String(carryCount)}
          subtitle="Premium arb positions"
          icon={ArrowLeftRight}
          accentColor="blue"
        />
        <StatCard
          title="Tracked Rates"
          value={String(activeRates)}
          subtitle="Across 4 exchanges"
          icon={Layers}
          accentColor="purple"
        />
      </div>

      <EquityChart />

      <FundingTable />
    </div>
  );
}
