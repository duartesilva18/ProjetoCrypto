"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Line,
  LineChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";
import type { AnalyticsPoint, AnalyticsResponse } from "@/types/api";
import { TrendingUp, TrendingDown, Zap, Grid3X3, ArrowLeftRight, DollarSign } from "lucide-react";

const STRATEGY_CONFIG = {
  funding_arb: {
    label: "Funding Arb",
    color: "#10b981",
    icon: Zap,
  },
  grid: {
    label: "Grid Trading",
    color: "#f59e0b",
    icon: Grid3X3,
  },
  carry: {
    label: "Cash & Carry",
    color: "#3b82f6",
    icon: ArrowLeftRight,
  },
  total: {
    label: "Total",
    color: "#a855f7",
    icon: DollarSign,
  },
} as const;

const PERIODS = [
  { key: "daily", label: "Daily", days: 30 },
  { key: "daily", label: "7 Days", days: 7 },
  { key: "monthly", label: "Monthly", days: 365 },
  { key: "yearly", label: "Yearly", days: 365 },
] as const;

function formatPeriodLabel(iso: string, period: string): string {
  const d = new Date(iso);
  if (period === "yearly") return d.getFullYear().toString();
  if (period === "monthly") {
    return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  }
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function SummaryCard({
  strategy,
  value,
}: {
  strategy: keyof typeof STRATEGY_CONFIG;
  value: number;
}) {
  const config = STRATEGY_CONFIG[strategy];
  const Icon = config.icon;
  const isPositive = value >= 0;

  return (
    <Card className="group relative overflow-hidden transition-all duration-300 hover:border-zinc-700">
      <div className="relative p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              {config.label}
            </p>
            <p className={cn(
              "text-2xl font-bold tabular-nums",
              isPositive ? "text-emerald-400" : "text-red-400"
            )}>
              {formatCurrency(value)}
            </p>
            <div className="flex items-center gap-1">
              {isPositive ? (
                <TrendingUp className="h-3 w-3 text-emerald-400" />
              ) : (
                <TrendingDown className="h-3 w-3 text-red-400" />
              )}
              <span className={cn(
                "text-xs font-medium",
                isPositive ? "text-emerald-400" : "text-red-400"
              )}>
                {isPositive ? "Profit" : "Loss"}
              </span>
            </div>
          </div>
          <div
            className="flex h-10 w-10 items-center justify-center rounded-lg ring-1"
            style={{
              background: `${config.color}15`,
              borderColor: `${config.color}30`,
            }}
          >
            <Icon className="h-5 w-5" style={{ color: config.color }} />
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedPeriodIdx, setSelectedPeriodIdx] = useState(0);
  const [visibleLines, setVisibleLines] = useState<Record<string, boolean>>({
    funding_arb: true,
    grid: true,
    carry: true,
    total: true,
  });

  const selected = PERIODS[selectedPeriodIdx];

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    api
      .getAnalytics(selected.key, selected.days)
      .then((res) => {
        if (mounted) setAnalytics(res);
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => { mounted = false; };
  }, [selected.key, selected.days]);

  const chartData = useMemo(() => {
    if (!analytics?.data) return [];
    return analytics.data.map((point: AnalyticsPoint) => ({
      ...point,
      label: formatPeriodLabel(point.period, analytics.period),
    }));
  }, [analytics]);

  const toggleLine = (key: string) => {
    setVisibleLines((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">P&L Analytics</h2>
          <p className="text-sm text-zinc-500">
            Cumulative profit/loss by strategy over time
          </p>
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p, idx) => (
            <Button
              key={`${p.key}-${p.days}`}
              variant={selectedPeriodIdx === idx ? "default" : "ghost"}
              size="sm"
              onClick={() => setSelectedPeriodIdx(idx)}
              className={cn(
                "h-7 px-2.5 text-xs",
                selectedPeriodIdx === idx
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-500"
              )}
            >
              {p.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          strategy="funding_arb"
          value={analytics?.summary?.funding_arb ?? 0}
        />
        <SummaryCard
          strategy="grid"
          value={analytics?.summary?.grid ?? 0}
        />
        <SummaryCard
          strategy="carry"
          value={analytics?.summary?.carry ?? 0}
        />
        <SummaryCard
          strategy="total"
          value={analytics?.summary?.total ?? 0}
        />
      </div>

      {/* Combined line chart */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Cumulative P&L by Strategy</CardTitle>
          <div className="flex gap-2">
            {(Object.keys(STRATEGY_CONFIG) as (keyof typeof STRATEGY_CONFIG)[]).map((key) => (
              <button
                key={key}
                onClick={() => toggleLine(key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-all",
                  visibleLines[key]
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-600 hover:text-zinc-400"
                )}
              >
                <span
                  className="h-2 w-2 rounded-full"
                  style={{
                    backgroundColor: visibleLines[key]
                      ? STRATEGY_CONFIG[key].color
                      : "#52525b",
                  }}
                />
                {STRATEGY_CONFIG[key].label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex h-80 items-center justify-center">
              <Spinner />
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex h-80 items-center justify-center text-sm text-zinc-500">
              No analytics data yet. Let the bot run to accumulate P&L data.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={380}>
              <LineChart
                data={chartData}
                margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
              >
                <defs>
                  {Object.entries(STRATEGY_CONFIG).map(([key, cfg]) => (
                    <linearGradient key={key} id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={cfg.color} stopOpacity={0.8} />
                      <stop offset="100%" stopColor={cfg.color} stopOpacity={0.2} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="label"
                  stroke="#52525b"
                  tick={{ fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  stroke="#52525b"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: number) => formatCurrency(v, 0)}
                  axisLine={false}
                  tickLine={false}
                  width={70}
                />
                <Tooltip
                  contentStyle={{
                    background: "#18181b",
                    border: "1px solid #27272a",
                    borderRadius: "8px",
                    fontSize: "12px",
                    padding: "12px 16px",
                  }}
                  labelStyle={{ color: "#a1a1aa", marginBottom: "8px" }}
                  formatter={(value: number, name: string) => [
                    formatCurrency(value),
                    STRATEGY_CONFIG[name as keyof typeof STRATEGY_CONFIG]?.label ?? name,
                  ]}
                />
                <Legend
                  verticalAlign="top"
                  height={0}
                  content={() => null}
                />
                {visibleLines.funding_arb && (
                  <Line
                    type="monotone"
                    dataKey="funding_arb"
                    name="funding_arb"
                    stroke={STRATEGY_CONFIG.funding_arb.color}
                    strokeWidth={2.5}
                    dot={{ fill: STRATEGY_CONFIG.funding_arb.color, r: 3, strokeWidth: 0 }}
                    activeDot={{ r: 5, strokeWidth: 2, stroke: "#18181b" }}
                  />
                )}
                {visibleLines.grid && (
                  <Line
                    type="monotone"
                    dataKey="grid"
                    name="grid"
                    stroke={STRATEGY_CONFIG.grid.color}
                    strokeWidth={2.5}
                    dot={{ fill: STRATEGY_CONFIG.grid.color, r: 3, strokeWidth: 0 }}
                    activeDot={{ r: 5, strokeWidth: 2, stroke: "#18181b" }}
                  />
                )}
                {visibleLines.carry && (
                  <Line
                    type="monotone"
                    dataKey="carry"
                    name="carry"
                    stroke={STRATEGY_CONFIG.carry.color}
                    strokeWidth={2.5}
                    dot={{ fill: STRATEGY_CONFIG.carry.color, r: 3, strokeWidth: 0 }}
                    activeDot={{ r: 5, strokeWidth: 2, stroke: "#18181b" }}
                  />
                )}
                {visibleLines.total && (
                  <Line
                    type="monotone"
                    dataKey="total"
                    name="total"
                    stroke={STRATEGY_CONFIG.total.color}
                    strokeWidth={3}
                    strokeDasharray="6 3"
                    dot={false}
                    activeDot={{ r: 5, strokeWidth: 2, stroke: "#18181b" }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Individual strategy charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {(["funding_arb", "grid", "carry"] as const).map((strat) => {
          const config = STRATEGY_CONFIG[strat];
          return (
            <Card key={strat}>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <config.icon className="h-4 w-4" style={{ color: config.color }} />
                  <CardTitle className="text-sm">{config.label}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex h-48 items-center justify-center">
                    <Spinner />
                  </div>
                ) : chartData.length === 0 ? (
                  <div className="flex h-48 items-center justify-center text-xs text-zinc-600">
                    No data
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart
                      data={chartData}
                      margin={{ top: 4, right: 4, left: 4, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis
                        dataKey="label"
                        stroke="#52525b"
                        tick={{ fontSize: 9 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        stroke="#52525b"
                        tick={{ fontSize: 9 }}
                        tickFormatter={(v: number) =>
                          v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`
                        }
                        axisLine={false}
                        tickLine={false}
                        width={50}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#18181b",
                          border: "1px solid #27272a",
                          borderRadius: "8px",
                          fontSize: "11px",
                        }}
                        formatter={(value: number) => [
                          formatCurrency(value),
                          config.label,
                        ]}
                      />
                      <Line
                        type="monotone"
                        dataKey={strat}
                        stroke={config.color}
                        strokeWidth={2}
                        dot={{ fill: config.color, r: 2, strokeWidth: 0 }}
                        activeDot={{ r: 4, strokeWidth: 2, stroke: "#18181b" }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
