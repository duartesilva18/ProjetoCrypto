"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useStore } from "@/lib/store";
import { formatRate, formatCountdown } from "@/lib/utils";

export function FundingTable() {
  const rates = useStore((s) => s.fundingRates);
  const entries = Object.entries(rates).sort((a, b) => {
    const rateA = Math.abs(parseFloat(a[1].funding_rate || "0"));
    const rateB = Math.abs(parseFloat(b[1].funding_rate || "0"));
    return rateB - rateA;
  });

  return (
    <Card className="col-span-full">
      <CardHeader>
        <CardTitle>Live Funding Rates</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="py-8 text-center text-sm text-zinc-500">
            Waiting for funding rate data...
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
                  <th className="pb-3 pr-4">Exchange</th>
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4 text-right">Current Rate</th>
                  <th className="pb-3 pr-4 text-right">Predicted</th>
                  <th className="pb-3 pr-4 text-right">Mark Price</th>
                  <th className="pb-3 text-right">Next Funding</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {entries.map(([key, rate]) => {
                  const fundingRate = parseFloat(rate.funding_rate || "0");
                  const isPositive = fundingRate > 0;
                  return (
                    <tr
                      key={key}
                      className="transition-colors hover:bg-zinc-800/30"
                    >
                      <td className="py-3 pr-4">
                        <Badge variant="default">{rate.exchange}</Badge>
                      </td>
                      <td className="py-3 pr-4 font-mono font-medium text-white">
                        {rate.symbol}
                      </td>
                      <td className="py-3 pr-4 text-right font-mono">
                        <span
                          className={
                            isPositive ? "text-emerald-400" : "text-red-400"
                          }
                        >
                          {formatRate(rate.funding_rate)}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-right font-mono text-zinc-400">
                        {rate.predicted_rate
                          ? formatRate(rate.predicted_rate)
                          : "—"}
                      </td>
                      <td className="py-3 pr-4 text-right font-mono text-zinc-300">
                        {rate.mark_price
                          ? `$${parseFloat(rate.mark_price).toLocaleString()}`
                          : "—"}
                      </td>
                      <td className="py-3 text-right font-mono text-zinc-400">
                        {rate.time_to_funding_s
                          ? formatCountdown(rate.time_to_funding_s)
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
