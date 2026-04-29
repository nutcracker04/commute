import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, RefreshCw, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { QrInventoryCard } from '../components/QrInventoryCard';
import {
  createQrs,
  listQrs,
  createDriver,
  listDrivers,
  listAvailableRefIds,
  listWeeks,
  listDlc,
  runDlcAggregation,
  type QrItem,
  type DriverItem,
  type WeekItem,
  type DlcItem,
} from '../lib/adminApi';

const PAGE_SIZE = 12;
const MAX_BATCH = 100;

function weekFilterLabel(w: WeekItem): string {
  try {
    const start = new Date(w.start_at * 1000).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
    return `Week #${w.id} — ${start}`;
  } catch {
    return `Week #${w.id}`;
  }
}

function formatDlcComputedAt(ts: number | string | undefined): string {
  if (ts == null || ts === '') return '—';
  const n = typeof ts === 'number' ? ts : Number(ts);
  if (!Number.isFinite(n)) return String(ts);
  const ms = n < 1e12 ? n * 1000 : n;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return String(ts);
  }
}

const fieldInputClass =
  'w-full min-w-0 rounded-md border border-gray-300 px-2.5 py-2 text-base sm:py-1.5 sm:text-sm focus:border-transparent focus:ring-2 focus:ring-purple-500 disabled:bg-gray-100';

function MobileDriverAssetRow({
  href,
  label,
}: {
  href: string | null | undefined;
  label: string;
}) {
  if (!href) {
    return (
      <div className="flex min-h-11 items-center justify-between gap-3 py-2.5 text-sm">
        <span className="text-gray-500">{label}</span>
        <span className="tabular-nums text-gray-300">—</span>
      </div>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      title={href}
      aria-label={`${label} (opens in new tab)`}
      className="group flex min-h-11 items-center justify-between gap-3 rounded-lg py-2.5 text-left text-sm text-gray-800 transition-colors hover:bg-violet-50/60 hover:text-violet-900 active:bg-violet-50"
    >
      <span className="min-w-0 truncate font-medium">{label}</span>
      <ExternalLink className="size-4 shrink-0 text-violet-500/70 group-hover:text-violet-600" aria-hidden />
    </a>
  );
}

export function AdminPage() {

  const [tab, setTab] = useState('generate');

  const [quantity, setQuantity] = useState('1');
  const [recentItems, setRecentItems] = useState<QrItem[]>([]);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const [libraryItems, setLibraryItems] = useState<QrItem[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  const [drivers, setDrivers] = useState<DriverItem[]>([]);
  const [driversLoading, setDriversLoading] = useState(false);
  const [driversError, setDriversError] = useState<string | null>(null);
  const [dName, setDName] = useState('');
  const [dPhone, setDPhone] = useState('');
  const [dQrRefId, setDQrRefId] = useState('');
  const [availableRefIds, setAvailableRefIds] = useState<number[]>([]);
  const [refIdsLoading, setRefIdsLoading] = useState(false);
  const [driverCreateBusy, setDriverCreateBusy] = useState(false);
  const upiQrFileRef = useRef<HTMLInputElement>(null);
  const identityFileRef = useRef<HTMLInputElement>(null);

  const [weeks, setWeeks] = useState<WeekItem[]>([]);
  const [dlcRows, setDlcRows] = useState<DlcItem[]>([]);
  const [dlcWeekId, setDlcWeekId] = useState<string>('');
  const [commissionLoading, setCommissionLoading] = useState(false);
  const [commissionError, setCommissionError] = useState<string | null>(null);
  const [dlcRunMsg, setDlcRunMsg] = useState<string | null>(null);
  const [dlcRunBusy, setDlcRunBusy] = useState(false);

  const loadLibrary = useCallback(async () => {
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const { items, total } = await listQrs({
        limit: PAGE_SIZE,
        offset: libraryOffset,
      });
      setLibraryItems(items);
      setLibraryTotal(total);
    } catch (e) {
      setLibraryError(e instanceof Error ? e.message : 'Failed to load library');
      setLibraryItems([]);
    } finally {
      setLibraryLoading(false);
    }
  }, [libraryOffset]);

  useEffect(() => {
    if (tab === 'library') {
      void loadLibrary();
    }
  }, [tab, loadLibrary]);

  const loadDrivers = useCallback(async () => {
    setDriversLoading(true);
    setDriversError(null);
    try {
      const { items } = await listDrivers({ limit: 100, offset: 0 });
      setDrivers(items);
    } catch (e) {
      setDriversError(e instanceof Error ? e.message : 'Failed to load drivers');
      setDrivers([]);
    } finally {
      setDriversLoading(false);
    }
  }, []);

  const loadAvailableRefIds = useCallback(async () => {
    setRefIdsLoading(true);
    try {
      const page = 2000;
      const acc: number[] = [];
      let offset = 0;
      for (let guard = 0; guard < 100; guard += 1) {
        const { ref_ids, has_more } = await listAvailableRefIds({ limit: page, offset });
        acc.push(...ref_ids);
        if (!has_more) break;
        offset += ref_ids.length;
      }
      setAvailableRefIds(acc);
    } catch {
      setAvailableRefIds([]);
    } finally {
      setRefIdsLoading(false);
    }
  }, []);

  const loadCommission = useCallback(async () => {
    setCommissionLoading(true);
    setCommissionError(null);
    try {
      const [w, d] = await Promise.all([
        listWeeks({ limit: 50, offset: 0 }),
        listDlc({
          limit: 200,
          offset: 0,
          week_id: dlcWeekId ? parseInt(dlcWeekId, 10) : undefined,
        }),
      ]);
      setWeeks(w.items);
      setDlcRows(d.items);
    } catch (e) {
      setCommissionError(e instanceof Error ? e.message : 'Failed to load commission data');
      setWeeks([]);
      setDlcRows([]);
    } finally {
      setCommissionLoading(false);
    }
  }, [dlcWeekId]);

  useEffect(() => {
    if (tab === 'drivers') {
      void loadDrivers();
      void loadAvailableRefIds();
    }
  }, [tab, loadDrivers, loadAvailableRefIds]);

  useEffect(() => {
    if (tab === 'commission') {
      void loadCommission();
    }
  }, [tab, loadCommission]);

  const handleGenerate = async () => {
    const qty = parseInt(quantity, 10);
    if (isNaN(qty) || qty < 1 || qty > MAX_BATCH) {
      setGenerateError(`Enter a quantity between 1 and ${MAX_BATCH}`);
      return;
    }

    setGenerateError(null);
    setIsGenerating(true);
    try {
      const { items } = await createQrs({ count: qty });
      setRecentItems(items);
      setQuantity('1');
      if (tab === 'library') {
        await loadLibrary();
      }
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setIsGenerating(false);
    }
  };

  const libraryEnd = Math.min(libraryOffset + libraryItems.length, libraryTotal);
  const canPrev = libraryOffset > 0;
  const canNext = libraryOffset + PAGE_SIZE < libraryTotal;

  const handleCreateDriver = async () => {
    const name = dName.trim();
    const phone = dPhone.trim();
    const refNum = parseInt(dQrRefId.trim(), 10);
    if (!name || !phone) {
      setDriversError('Name and phone are required');
      return;
    }
    if (isNaN(refNum) || refNum < 1 || !availableRefIds.includes(refNum)) {
      setDriversError('Select an available ref ID from the list');
      return;
    }
    const upiFile = upiQrFileRef.current?.files?.[0];
    const idFile = identityFileRef.current?.files?.[0];
    if (!upiFile || !idFile) {
      setDriversError('UPI QR and identity proof files are required');
      return;
    }
    setDriverCreateBusy(true);
    setDriversError(null);
    try {
      const fd = new FormData();
      fd.append('name', name);
      fd.append('phone', phone);
      fd.append('qr_ref_id', String(refNum));
      fd.append('upi_qr', upiFile);
      fd.append('identity', idFile);
      await createDriver(fd);
      setDName('');
      setDPhone('');
      setDQrRefId('');
      if (upiQrFileRef.current) upiQrFileRef.current.value = '';
      if (identityFileRef.current) identityFileRef.current.value = '';
      await loadDrivers();
      await loadAvailableRefIds();
    } catch (e) {
      setDriversError(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setDriverCreateBusy(false);
    }
  };

  const handleRunDlc = async () => {
    setDlcRunBusy(true);
    setDlcRunMsg(null);
    try {
      const r = await runDlcAggregation();
      setDlcRunMsg(JSON.stringify(r));
      await loadCommission();
    } catch (e) {
      setDlcRunMsg(e instanceof Error ? e.message : 'Run failed');
    } finally {
      setDlcRunBusy(false);
    }
  };

  return (
    <div className="h-full min-h-0 overflow-auto bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 pb-10">
        <Tabs value={tab} onValueChange={setTab} className="w-full gap-4">
          <TabsList className="flex h-auto min-h-11 w-full max-w-full flex-nowrap gap-1 overflow-x-auto overflow-y-hidden rounded-xl bg-gray-100 p-1 [-webkit-overflow-scrolling:touch] sm:grid sm:h-auto sm:w-full sm:grid-cols-4 sm:overflow-visible">
            <TabsTrigger
              value="generate"
              className="min-h-11 min-w-[100px] shrink-0 rounded-lg px-3 sm:min-w-0 sm:flex-1"
              title="Generate QR codes"
            >
              Generate
            </TabsTrigger>
            <TabsTrigger
              value="library"
              className="min-h-11 min-w-[100px] shrink-0 rounded-lg px-3 sm:min-w-0 sm:flex-1"
              title="QR Library"
            >
              <span className="sm:hidden">Library</span>
              <span className="hidden sm:inline">QR Library</span>
            </TabsTrigger>
            <TabsTrigger
              value="drivers"
              className="min-h-11 min-w-[100px] shrink-0 rounded-lg px-3 sm:min-w-0 sm:flex-1"
              title="Drivers"
            >
              Drivers
            </TabsTrigger>
            <TabsTrigger
              value="commission"
              className="min-h-11 min-w-[100px] shrink-0 rounded-lg px-3 sm:min-w-0 sm:flex-1"
              title="Commission"
            >
              <span className="sm:hidden">DLC</span>
              <span className="hidden sm:inline">Commission</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="generate" className="mt-4 space-y-6 outline-none">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
              <h2 className="text-base font-semibold text-gray-900">Provision QR codes</h2>
              <p className="mt-1 text-sm text-gray-600">
                Creates permanent QR codes with sequential IDs and prefilled WhatsApp text.
              </p>

              <div className="mt-4 sm:max-w-xs">
                <label htmlFor="admin-qty" className="mb-1 block text-xs font-medium text-gray-700">
                  Quantity <span className="text-red-500">*</span>
                </label>
                <input
                  id="admin-qty"
                  type="number"
                  min={1}
                  max={MAX_BATCH}
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className={fieldInputClass}
                />
                <p className="mt-0.5 text-[11px] text-gray-500">Up to {MAX_BATCH} per request</p>
              </div>

              {generateError && (
                <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                  {generateError}
                </div>
              )}

              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => void handleGenerate()}
                  disabled={isGenerating}
                  className="inline-flex min-h-11 h-auto w-full items-center justify-center gap-2 rounded-md bg-purple-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50 sm:h-10 sm:w-auto sm:py-0"
                >
                  <Plus className="h-4 w-4" />
                  {isGenerating ? 'Provisioning…' : 'Generate QR codes'}
                </button>
              </div>
            </div>

            {recentItems.length > 0 && (
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
                <h3 className="text-base font-semibold text-gray-900">
                  This batch ({recentItems.length})
                </h3>
                <p className="mt-1 text-sm text-gray-600">Download each QR from the card below.</p>
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {recentItems.map((item) => (
                    <QrInventoryCard key={item.id} item={item} />
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="library" className="mt-4 space-y-4 outline-none">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
              <p className="min-w-0 text-xs text-gray-600 sm:text-sm">
                {libraryTotal > 0 ? (
                  <>
                    Showing{' '}
                    <span className="font-medium">{libraryTotal === 0 ? 0 : libraryOffset + 1}</span>–
                    <span className="font-medium">{libraryEnd}</span> of{' '}
                    <span className="font-medium">{libraryTotal}</span>
                  </>
                ) : null}
              </p>
              <button
                type="button"
                onClick={() => void loadLibrary()}
                disabled={libraryLoading}
                className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 self-start rounded-md border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50 sm:self-auto"
              >
                <RefreshCw className={`h-4 w-4 ${libraryLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            {libraryError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {libraryError}
              </div>
            )}

            {libraryLoading && libraryItems.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white p-12 text-center text-sm text-gray-500">
                Loading inventory…
              </div>
            ) : libraryItems.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white p-12 text-center text-sm text-gray-500">
                No QR codes yet. Use Generate to provision some.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {libraryItems.map((item) => (
                    <QrInventoryCard key={item.id} item={item} />
                  ))}
                </div>
                <div className="flex items-center justify-center gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setLibraryOffset((o) => Math.max(0, o - PAGE_SIZE))}
                    disabled={!canPrev || libraryLoading}
                    className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="text-sm text-gray-600">
                    Page {Math.floor(libraryOffset / PAGE_SIZE) + 1} /{' '}
                    {Math.max(1, Math.ceil(libraryTotal / PAGE_SIZE))}
                  </span>
                  <button
                    type="button"
                    onClick={() => setLibraryOffset((o) => o + PAGE_SIZE)}
                    disabled={!canNext || libraryLoading}
                    className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    aria-label="Next page"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </>
            )}
          </TabsContent>

          <TabsContent value="drivers" className="mt-4 space-y-4 outline-none">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-6 space-y-4">
              <h2 className="text-base font-semibold text-gray-900">Drivers</h2>
              <div className="grid gap-3 sm:grid-cols-2 sm:max-w-xl">
                <input
                  placeholder="Name *"
                  value={dName}
                  onChange={(e) => setDName(e.target.value)}
                  className={fieldInputClass}
                />
                <input
                  placeholder="Phone *"
                  value={dPhone}
                  onChange={(e) => setDPhone(e.target.value)}
                  className={fieldInputClass}
                />
                <div className="flex min-w-0 flex-col gap-1 sm:col-span-2">
                  <label className="text-xs font-medium text-gray-700" htmlFor="driver-ref-id-select">
                    Ref ID *
                  </label>
                  <select
                    id="driver-ref-id-select"
                    value={dQrRefId}
                    onChange={(e) => setDQrRefId(e.target.value)}
                    disabled={refIdsLoading}
                    className={fieldInputClass}
                  >
                    <option value="">
                      {refIdsLoading
                        ? 'Loading…'
                        : availableRefIds.length === 0
                          ? 'Generate first'
                          : 'Select ref ID…'}
                    </option>
                    {availableRefIds.map((id) => (
                      <option key={id} value={String(id)}>
                        {id}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-1 md:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs font-medium text-gray-700">
                  UPI QR *
                  <input
                    ref={upiQrFileRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="min-w-0 text-base sm:text-sm file:mr-2 file:rounded file:border-0 file:bg-purple-50 file:px-2 file:py-2 file:text-xs sm:file:py-1"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-gray-700">
                  Identity proof *
                  <input
                    ref={identityFileRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,application/pdf"
                    className="min-w-0 text-base sm:text-sm file:mr-2 file:rounded file:border-0 file:bg-purple-50 file:px-2 file:py-2 file:text-xs sm:file:py-1"
                  />
                </label>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                <button
                  type="button"
                  onClick={() => void handleCreateDriver()}
                  disabled={driverCreateBusy}
                  className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-purple-600 px-4 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 sm:w-auto"
                >
                  {driverCreateBusy ? 'Saving…' : 'Add driver'}
                </button>
                <button
                  type="button"
                  onClick={() => void loadDrivers()}
                  disabled={driversLoading}
                  className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 sm:w-auto"
                >
                  <RefreshCw className={`h-4 w-4 ${driversLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>
              {driversError && (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                  {driversError}
                </div>
              )}
              {driversLoading && drivers.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
                  Loading drivers…
                </div>
              ) : drivers.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
                  No drivers yet.
                </div>
              ) : (
                <>
                  <div className="space-y-4 md:hidden">
                    {drivers.map((d) => (
                      <article
                        key={d.id}
                        className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-gray-950/[0.06]"
                      >
                        <div className="flex gap-4 border-b border-gray-100 px-4 pb-3 pt-4">
                          <div className="min-w-0 flex-1 space-y-2">
                            <p
                              className="font-mono text-[13px] font-semibold text-gray-900"
                              title={`Row id ${d.id}`}
                            >
                              {d.driver_code ?? d.driver_id ?? `D${d.id}`}
                            </p>
                            <p className="text-sm leading-snug text-gray-800">{d.name}</p>
                            <p className="break-all text-sm leading-snug text-gray-600">{d.phone}</p>
                          </div>
                          <div className="shrink-0 text-right">
                            <p className="text-[11px] font-medium text-gray-400">Ref</p>
                            <p className="font-mono text-lg font-semibold tabular-nums leading-tight text-gray-900">
                              {d.qr_ref_id ?? '—'}
                            </p>
                          </div>
                        </div>
                        <div className="divide-y divide-gray-100 px-4 pb-1 pt-0">
                          {d.qr_asset_url ? (
                            <MobileDriverAssetRow href={d.qr_asset_url} label="Lead QR" />
                          ) : null}
                          <MobileDriverAssetRow href={d.upi_qr_asset_url} label="UPI QR" />
                          {d.identity_asset_urls?.length ? (
                            d.identity_asset_urls.map((url, i) => (
                              <MobileDriverAssetRow
                                key={`${d.id}-id-${i}`}
                                href={url}
                                label={
                                  d.identity_asset_urls.length > 1
                                    ? `ID proof ${i + 1}`
                                    : 'ID proof'
                                }
                              />
                            ))
                          ) : (
                            <MobileDriverAssetRow href={null} label="ID proof" />
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                  <div className="hidden overflow-x-auto touch-pan-x rounded-lg border border-gray-200 md:block">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 text-left text-xs text-gray-500 uppercase">
                        <tr>
                          <th className="px-3 py-2">Driver</th>
                          <th className="px-3 py-2">Name</th>
                          <th className="px-3 py-2">Phone</th>
                          <th className="px-3 py-2">Ref ID</th>
                          <th className="px-3 py-2">UPI QR</th>
                          <th className="px-3 py-2">Identity</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {drivers.map((d) => (
                          <tr key={d.id}>
                            <td className="px-3 py-2 font-mono" title={`Row id ${d.id}`}>
                              {d.driver_code ?? d.driver_id ?? `D${d.id}`}
                            </td>
                            <td className="px-3 py-2">{d.name}</td>
                            <td className="px-3 py-2">{d.phone}</td>
                            <td className="px-3 py-2 font-mono">{d.qr_ref_id ?? '—'}</td>
                            <td className="px-3 py-2 max-w-[100px] truncate">
                              {d.upi_qr_asset_url ? (
                                <a
                                  href={d.upi_qr_asset_url}
                                  className="text-purple-600 hover:underline"
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  link
                                </a>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td className="px-3 py-2 max-w-[120px] truncate">
                              {d.identity_asset_urls?.length ? (
                                <a
                                  href={d.identity_asset_urls[0]}
                                  className="text-purple-600 hover:underline"
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {d.identity_asset_urls.length > 1
                                    ? `${d.identity_asset_urls.length} files`
                                    : 'link'}
                                </a>
                              ) : (
                                '—'
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="commission" className="mt-4 space-y-4 outline-none">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-6 space-y-4">
              <h2 className="text-base font-semibold text-gray-900">Commission (DLC)</h2>
              <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:flex-wrap sm:items-end sm:gap-3">
                <div className="min-w-0 w-full sm:w-auto">
                  <label className="mb-1 block text-xs text-gray-600">Week</label>
                  <select
                    value={dlcWeekId}
                    onChange={(e) => setDlcWeekId(e.target.value)}
                    className={`${fieldInputClass} sm:min-w-[min(100%,12rem)]`}
                  >
                    <option value="">All weeks</option>
                    {weeks.map((w) => (
                      <option key={w.id} value={String(w.id)}>
                        {weekFilterLabel(w)}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={() => void loadCommission()}
                  disabled={commissionLoading}
                  className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 sm:w-auto"
                >
                  <RefreshCw className={`h-4 w-4 ${commissionLoading ? 'animate-spin' : ''}`} />
                  Reload
                </button>
                <button
                  type="button"
                  onClick={() => void handleRunDlc()}
                  disabled={dlcRunBusy}
                  className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-purple-600 px-4 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 sm:w-auto"
                >
                  {dlcRunBusy ? 'Running…' : 'Run weekly aggregation'}
                </button>
              </div>
              {commissionError && (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                  {commissionError}
                </div>
              )}
              {dlcRunMsg && (
                <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-xs font-mono text-gray-800 break-all">
                  {dlcRunMsg}
                </div>
              )}
              <h3 className="text-sm font-medium text-gray-800">Driver lead counts</h3>
              {commissionLoading && dlcRows.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
                  Loading commission data…
                </div>
              ) : dlcRows.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
                  No DLC rows yet. Run aggregation.
                </div>
              ) : (
                <>
                  <div className="space-y-4 md:hidden">
                    {dlcRows.map((r) => (
                      <article
                        key={r.id}
                        className="overflow-hidden rounded-2xl bg-white px-4 py-4 shadow-sm ring-1 ring-gray-950/[0.06]"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <p className="text-[11px] font-medium text-gray-400">Leads</p>
                            <p className="mt-0.5 text-3xl font-semibold tabular-nums tracking-tight text-gray-900">
                              {r.lead_count}
                            </p>
                          </div>
                          <div className="shrink-0 text-right">
                            <p className="text-sm font-medium text-gray-900">Week {r.week_id}</p>
                            <p className="mt-1 font-mono text-xs tabular-nums text-gray-500">
                              Ref {r.ref_id}
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 border-t border-gray-100 pt-3">
                          <p className="break-all font-mono text-[11px] leading-relaxed text-gray-500">
                            <span className="text-gray-400">Entry</span>{' '}
                            <span className="text-gray-600">{r.id}</span>
                          </p>
                          <p className="mt-1.5 text-[11px] leading-relaxed text-gray-500">
                            <span className="text-gray-400">Updated</span>{' '}
                            <span className="text-gray-600">{formatDlcComputedAt(r.computed_at)}</span>
                          </p>
                        </div>
                      </article>
                    ))}
                  </div>
                  <div className="hidden max-h-64 overflow-y-auto overflow-x-auto touch-pan-x rounded-lg border border-gray-200 md:block">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-gray-50 text-left text-xs text-gray-500 uppercase">
                        <tr>
                          <th className="px-3 py-2">Entry</th>
                          <th className="px-3 py-2">QR ref</th>
                          <th className="px-3 py-2">Week #</th>
                          <th className="px-3 py-2">Leads</th>
                          <th className="px-3 py-2">Updated</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {dlcRows.map((r) => (
                          <tr key={r.id}>
                            <td className="px-3 py-2 font-mono">{r.id}</td>
                            <td className="px-3 py-2 font-mono">{r.ref_id}</td>
                            <td className="px-3 py-2">{r.week_id}</td>
                            <td className="px-3 py-2">{r.lead_count}</td>
                            <td className="px-3 py-2 text-xs">{formatDlcComputedAt(r.computed_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
