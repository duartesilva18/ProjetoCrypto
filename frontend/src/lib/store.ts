import { create } from "zustand";
import type { BotStatus, FundingRateEntry, PnlSummary } from "@/types/api";

interface DashboardState {
  token: string | null;
  botStatus: BotStatus | null;
  fundingRates: Record<string, FundingRateEntry>;
  pnl: PnlSummary | null;
  wsConnected: boolean;

  setToken: (token: string | null) => void;
  setBotStatus: (status: BotStatus) => void;
  setFundingRates: (rates: Record<string, FundingRateEntry>) => void;
  setPnl: (pnl: PnlSummary) => void;
  setWsConnected: (connected: boolean) => void;
}

export const useStore = create<DashboardState>((set) => ({
  token: typeof window !== "undefined" ? localStorage.getItem("token") : null,
  botStatus: null,
  fundingRates: {},
  pnl: null,
  wsConnected: false,

  setToken: (token) => {
    if (typeof window !== "undefined") {
      if (token) localStorage.setItem("token", token);
      else localStorage.removeItem("token");
    }
    set({ token });
  },
  setBotStatus: (botStatus) => set({ botStatus }),
  setFundingRates: (fundingRates) => set({ fundingRates }),
  setPnl: (pnl) => set({ pnl }),
  setWsConnected: (wsConnected) => set({ wsConnected }),
}));
