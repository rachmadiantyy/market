/**
 * The API base URL differs by execution context:
 *
 * - Server components (and the dev server) fetch from inside the container
 *   network, so they must use the internal service name (`http://backend:8000`)
 *   — `localhost` there is the frontend container itself.
 * - Browser code (client components) fetches from the user's machine, so it
 *   needs the publicly reachable address.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is the browser-facing value; `API_INTERNAL_BASE_URL`
 * overrides it for server-side rendering only.
 */
export const PUBLIC_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const INTERNAL_API_BASE = process.env.API_INTERNAL_BASE_URL ?? PUBLIC_API_BASE;

export const API_BASE =
  typeof window === "undefined" ? INTERNAL_API_BASE : PUBLIC_API_BASE;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail.length > 0) {
      const first = body.detail[0];
      return typeof first?.msg === "string" ? first.msg : "Permintaan tidak valid";
    }
  } catch {
    /* fall through */
  }
  return `Permintaan gagal (HTTP ${res.status})`;
}

export async function apiGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function apiSend<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new ApiError(await readErrorDetail(res), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface AnalyticsSummary {
  products: number;
  content_items: number;
  jobs: number;
  events: number;
  tracked_value: number;
  queue_depth: number;
}

export interface Product {
  id: string;
  name: string;
  status: string;
  price: number | null;
  currency: string;
}

export type GenerationStatus = "queued" | "processing" | "completed" | "failed";

export type AIContentType =
  | "caption"
  | "hook"
  | "short_video_script"
  | "product_description"
  | "cta";

export type AIPlatform = "tiktok" | "instagram" | "facebook" | "threads" | "x";

export interface AIVariation {
  index: number;
  text: string;
}

export interface AIGeneration {
  id: string;
  product_id: string | null;
  product_name: string | null;
  type: AIContentType;
  platform: AIPlatform;
  variations: number;
  prompt: string;
  status: GenerationStatus;
  result: { variations: AIVariation[] } | null;
  error_message: string | null;
  model: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AIGeneratePayload {
  prompt: string;
  product_id?: string | null;
  content_type: AIContentType;
  platform: AIPlatform;
  variations: number;
}

export function createGeneration(payload: AIGeneratePayload): Promise<AIGeneration> {
  return apiSend<AIGeneration>("/ai/generate", "POST", payload);
}

export function retryGeneration(id: string): Promise<AIGeneration> {
  return apiSend<AIGeneration>(`/ai/generations/${id}/retry`, "POST");
}

export function getGeneration(id: string): Promise<AIGeneration> {
  return apiSend<AIGeneration>(`/ai/generations/${id}`, "GET");
}

export function fetchGenerations(limit = 100): Promise<AIGeneration[]> {
  return apiSend<AIGeneration[]>(`/ai/generations?limit=${limit}`, "GET");
}

export const CONTENT_TYPE_LABELS: Record<AIContentType, string> = {
  caption: "Caption",
  hook: "Hook",
  short_video_script: "Short Video Script",
  product_description: "Product Description",
  cta: "CTA",
};

export const PLATFORM_LABELS: Record<AIPlatform, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
  facebook: "Facebook",
  threads: "Threads",
  x: "X",
};
