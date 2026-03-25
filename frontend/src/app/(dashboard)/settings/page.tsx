"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useStore } from "@/lib/store";
import { cn, statusColor } from "@/lib/utils";
import { Save, Shield, Sliders, Activity } from "lucide-react";

interface ConfigField {
  key: string;
  label: string;
  description: string;
  defaultValue: string;
}

const configFields: ConfigField[] = [
  {
    key: "funding_rate_entry_threshold",
    label: "Entry Threshold",
    description: "Minimum funding rate to open a position (e.g. 0.0001 = 0.01%)",
    defaultValue: "0.0001",
  },
  {
    key: "funding_rate_exit_threshold",
    label: "Exit Threshold",
    description: "Close position when rate drops below this",
    defaultValue: "0.00005",
  },
  {
    key: "min_opportunity_score",
    label: "Min Score",
    description: "Minimum opportunity score (0-1) to trigger entry",
    defaultValue: "0.5",
  },
  {
    key: "max_exposure_per_exchange",
    label: "Max Exposure / Exchange",
    description: "Maximum capital % allocated to one exchange",
    defaultValue: "0.30",
  },
  {
    key: "max_exposure_per_pair",
    label: "Max Exposure / Pair",
    description: "Maximum capital % allocated to one trading pair",
    defaultValue: "0.10",
  },
  {
    key: "max_daily_drawdown",
    label: "Max Daily Drawdown",
    description: "Soft limit — triggers caution mode",
    defaultValue: "0.02",
  },
];

export default function SettingsPage() {
  const botStatus = useStore((s) => s.botStatus);
  const status = botStatus?.status ?? "unknown";

  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(configFields.map((f) => [f.key, f.defaultValue]))
  );
  const [saved, setSaved] = useState(false);

  function handleChange(key: string, value: string) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl">
      <div>
        <h2 className="text-lg font-semibold text-white">Settings</h2>
        <p className="text-sm text-zinc-500">
          Configure strategy parameters and risk limits
        </p>
      </div>

      {/* System Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            System Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-zinc-500">Bot</p>
              <p className={cn("mt-1 text-sm font-medium capitalize", statusColor(status))}>
                {status}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-zinc-500">Mode</p>
              <Badge variant="info" className="mt-1">PAPER</Badge>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-zinc-500">Exchanges</p>
              <div className="mt-1 flex gap-1">
                <Badge>Binance</Badge>
                <Badge>Bybit</Badge>
                <Badge>OKX</Badge>
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-zinc-500">Pairs</p>
              <p className="mt-1 text-sm text-zinc-300 font-mono">BTC, ETH, SOL</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Strategy Config */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sliders className="h-4 w-4" />
            Strategy Parameters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 sm:grid-cols-2">
            {configFields.slice(0, 3).map((field) => (
              <div key={field.key}>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {field.label}
                </label>
                <Input
                  type="text"
                  value={values[field.key]}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                />
                <p className="mt-1 text-xs text-zinc-600">{field.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Risk Config */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Risk Limits
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 sm:grid-cols-2">
            {configFields.slice(3).map((field) => (
              <div key={field.key}>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-500">
                  {field.label}
                </label>
                <Input
                  type="text"
                  value={values[field.key]}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                />
                <p className="mt-1 text-xs text-zinc-600">{field.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Save */}
      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={handleSave}>
          <Save className="h-4 w-4" />
          Save Configuration
        </Button>
        {saved && (
          <span className="animate-fade-in text-sm text-emerald-400">
            Configuration saved
          </span>
        )}
      </div>
    </div>
  );
}
