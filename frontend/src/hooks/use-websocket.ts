"use client";

import { useEffect, useRef } from "react";
import { useStore } from "@/lib/store";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const setWsConnected = useStore((s) => s.setWsConnected);
  const setBotStatus = useStore((s) => s.setBotStatus);
  const setFundingRates = useStore((s) => s.setFundingRates);
  const currentRates = useStore((s) => s.fundingRates);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      const ws = new WebSocket(`${WS_URL}/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        ws.send(
          JSON.stringify({
            subscribe: ["funding_rates", "bot_status", "positions"],
          })
        );
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(
            typeof event.data === "string"
              ? event.data
              : new TextDecoder().decode(event.data)
          );

          if (data.status) {
            setBotStatus(data);
          } else if (data.type === "funding" && data.exchange && data.symbol) {
            const key = `${data.exchange}:${data.symbol}`;
            setFundingRates({ ...currentRates, [key]: data });
          }
        } catch {
          /* ignore malformed messages */
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        if (!destroyed) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      destroyed = true;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
