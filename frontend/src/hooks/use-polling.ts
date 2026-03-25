"use client";

import { useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";

export function usePolling(intervalMs = 10_000) {
  const token = useStore((s) => s.token);
  const setFundingRates = useStore((s) => s.setFundingRates);
  const setPnl = useStore((s) => s.setPnl);
  const setBotStatus = useStore((s) => s.setBotStatus);

  const poll = useCallback(async () => {
    if (!token) return;
    try {
      const [rates, pnl, status] = await Promise.allSettled([
        api.getFundingRates(),
        api.getPnl(),
        api.getBotStatus(),
      ]);

      if (rates.status === "fulfilled") setFundingRates(rates.value.rates);
      if (pnl.status === "fulfilled") setPnl(pnl.value);
      if (status.status === "fulfilled") setBotStatus(status.value.status);
    } catch {
      /* network errors are non-fatal */
    }
  }, [token, setFundingRates, setPnl, setBotStatus]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, intervalMs);
    return () => clearInterval(id);
  }, [poll, intervalMs]);
}
