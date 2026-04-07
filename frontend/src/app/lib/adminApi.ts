/**
 * Worker admin API for QR inventory and leads.
 * Auth: header from VITE_ADMIN_API_SECRET_HEADER (default X-Admin-Key) + VITE_ADMIN_API_SECRET.
 * Base URL: VITE_API_BASE_URL (empty = same origin; use Vite dev proxy to wrangler).
 */

export type QrItem = {
  id: number;
  full_prefilled_text: string;
  redirect_url: string;
  provisioned_at: number;
  last_scanned_at: number | null;
  expires_at: number | null;
};

export type LeadItem = {
  id: number;
  from_phone: string;
  wa_display_name: string | null;
  qr_id: number | null;
  match_method: string;
  created_at: number;
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

export async function createQrs(body: {
  count: number;
}): Promise<{ created: number; items: QrItem[] }> {
  const res = await fetch(apiUrl('/api/qrs'), {
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

export async function listQrs(params: {
  limit?: number;
  offset?: number;
}): Promise<{ items: QrItem[]; total: number; limit: number; offset: number }> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));

  const qs = sp.toString();
  const res = await fetch(apiUrl(`/api/qrs${qs ? `?${qs}` : ''}`), {
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

export async function listLeads(params: {
  limit?: number;
  offset?: number;
  qr_id?: number;
  from_phone?: string;
  start_ts?: number;
  end_ts?: number;
}): Promise<{ items: LeadItem[]; total: number; limit: number; offset: number }> {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', String(params.limit));
  if (params.offset != null) sp.set('offset', String(params.offset));
  if (params.qr_id != null) sp.set('qr_id', String(params.qr_id));
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
