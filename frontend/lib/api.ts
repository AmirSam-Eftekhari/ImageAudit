import type {
  DupPage,
  FindingsResponse,
  HealthInfo,
  ImageDetail,
  ImagePage,
  ImageQuery,
  IssuePage,
  Job,
  Leakage,
  Overview,
  Summary,
} from "./types";

/**
 * Base URL of the API. "" means same-origin (`/api/...`).
 *  - Packaged/static-export build (NEXT_EXPORT=1 sets NEXT_PUBLIC_SAME_ORIGIN=1): always same-origin.
 *    The dev URL below is dead code there and is removed by the minifier.
 *  - Dev / Docker / `next start`: NEXT_PUBLIC_API_URL, defaulting to the local `imageaudit serve`.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_SAME_ORIGIN === "1"
    ? ""
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const unreachableMessage = () =>
  API_BASE === ""
    ? "Cannot reach the ImageAudit server that served this page. Is ImageAudit still running?"
    : `Cannot reach the ImageAudit API at ${API_BASE}. Start it with "imageaudit serve" and check NEXT_PUBLIC_API_URL and CORS settings.`;

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string } };
    return new ApiError(res.status, body.error?.code ?? "error", body.error?.message ?? res.statusText);
  } catch {
    return new ApiError(res.status, "error", `${res.status} ${res.statusText}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "unreachable", unreachableMessage());
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

type Query = Record<string, string | number | string[] | undefined>;

function qs(params: Query): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<HealthInfo>("/api/health"),
  defaults: () => request<Record<string, unknown>>("/api/config/defaults"),
  startScan: (path: string, mode: "scan" | "validate" = "scan") =>
    request<Job>("/api/scans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, mode }),
    }),
  job: (id: string) => request<Job>(`/api/scans/${id}`),
  cancelJob: (id: string) => request<Job>(`/api/scans/${id}`, { method: "DELETE" }),
  audits: () => request<Summary[]>("/api/audits"),
  audit: (id: string) => request<Overview>(`/api/audits/${id}`),
  deleteAudit: (id: string) => request<void>(`/api/audits/${id}`, { method: "DELETE" }),
  images: (id: string, q: ImageQuery) => request<ImagePage>(`/api/audits/${id}/images${qs({ ...q })}`),
  image: (id: string, imageId: string) => request<ImageDetail>(`/api/audits/${id}/images/${imageId}`),
  issues: (id: string, p: Query) => request<IssuePage>(`/api/audits/${id}/annotations/issues${qs(p)}`),
  duplicates: (id: string, p: Query) => request<DupPage>(`/api/audits/${id}/duplicates${qs(p)}`),
  leakage: (id: string) => request<Leakage>(`/api/audits/${id}/leakage`),
  findings: (id: string, p: Query) => request<FindingsResponse>(`/api/audits/${id}/findings${qs(p)}`),
};

export function thumbUrl(auditId: string, imageId: string, size = 256): string {
  return `${API_BASE}/api/audits/${auditId}/images/${imageId}/thumbnail?size=${size}`;
}

export function reportUrl(
  auditId: string,
  fmt: string,
  opts: { csvKind?: string; inline?: boolean; includeImages?: boolean } = {},
): string {
  return `${API_BASE}/api/audits/${auditId}/reports/${fmt}${qs({
    csv_kind: opts.csvKind,
    inline: opts.inline ? "true" : undefined,
    include_images: opts.includeImages ? "true" : undefined,
  })}`;
}

/** Upload a .zip dataset to the local API (it never leaves this machine), with progress. */
export function uploadArchive(
  file: File,
  onProgress: (fraction: number) => void,
  mode: "scan" | "validate" = "scan",
): { promise: Promise<Job>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<Job>((resolve, reject) => {
    xhr.open("POST", `${API_BASE}/api/scans/upload?mode=${mode}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () =>
      reject(new ApiError(0, "unreachable", unreachableMessage()));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "Upload cancelled"));
    xhr.onload = () => {
      try {
        const body: unknown = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as Job);
          return;
        }
        const err = (body as { error?: { code?: string; message?: string } }).error;
        reject(new ApiError(xhr.status, err?.code ?? "error", err?.message ?? xhr.statusText));
      } catch {
        reject(new ApiError(xhr.status, "error", `${xhr.status} ${xhr.statusText}`));
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
