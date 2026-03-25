"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { formatCurrency, formatTimeAgo } from "@/lib/utils";
import type { Position } from "@/types/api";
import { Filter } from "lucide-react";

const statusVariant = (s: string) => {
  switch (s) {
    case "OPEN":
      return "success" as const;
    case "CLOSING":
      return "warning" as const;
    case "CLOSED":
      return "default" as const;
    default:
      return "default" as const;
  }
};

const strategyLabel = (s?: string) => {
  switch (s) {
    case "grid":
      return { label: "GRID", variant: "warning" as const, color: "text-amber-400" };
    case "carry":
      return { label: "CARRY", variant: "info" as const, color: "text-blue-400" };
    case "funding_arb":
    default:
      return { label: "FUNDING", variant: "success" as const, color: "text-emerald-400" };
  }
};

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    const params: Record<string, string> = {};
    if (filter) params.status = filter;

    api
      .getPositions(params)
      .then((res) => {
        if (mounted) {
          let data = res.data;
          if (strategyFilter) {
            data = data.filter((p) => (p.strategy || "funding_arb") === strategyFilter);
          }
          setPositions(data);
          setTotal(res.total);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => { mounted = false; };
  }, [filter, strategyFilter]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Positions</h2>
          <p className="text-sm text-zinc-500">
            {positions.length} position{positions.length !== 1 ? "s" : ""} shown
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-zinc-500" />
            {["OPEN", "CLOSED", null].map((f) => (
              <Button
                key={f ?? "all"}
                variant={filter === f ? "default" : "ghost"}
                size="sm"
                onClick={() => setFilter(f)}
                className="h-7 text-xs"
              >
                {f ?? "All"}
              </Button>
            ))}
          </div>
          <div className="h-4 w-px bg-zinc-700" />
          <div className="flex items-center gap-1">
            {[
              { key: null, label: "All" },
              { key: "funding_arb", label: "Funding" },
              { key: "grid", label: "Grid" },
              { key: "carry", label: "Carry" },
            ].map((s) => (
              <Button
                key={s.key ?? "all-strat"}
                variant={strategyFilter === s.key ? "default" : "ghost"}
                size="sm"
                onClick={() => setStrategyFilter(s.key)}
                className="h-7 text-xs"
              >
                {s.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner />
        </div>
      ) : positions.length === 0 ? (
        <Card>
          <CardContent className="flex h-48 items-center justify-center text-sm text-zinc-500">
            No positions found.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {positions.map((pos) => (
            <Card
              key={pos.id}
              className="transition-all duration-200 hover:border-zinc-700"
            >
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-base text-white normal-case">
                    {pos.symbol}
                  </CardTitle>
                  <Badge variant="default">{pos.exchange}</Badge>
                  <Badge variant={strategyLabel(pos.strategy).variant}>
                    {strategyLabel(pos.strategy).label}
                  </Badge>
                  <Badge variant={statusVariant(pos.status)}>
                    {pos.status}
                  </Badge>
                  {pos.is_paper && (
                    <Badge variant="info">PAPER</Badge>
                  )}
                </div>
                {pos.opened_at && (
                  <span className="text-xs text-zinc-500">
                    {formatTimeAgo(pos.opened_at)}
                  </span>
                )}
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
                  <Metric
                    label="Strategy"
                    value={strategyLabel(pos.strategy).label}
                    color={strategyLabel(pos.strategy).color}
                  />
                  <Metric
                    label="Side"
                    value={
                      pos.side === "GRID"
                        ? "Grid (Buy & Sell)"
                        : pos.side === "LONG_SPOT_SHORT_PERP"
                          ? "Long Spot / Short Perp"
                          : "Short Spot / Long Perp"
                    }
                  />
                  <Metric label="Spot Qty" value={pos.spot_qty.toFixed(6)} />
                  {pos.strategy === "grid" ? (
                    <Metric
                      label="Grid Range"
                      value={`$${(pos.grid_low ?? 0).toFixed(2)} - $${(pos.grid_high ?? 0).toFixed(2)}`}
                    />
                  ) : (
                    <Metric
                      label="Entry (Spot)"
                      value={formatCurrency(pos.entry_price_spot)}
                    />
                  )}
                  {pos.strategy === "carry" ? (
                    <Metric
                      label="Premium"
                      value={`${(pos.entry_premium_bps ?? 0).toFixed(1)} bps`}
                    />
                  ) : (
                    <Metric
                      label="Entry (Perp)"
                      value={formatCurrency(pos.entry_price_perp)}
                    />
                  )}
                  <Metric
                    label={pos.strategy === "grid" ? "Grid Profit" : pos.strategy === "carry" ? "Carry Profit" : "Funding Collected"}
                    value={formatCurrency(pos.funding_collected)}
                    highlight
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  highlight = false,
  color,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  color?: string;
}) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </p>
      <p
        className={`mt-0.5 text-sm font-mono ${
          color ? `font-semibold ${color}` : highlight ? "font-semibold text-emerald-400" : "text-zinc-200"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
