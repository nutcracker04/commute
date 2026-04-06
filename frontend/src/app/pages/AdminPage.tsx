import React, { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { QrInventoryCard } from '../components/QrInventoryCard';
import {
  createPhysicalQrs,
  listPhysicalQrs,
  isAdminApiConfigured,
  type PhysicalQrItem,
} from '../lib/adminApi';

/** Matches seed in migrations/0001_initial.sql */
const DEFAULT_EVENT_ID = 'evt_demo';
const PAGE_SIZE = 12;
const MAX_BATCH = 100;

export function AdminPage() {
  const configured = isAdminApiConfigured();

  const [tab, setTab] = useState('generate');

  const [eventId, setEventId] = useState(DEFAULT_EVENT_ID);
  const [quantity, setQuantity] = useState('1');
  const [recentItems, setRecentItems] = useState<PhysicalQrItem[]>([]);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const [filterEventId, setFilterEventId] = useState('');
  const [libraryItems, setLibraryItems] = useState<PhysicalQrItem[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  const loadLibrary = useCallback(async () => {
    if (!configured) return;
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const { items, total } = await listPhysicalQrs({
        limit: PAGE_SIZE,
        offset: libraryOffset,
        event_id: filterEventId.trim() || undefined,
      });
      setLibraryItems(items);
      setLibraryTotal(total);
    } catch (e) {
      setLibraryError(e instanceof Error ? e.message : 'Failed to load library');
      setLibraryItems([]);
    } finally {
      setLibraryLoading(false);
    }
  }, [configured, libraryOffset, filterEventId]);

  useEffect(() => {
    if (tab === 'library' && configured) {
      void loadLibrary();
    }
  }, [tab, configured, loadLibrary]);

  const handleGenerate = async () => {
    if (!configured) return;
    const qty = parseInt(quantity, 10);
    if (isNaN(qty) || qty < 1 || qty > MAX_BATCH) {
      setGenerateError(`Enter a quantity between 1 and ${MAX_BATCH}`);
      return;
    }
    const ev = eventId.trim();
    if (!ev) {
      setGenerateError('Event ID is required');
      return;
    }

    setGenerateError(null);
    setIsGenerating(true);
    try {
      const { items } = await createPhysicalQrs({
        event_id: ev,
        count: qty,
      });
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

  return (
    <div className="h-full min-h-0 overflow-auto bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 pb-10">
        <Tabs value={tab} onValueChange={setTab} className="w-full gap-4">
          <TabsList className="grid h-auto w-full grid-cols-2 rounded-xl bg-gray-100 p-1 sm:inline-flex sm:w-auto">
            <TabsTrigger value="generate" className="rounded-lg">
              Generate
            </TabsTrigger>
            <TabsTrigger value="library" className="rounded-lg">
              QR Library
            </TabsTrigger>
          </TabsList>

          <TabsContent value="generate" className="mt-4 space-y-6 outline-none">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
              <h2 className="text-base font-semibold text-gray-900">Provision QR codes</h2>
              <p className="mt-1 text-sm text-gray-600">
                Creates rows in inventory and returns printable QR images (encode the redirect URL).
              </p>

              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 sm:max-w-2xl">
                <div>
                  <label htmlFor="admin-event-id" className="mb-1 block text-xs font-medium text-gray-700">
                    Event ID <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="admin-event-id"
                    type="text"
                    value={eventId}
                    onChange={(e) => setEventId(e.target.value)}
                    disabled={!configured}
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-transparent focus:ring-2 focus:ring-purple-500 disabled:bg-gray-100"
                    placeholder="evt_demo"
                  />
                </div>
                <div>
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
                  <p className="mt-0.5 text-[11px] text-gray-500">Up to {MAX_BATCH} per request (worker may allow more)</p>
                </div>
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
                    <QrInventoryCard key={item.ref_id} item={item} />
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="library" className="mt-4 space-y-4 outline-none">
            <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:flex-row sm:items-end sm:justify-between">
              <div className="flex flex-1 flex-col gap-2 sm:max-w-xs">
                <label htmlFor="library-filter-event" className="text-xs font-medium text-gray-700">
                  Filter by event ID
                </label>
                <input
                  id="library-filter-event"
                  type="text"
                  value={filterEventId}
                  onChange={(e) => {
                    setFilterEventId(e.target.value);
                    setLibraryOffset(0);
                  }}
                  disabled={!configured}
                  placeholder="Leave empty for all"
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-transparent focus:ring-2 focus:ring-purple-500 disabled:bg-gray-100"
                />
              </div>
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
                No QR codes in inventory yet. Use Generate to provision some.
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
                    <QrInventoryCard key={item.ref_id} item={item} />
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
        </Tabs>
      </div>
    </div>
  );
}
