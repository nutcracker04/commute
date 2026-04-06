/**
 * Worker admin API for physical QR inventory.
 * Auth: header from VITE_ADMIN_API_SECRET_HEADER (default X-Admin-Key) + VITE_ADMIN_API_SECRET.
 * Base URL: VITE_API_BASE_URL (empty = same origin; use Vite dev proxy to wrangler).
 */

export type PhysicalQrItem = {
  ref_id: string;
  event_id: string;
  full_prefilled_text: string;
  redirect_url: string;
  batch_id: string | null;
  label: string | null;
  slug?: string | null;
  external_sku?: string | null;
  provisioned_at: number;
  first_scanned_at?: number | null;
  expires_at?: number | null;
};

const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
const adminSecret = (import.meta.env.VITE_ADMIN_API_SECRET as string | undefined) ?? '';
const adminHeaderName =
  (import.meta.env.VITE_ADMIN_API_SECRET_HEADER as string | undefined)?.trim() || 'X-Admin-Key';

export function isAdminApiConfigured(): boolean {
  return Boolean(adminSecret);
}

function adminHeaders(includeJson = false): HeadersInit {
  const h: Record<string, string> = {
    [adminHeaderName]: adminSecret,
  };
  if (includeJson) {
    h['Content-Type'] = 'application/json';
  }
  return h;
}

function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${apiBase}${p}`;
}

export async function createPhysicalQrs(body: {
  event_id: string;
  count: number;
  batch_id?: string;
  label?: string;
}): Promise<{ created: number; items: PhysicalQrItem[] }> {
  const res = await fetch(apiUrl('/api/physical-qrs'), {
    method: 'POST',
    headers: adminHeaders(true),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.error === 'string' ? data.error : `Request failed (${res.status})`);
  }
  return {
    created: data.created ?? 0,
    items: Array.isArray(data.items) ? data.items : [],
  };
}

export type LeadItem = {
  id: number;
  from_phone: string;
  wa_display_name: string | null;
  ref_id: string;
  event_id: string;
  match_method: string;
  created_at: number;
};

export async function listLeads(params: {
  limit?: number;
  offset?: number;
  event_id?: string;
  ref_id?: string;
  from_phone?: string;
  start_ts?: number;
  end_ts?: number;
}): Promise<{ items: LeadItem[]; total: number; limit: number; offset: number }> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.event_id) sp.set('event_id', params.event_id);
  if (params.ref_id) sp.set('ref_id', params.ref_id);
  if (params.from_phone) sp.set('from_phone', params.from_phone);
  if (params.start_ts != null) sp.set('start_ts', String(params.start_ts));
  if (params.end_ts != null) sp.set('end_ts', String(params.end_ts));

  const qs = sp.toString();
  const res = await fetch(apiUrl(`/api/leads${qs ? `?${qs}` : ''}`), {
    method: 'GET',
    headers: adminHeaders(false),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.error === 'string' ? data.error : `Request failed (${res.status})`);
  }
  return {
    items: Array.isArray(data.items) ? data.items : [],
    total: data.total ?? 0,
    limit: data.limit ?? 0,
    offset: data.offset ?? 0,
  };
}

export async function listPhysicalQrs(params: {
  limit?: number;
  offset?: number;
  event_id?: string;
  batch_id?: string;
}): Promise<{ items: PhysicalQrItem[]; total: number; limit: number; offset: number }> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.event_id) sp.set('event_id', params.event_id);
  if (params.batch_id) sp.set('batch_id', params.batch_id);

  const qs = sp.toString();
  const res = await fetch(apiUrl(`/api/physical-qrs${qs ? `?${qs}` : ''}`), {
    method: 'GET',
    headers: adminHeaders(false),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.error === 'string' ? data.error : `Request failed (${res.status})`);
  }
  return {
    items: Array.isArray(data.items) ? data.items : [],
    total: data.total ?? 0,
    limit: data.limit ?? 0,
    offset: data.offset ?? 0,
  };
}
