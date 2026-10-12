/** Thin fetch wrapper: cookie auth, CSRF header, transparent token refresh. */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith("rm_csrf="))
    ?.split("=")[1];
}

export function toQueryString(params?: Query): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) sp.append(key, String(v));
    } else {
      sp.append(key, String(value));
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken() ?? "" },
  })
    .then((r) => r.ok)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export const onUnauthorized = { handler: () => {} };

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { loc?: string[]; msg: string }) => `${d.loc?.at(-1) ?? ""}: ${d.msg}`)
        .join("; ");
    }
  } catch {
    /* not JSON */
  }
  return res.statusText || `Request failed (${res.status})`;
}

export async function request<T>(
  method: string,
  path: string,
  options: { query?: Query; body?: unknown; form?: FormData; raw?: boolean } = {},
  retry = true,
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = csrfToken();
  if (token && method !== "GET") headers["X-CSRF-Token"] = token;
  let body: BodyInit | undefined;
  if (options.form) body = options.form;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const res = await fetch(`/api/v1${path}${toQueryString(options.query)}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
  });

  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(method, path, options, false);
    onUnauthorized.handler();
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  if (res.status === 204) return undefined as T;
  if (options.raw) return res as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  del: <T = void>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, { form }),
};

/** Navigate the browser to a download URL (cookies are sent automatically). */
export function downloadUrl(path: string, query?: Query): string {
  return `/api/v1${path}${toQueryString(query)}`;
}
