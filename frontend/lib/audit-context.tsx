"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api, uploadArchive } from "./api";
import type { Job, Overview, Summary } from "./types";

const STORAGE_KEY = "imageaudit.activeAudit";

interface AuditContextValue {
  audits: Summary[];
  auditsError: Error | null;
  activeId: string | null;
  overview: Overview | null;
  overviewLoading: boolean;
  overviewError: Error | null;
  job: Job | null;
  uploadFraction: number | null;
  select: (id: string | null) => void;
  scanPath: (path: string, mode?: "scan" | "validate") => Promise<void>;
  scanUpload: (file: File) => Promise<void>;
  cancelJob: () => Promise<void>;
  dismissJob: () => void;
  removeAudit: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
  startError: Error | null;
}

const Ctx = createContext<AuditContextValue | null>(null);

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage can be unavailable (private mode); this is only a convenience
  }
}

function writeStored(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function AuditProvider({ children }: { children: ReactNode }) {
  const [audits, setAudits] = useState<Summary[]>([]);
  const [auditsError, setAuditsError] = useState<Error | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<Error | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [uploadFraction, setUploadFraction] = useState<number | null>(null);
  const [startError, setStartError] = useState<Error | null>(null);
  const initialised = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const list = await api.audits();
      setAudits(list);
      setAuditsError(null);
      setActiveId((cur) => {
        if (cur && list.some((a) => a.id === cur)) return cur;
        const stored = readStored();
        if (stored && list.some((a) => a.id === stored)) return stored;
        return list[0]?.id ?? null;
      });
    } catch (e) {
      setAuditsError(e instanceof Error ? e : new Error(String(e)));
    }
  }, []);

  useEffect(() => {
    if (initialised.current) return;
    initialised.current = true;
    void refresh();
  }, [refresh]);

  useEffect(() => {
    writeStored(activeId);
    if (!activeId) {
      setOverview(null);
      return;
    }
    let cancelled = false;
    setOverviewLoading(true);
    setOverviewError(null);
    api
      .audit(activeId)
      .then((o) => !cancelled && setOverview(o))
      .catch((e: unknown) => !cancelled && setOverviewError(e instanceof Error ? e : new Error(String(e))))
      .finally(() => !cancelled && setOverviewLoading(false));
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  // Poll a running job until it finishes.
  const jobId = job && (job.status === "queued" || job.status === "running") ? job.id : null;
  useEffect(() => {
    if (!jobId) return;
    const timer = setInterval(() => {
      api
        .job(jobId)
        .then(async (j) => {
          setJob(j);
          if (j.status === "done" && j.audit_id) {
            await refresh();
            setActiveId(j.audit_id);
          }
        })
        .catch((e: unknown) => {
          setJob((cur) =>
            cur ? { ...cur, status: "failed", error: e instanceof Error ? e.message : String(e) } : cur,
          );
        });
    }, 500);
    return () => clearInterval(timer);
  }, [jobId, refresh]);

  const scanPath = useCallback(async (path: string, mode: "scan" | "validate" = "scan") => {
    setStartError(null);
    try {
      setJob(await api.startScan(path, mode));
    } catch (e) {
      setStartError(e instanceof Error ? e : new Error(String(e)));
    }
  }, []);

  const scanUpload = useCallback(async (file: File) => {
    setStartError(null);
    setUploadFraction(0);
    try {
      const { promise } = uploadArchive(file, setUploadFraction);
      setJob(await promise);
    } catch (e) {
      setStartError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setUploadFraction(null);
    }
  }, []);

  const cancelJob = useCallback(async () => {
    if (job) setJob(await api.cancelJob(job.id));
  }, [job]);

  const removeAudit = useCallback(
    async (id: string) => {
      try {
        await api.deleteAudit(id);
      } catch (e) {
        // 404 = already gone (deleted in another tab, or a retry); the end state is what was asked for.
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
      setAudits((cur) => cur.filter((a) => a.id !== id)); // disappear immediately, no reload needed
      if (id === activeId) setActiveId(null);
      await refresh();
    },
    [activeId, refresh],
  );

  const value = useMemo<AuditContextValue>(
    () => ({
      audits,
      auditsError,
      activeId,
      overview,
      overviewLoading,
      overviewError,
      job,
      uploadFraction,
      startError,
      select: setActiveId,
      scanPath,
      scanUpload,
      cancelJob,
      dismissJob: () => setJob(null),
      removeAudit,
      refresh,
    }),
    [audits, auditsError, activeId, overview, overviewLoading, overviewError, job, uploadFraction, startError, scanPath, scanUpload, cancelJob, removeAudit, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAudit(): AuditContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAudit must be used inside <AuditProvider>");
  return v;
}
