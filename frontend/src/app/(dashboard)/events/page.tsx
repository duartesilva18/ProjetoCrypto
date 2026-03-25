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
import type { BotEvent } from "@/types/api";
import { Filter, RefreshCw } from "lucide-react";

const levelVariant = (level: string) => {
  switch (level) {
    case "CRITICAL":
    case "ERROR":
      return "danger" as const;
    case "WARNING":
      return "warning" as const;
    case "INFO":
      return "info" as const;
    default:
      return "default" as const;
  }
};

const levels = ["ALL", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] as const;

export default function EventsPage() {
  const [events, setEvents] = useState<BotEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>("ALL");

  function fetchEvents() {
    setLoading(true);
    const params: Record<string, string> = { limit: "200" };
    if (levelFilter !== "ALL") params.level = levelFilter;

    api
      .getEvents(params)
      .then((res) => setEvents(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    fetchEvents();
  }, [levelFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Bot Events</h2>
          <p className="text-sm text-zinc-500">
            {events.length} event{events.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-zinc-500" />
          {levels.map((l) => (
            <Button
              key={l}
              variant={levelFilter === l ? "default" : "ghost"}
              size="sm"
              onClick={() => setLevelFilter(l)}
              className="h-7 text-xs"
            >
              {l}
            </Button>
          ))}
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchEvents}
            className="h-7 w-7"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner />
        </div>
      ) : events.length === 0 ? (
        <Card>
          <CardContent className="flex h-48 items-center justify-center text-sm text-zinc-500">
            No events found.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Event Log</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {events.map((event) => (
                <div
                  key={event.id}
                  className="flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-zinc-800/30"
                >
                  <Badge variant={levelVariant(event.level)} className="mt-0.5 shrink-0">
                    {event.level}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-zinc-400">
                        [{event.component}]
                      </span>
                      <span className="text-sm text-zinc-200">
                        {event.message}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-600 font-mono">
                      {new Date(event.timestamp).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
