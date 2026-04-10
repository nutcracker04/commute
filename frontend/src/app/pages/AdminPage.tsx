import React, { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { QrInventoryCard } from '../components/QrInventoryCard';
import {
  createQrs,
  listQrs,
  isAdminApiConfigured,
  createDriver,
  listDrivers,
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

export function AdminPage() {
  const configured = isAdminApiConfigured();

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
  const [dCode, setDCode] = useState('');
  const [dExtRef, setDExtRef] = useState('');
  const [dQrRef, setDQrRef] = useState('');
  const [driverCreateBusy, setDriverCreateBusy] = useState(false);

  const [weeks, setWeeks] = useState<WeekItem[]>([]);
  const [dlcRows, setDlcRows] = useState<DlcItem[]>([]);
  const [dlcWeekId, setDlcWeekId] = useState<string>('');
  const [commissionLoading, setCommissionLoading] = useState(false);
  const [commissionError, setCommissionError] = useState<string | null>(null);
  const [dlcRunMsg, setDlcRunMsg] = useState<string | null>(null);
  const [dlcRunBusy, setDlcRunBusy] = useState(false);

  const loadLibrary = useCallback(async () => {
    if (!configured) return;
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
  }, [configured, libraryOffset]);

  useEffect(() => {
    if (tab === 'library' && configured) {
      void loadLibrary();
    }
  }, [tab, configured, loadLibrary]);

  const loadDrivers = useCallback(async () => {
    if (!configured) return;
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
  }, [configured]);

  const loadCommission = useCallback(async () => {
    if (!configured) return;
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
  }, [configured, dlcWeekId]);

  useEffect(() => {
    if (tab === 'drivers' && configured) {
      void loadDrivers();
    }
  }, [tab, configured, loadDrivers]);

  useEffect(() => {
    if (tab === 'commission' && configured) {
      void loadCommission();
    }
  }, [tab, configured, loadCommission]);

  const handleGenerate = async () => {
    if (!configured) return;
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
    if (!configured) return;
    const name = dName.trim();
    const phone = dPhone.trim();
    if (!name || !phone) {
      setDriversError('Name and phone are required');
      return;
    }
    setDriverCreateBusy(true);
    setDriversError(null);
    try {
      const qrRefNum = dQrRef.trim() ? parseInt(dQrRef.trim(), 10) : NaN;
      await createDriver({
        name,
        phone,
        driver_code: dCode.trim() || undefined,
        external_ref: dExtRef.trim() || undefined,
        qr_ref_id: !isNaN(qrRefNum) ? qrRefNum : undefined,
      });
      setDName('');
      setDPhone('');
      setDCode('');
      setDExtRef('');
      setDQrRef('');
      await loadDrivers();
    } catch (e) {
      setDriversError(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setDriverCreateBusy(false);
    }
  };

  const handleRunDlc = async () => {
    if (!configured) return;
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
          <TabsList className="grid h-auto w-full grid-cols-2 gap-1 rounded-xl bg-gray-100 p-1 sm:grid-cols-4">
            <TabsTrigger value="generate" className="rounded-lg">
              Generate
            </TabsTrigger>
            <TabsTrigger value="library" className="rounded-lg">
              QR Library
            </TabsTrigger>
            <TabsTrigger value="drivers" className="rounded-lg">
              Drivers
            </TabsTrigger>
            <TabsTrigger value="commission" className="rounded-lg">
              Commission
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
                  disabled={!configured}
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-transparent focus:ring-2 focus:ring-purple-500 disabled:bg-gray-100"
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
                  disabled={!configured || isGenerating}
                  className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-purple-600 px-6 text-sm font-medium text-white transition-colors hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
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
            <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:flex-row sm:items-end sm:justify-between">
              <div className="text-sm text-gray-600">All QR codes — permanent, reusable.</div>
              <button
                type="button"
                onClick={() => void loadLibrary()}
                disabled={!configured || libraryLoading}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-gray-300 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
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
                <div className="text-xs text-gray-600 sm:text-sm">
                  Showing{' '}
                  <span className="font-medium">{libraryTotal === 0 ? 0 : libraryOffset + 1}</span>–
                  <span className="font-medium">{libraryEnd}</span> of{' '}
                  <span className="font-medium">{libraryTotal}</span>
                </div>
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
                    className="rounded-md border border-gray-300 p-2 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
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
                    className="rounded-md border border-gray-300 p-2 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
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
              <p className="text-sm text-gray-600">
                Set <code className="text-xs bg-gray-100 px-1 rounded">qr_ref_id</code> to the provisioned QR id
                (<code className="text-xs">qrs.id</code>).
                Upload assets (R2):{' '}
                <code className="text-xs bg-gray-100 px-1 rounded">qr-image</code>,{' '}
                <code className="text-xs bg-gray-100 px-1 rounded">upi-qr-image</code>,{' '}
                <code className="text-xs bg-gray-100 px-1 rounded">identity-image</code>.
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                <input
                  placeholder="Name *"
                  value={dName}
                  onChange={(e) => setDName(e.target.value)}
                  disabled={!configured}
                  className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  placeholder="Phone *"
                  value={dPhone}
                  onChange={(e) => setDPhone(e.target.value)}
                  disabled={!configured}
                  className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  placeholder="Driver code"
                  value={dCode}
                  onChange={(e) => setDCode(e.target.value)}
                  disabled={!configured}
                  className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  placeholder="External ref"
                  value={dExtRef}
                  onChange={(e) => setDExtRef(e.target.value)}
                  disabled={!configured}
                  className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  placeholder="QR ref_id (qrs.id)"
                  value={dQrRef}
                  onChange={(e) => setDQrRef(e.target.value)}
                  disabled={!configured}
                  className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleCreateDriver()}
                  disabled={!configured || driverCreateBusy}
                  className="inline-flex h-9 items-center rounded-md bg-purple-600 px-4 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
                >
                  {driverCreateBusy ? 'Saving…' : 'Add driver'}
                </button>
                <button
                  type="button"
                  onClick={() => void loadDrivers()}
                  disabled={!configured || driversLoading}
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-gray-300 px-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
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
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs text-gray-500 uppercase">
                    <tr>
                      <th className="px-3 py-2">ID</th>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2">Phone</th>
                      <th className="px-3 py-2">Driver id</th>
                      <th className="px-3 py-2">ref_id</th>
                      <th className="px-3 py-2">WA QR</th>
                      <th className="px-3 py-2">UPI</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {drivers.map((d) => (
                      <tr key={d.id}>
                        <td className="px-3 py-2 font-mono">{d.id}</td>
                        <td className="px-3 py-2">{d.name}</td>
                        <td className="px-3 py-2">{d.phone}</td>
                        <td className="px-3 py-2">{d.driver_code ?? d.driver_id ?? '—'}</td>
                        <td className="px-3 py-2 font-mono">{d.qr_ref_id ?? '—'}</td>
                        <td className="px-3 py-2 max-w-[100px] truncate">
                          {d.qr_asset_url ? (
                            <a
                              href={d.qr_asset_url}
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
                      </tr>
                    ))}
                  </tbody>
                </table>
                {drivers.length === 0 && !driversLoading && (
                  <div className="p-6 text-center text-gray-500 text-sm">No drivers yet.</div>
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="commission" className="mt-4 space-y-4 outline-none">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-6 space-y-4">
              <h2 className="text-base font-semibold text-gray-900">Commission (DLC)</h2>
              <p className="text-sm text-gray-600">
                Counts increment on each new lead; Sunday 06:00 UTC cron reconciles from leads for the prior
                week. Manual run uses the same reconciliation.
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Filter by week id</label>
                  <select
                    value={dlcWeekId}
                    onChange={(e) => setDlcWeekId(e.target.value)}
                    className="rounded-md border border-gray-300 px-2 py-1.5 text-sm min-w-[120px]"
                  >
                    <option value="">All weeks</option>
                    {weeks.map((w) => (
                      <option key={w.id} value={String(w.id)}>
                        Week #{w.id}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={() => void loadCommission()}
                  disabled={!configured || commissionLoading}
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-gray-300 px-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${commissionLoading ? 'animate-spin' : ''}`} />
                  Reload
                </button>
                <button
                  type="button"
                  onClick={() => void handleRunDlc()}
                  disabled={!configured || dlcRunBusy}
                  className="inline-flex h-9 items-center rounded-md bg-purple-600 px-4 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
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
              <h3 className="text-sm font-medium text-gray-800">Weeks</h3>
              <div className="overflow-x-auto border border-gray-200 rounded-lg max-h-40 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs text-gray-500 uppercase sticky top-0">
                    <tr>
                      <th className="px-3 py-2">ID</th>
                      <th className="px-3 py-2">Start (unix)</th>
                      <th className="px-3 py-2">End (unix)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {weeks.map((w) => (
                      <tr key={w.id}>
                        <td className="px-3 py-2 font-mono">{w.id}</td>
                        <td className="px-3 py-2">{w.start_at}</td>
                        <td className="px-3 py-2">{w.end_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3 className="text-sm font-medium text-gray-800">Driver lead counts</h3>
              <div className="overflow-x-auto border border-gray-200 rounded-lg max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs text-gray-500 uppercase sticky top-0">
                    <tr>
                      <th className="px-3 py-2">DLC id</th>
                      <th className="px-3 py-2">ref_id</th>
                      <th className="px-3 py-2">Week</th>
                      <th className="px-3 py-2">Leads</th>
                      <th className="px-3 py-2">Computed</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {dlcRows.map((r) => (
                      <tr key={r.id}>
                        <td className="px-3 py-2 font-mono">{r.id}</td>
                        <td className="px-3 py-2 font-mono">{r.ref_id}</td>
                        <td className="px-3 py-2">{r.week_id}</td>
                        <td className="px-3 py-2">{r.lead_count}</td>
                        <td className="px-3 py-2 text-xs">{r.computed_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {dlcRows.length === 0 && !commissionLoading && (
                  <div className="p-6 text-center text-gray-500 text-sm">No DLC rows yet. Run aggregation.</div>
                )}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
