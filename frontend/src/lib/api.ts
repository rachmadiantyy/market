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

export interface ProductMedia {
  id: string;
  media_type: "image" | "video";
  file_path: string;
  mime_type: string;
  file_size: number;
  source: string;
  url: string;
  created_at: string;
}

export interface GeneratedMedia {
  id: string;
  product_id: string;
  source_media_id: string | null;
  type: "image" | "video";
  provider: string;
  model: string | null;
  preset: string | null;
  prompt: string;
  storage_key: string | null;
  mime_type: string;
  file_size: number;
  width: number;
  height: number;
  status: GenerationStatus;
  error_message: string | null;
  url: string;
  created_at: string;
  completed_at: string | null;
  // --- video metadata (populated when type === "video") ---
  provider_job_id?: string | null;
  duration_seconds?: number;
  aspect_ratio?: string | null;
}

export interface Product {
  id: string;
  name: string;
  status: string;
  description?: string | null;
  affiliate_url?: string | null;
  price: number | null;
  currency: string;
  category?: string | null;
  target_audience?: string | null;
  media?: ProductMedia[];
  generated_visuals?: GeneratedMedia[];
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

// --- Visual Generator API ---

export interface VisualPreset {
  id: string;
  name: string;
  description: string;
}

export interface VisualGeneratePayload {
  product_id: string;
  source_media_id?: string | null;
  preset_id: string;
  custom_prompt?: string | null;
  variations: number;
}

export function fetchVisualPresets(): Promise<VisualPreset[]> {
  return apiSend<VisualPreset[]>("/visuals/presets", "GET");
}

export interface VisualProviderStatus {
  provider: string;
  model: string;
  is_mock: boolean;
  credentials: "SET" | "NOT SET";
  supports_reference_image: boolean;
  reference_enabled: boolean;
  timeout_seconds: number;
  max_retries: number;
  r2_configured: boolean;
}

export function fetchVisualProviderStatus(): Promise<VisualProviderStatus> {
  return apiSend<VisualProviderStatus>("/visuals/provider", "GET");
}

export function generateVisuals(
  payload: VisualGeneratePayload
): Promise<GeneratedMedia[]> {
  return apiSend<GeneratedMedia[]>("/visuals/generate", "POST", payload);
}

export function fetchVisuals(productId?: string): Promise<GeneratedMedia[]> {
  const query = productId ? `?product_id=${productId}` : "";
  return apiSend<GeneratedMedia[]>(`/visuals${query}`, "GET");
}

export function deleteVisual(id: string): Promise<void> {
  return apiSend<void>(`/visuals/${id}`, "DELETE");
}

export function regenerateVisual(id: string): Promise<GeneratedMedia> {
  return apiSend<GeneratedMedia>(`/visuals/${id}/regenerate`, "POST");
}

// --- Video Generator API ---
//
// Mirrors the visuals API: same queue, same GeneratedMedia records, different
// media type. Provider status never exposes a credential value.

export interface VideoPreset {
  id: string;
  name: string;
  description: string;
  default_duration_seconds: number;
  default_aspect_ratio: string;
  supports_text_only: boolean;
}

export interface VideoProviderStatus {
  provider: string;
  model: string;
  is_mock: boolean;
  credentials: "SET" | "NOT SET";
  supports_text_to_video: boolean;
  supports_image_to_video: boolean;
  supports_audio: boolean;
  supported_durations: number[];
  supported_aspect_ratios: string[];
  default_resolution: number[];
  contract_verified: boolean;
  timeout_seconds: number;
  poll_timeout_seconds: number;
  max_retries: number;
  default_duration_seconds: number;
  max_duration_seconds: number;
  r2_configured: boolean;
}

export interface VideoGeneratePayload {
  product_id: string;
  source_media_id?: string | null;
  preset_id: string;
  custom_prompt?: string | null;
  variations?: number;
  duration_seconds?: number;
  aspect_ratio?: string;
}

export function fetchVideoPresets(): Promise<VideoPreset[]> {
  return apiSend<VideoPreset[]>("/videos/presets", "GET");
}

export function fetchVideoProviderStatus(): Promise<VideoProviderStatus> {
  return apiSend<VideoProviderStatus>("/videos/provider", "GET");
}

export function generateVideos(
  payload: VideoGeneratePayload
): Promise<GeneratedMedia[]> {
  return apiSend<GeneratedMedia[]>("/videos/generate", "POST", payload);
}

export function fetchVideos(productId?: string): Promise<GeneratedMedia[]> {
  const query = productId ? `?product_id=${productId}` : "";
  return apiSend<GeneratedMedia[]>(`/videos${query}`, "GET");
}

export function deleteVideo(id: string): Promise<void> {
  return apiSend<void>(`/videos/${id}`, "DELETE");
}

export function regenerateVideo(id: string): Promise<GeneratedMedia> {
  return apiSend<GeneratedMedia>(`/videos/${id}/regenerate`, "POST");
}

