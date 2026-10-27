"use client";

import { createContext, useContext } from "react";
import type { Report } from "../../types";

export interface ReportActions {
  report: Report;
  verifiedOnly: boolean;
  openSource: (ref: number) => void;
  openCompetitor: (index: number) => void;
}

const Context = createContext<ReportActions | null>(null);

export const ReportProvider = Context.Provider;

/** The report and its shared actions (open a source or a competitor panel; verified-only filter). */
export function useReport(): ReportActions {
  const value = useContext(Context);
  if (!value) throw new Error("useReport must be used inside <ReportProvider>");
  return value;
}
