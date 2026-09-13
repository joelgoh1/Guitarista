import { toast } from "sonner";

/** RFC 9457 problem+json body as emitted by the FastAPI error handlers. */
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  /** FastAPI validation errors (`errors=exc.errors()`). */
  errors?: Array<{ loc?: (string | number)[]; msg?: string; type?: string }>;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string;
  readonly problem: ProblemDetails | null;

  constructor(status: number, detail: string, problem: ProblemDetails | null = null, title?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.title = title ?? problem?.title ?? defaultTitle(status);
    this.problem = problem;
  }

  static fromResponse(status: number, body: unknown, fallback?: string): ApiError {
    if (isProblem(body)) {
      const detail =
        body.detail ??
        body.errors?.map((e) => `${(e.loc ?? []).join(".")}: ${e.msg ?? ""}`).join("; ") ??
        fallback ??
        `Request failed (${status})`;
      return new ApiError(status, detail, body);
    }
    if (typeof body === "string" && body.trim()) return new ApiError(status, body.trim());
    return new ApiError(status, fallback ?? `Request failed (${status})`);
  }
}

function defaultTitle(status: number): string {
  if (status === 0) return "Network error";
  if (status === 404) return "Not found";
  if (status === 422) return "Unprocessable";
  if (status >= 500) return "Server error";
  return "Request failed";
}

export function isProblem(value: unknown): value is ProblemDetails {
  return (
    typeof value === "object" &&
    value !== null &&
    ("detail" in value || "title" in value || "status" in value)
  );
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Normalise anything thrown by fetch/openapi-fetch/react-query into an ApiError. */
export function toApiError(error: unknown, fallback = "Something went wrong"): ApiError {
  if (isApiError(error)) return error;
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) {
    return new ApiError(0, "Cannot reach the Guitarista API. Is the backend running?", null, "Network error");
  }
  if (error instanceof Error) return new ApiError(0, error.message || fallback);
  return new ApiError(0, fallback);
}

export function toastApiError(error: unknown, fallback?: string): ApiError {
  const err = toApiError(error, fallback);
  toast.error(err.title, { description: err.detail });
  return err;
}
