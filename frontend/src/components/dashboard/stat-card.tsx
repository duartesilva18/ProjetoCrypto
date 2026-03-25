import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  accentColor?: string;
}

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  accentColor = "emerald",
}: StatCardProps) {
  const colorMap: Record<string, string> = {
    emerald: "from-emerald-600/10 ring-emerald-600/20 text-emerald-400",
    blue: "from-blue-600/10 ring-blue-600/20 text-blue-400",
    amber: "from-amber-600/10 ring-amber-600/20 text-amber-400",
    purple: "from-purple-600/10 ring-purple-600/20 text-purple-400",
  };

  const trendColor =
    trend === "up"
      ? "text-emerald-400"
      : trend === "down"
        ? "text-red-400"
        : "text-zinc-500";

  return (
    <Card className="group relative overflow-hidden transition-all duration-300 hover:border-zinc-700">
      <div
        className={cn(
          "absolute inset-0 bg-gradient-to-br opacity-0 transition-opacity duration-300 group-hover:opacity-100",
          colorMap[accentColor]?.split(" ")[0] ?? "from-emerald-600/10"
        )}
      />
      <div className="relative p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              {title}
            </p>
            <p className="text-2xl font-bold tabular-nums text-white">
              {value}
            </p>
            {subtitle && (
              <p className={cn("text-xs font-medium", trendColor)}>
                {subtitle}
              </p>
            )}
          </div>
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br ring-1",
              colorMap[accentColor] ?? colorMap.emerald
            )}
          >
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </div>
    </Card>
  );
}
