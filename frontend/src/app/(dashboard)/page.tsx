"use client";

import { useStore } from "@/lib/store";
import { formatCurrency } from "@/lib/utils";
import { StatCard } from "@/components/dashboard/stat-card";
import { EquityChart } from "@/components/charts/equity-chart";
import { FundingTable } from "@/components/dashboard/funding-table";
import { DollarSign, TrendingUp, Layers, Zap } from "lucide-react";

export default function OverviewPage() {
  const pnl = useStore((s) => s.pnl);
  const rates = useStore((s) => s.fundingRates);

  const dailyPnl = pnl?.funding_pnl.daily ?? 0;
  const weeklyPnl = pnl?.funding_pnl.weekly ?? 0;
  const openPositions = pnl?.positions.open ?? 0;
  const activeRates = Object.keys(rates).length;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          title="Open Positions"
          value={String(openPositions)}
          subtitle="Active hedges"
          icon={Layers}
          accentColor="purple"
        />
        <StatCard
          title="Tracked Rates"
          value={String(activeRates)}
          subtitle="Across exchanges"
          icon={Zap}
          accentColor="amber"
        />
      </div>

      {/* Equity Chart */}
      <EquityChart />

      {/* Live Funding Rates Table */}
      <FundingTable />
    </div>
  );
}
