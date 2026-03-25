"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";
import type { EquityPoint } from "@/types/api";

const periods = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
] as const;

export function EquityChart() {
  const [data, setData] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPeriod, setSelectedPeriod] = useState(24);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    api
      .getEquityCurve(selectedPeriod)
      .then((res) => {
        if (mounted) setData(res.data);
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => { mounted = false; };
  }, [selectedPeriod]);

  return (
    <Card className="col-span-full">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Equity Curve</CardTitle>
        <div className="flex gap-1">
          {periods.map((p) => (
            <Button
              key={p.hours}
              variant={selectedPeriod === p.hours ? "default" : "ghost"}
              size="sm"
              onClick={() => setSelectedPeriod(p.hours)}
              className={cn(
                "h-7 px-2.5 text-xs",
                selectedPeriod === p.hours
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-500"
              )}
            >
              {p.label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Spinner />
          </div>
        ) : data.length === 0 ? (
          <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
            No equity data yet. Start the bot to begin tracking.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart
              data={data}
              margin={{ top: 4, right: 4, left: 4, bottom: 0 }}
            >
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="fundingGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v: string) =>
                  new Date(v).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }
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
                }}
                labelFormatter={(v: string) =>
                  new Date(v).toLocaleString()
                }
                formatter={(value: number, name: string) => [
                  formatCurrency(value),
                  name === "total_equity"
                    ? "Total Equity"
                    : name === "funding_pnl"
                      ? "Funding P&L"
                      : name,
                ]}
              />
              <Area
                type="monotone"
                dataKey="total_equity"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#equityGrad)"
              />
              <Area
                type="monotone"
                dataKey="funding_pnl"
                stroke="#6366f1"
                strokeWidth={1.5}
                fill="url(#fundingGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
