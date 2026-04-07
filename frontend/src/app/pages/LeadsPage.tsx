import { useCallback, useEffect, useState, useMemo } from 'react';
import { Download } from 'lucide-react';
import * as XLSX from 'xlsx';
import { format } from 'date-fns';
import { LeadFilters } from '../components/LeadFilters';
import { LeadTable, Lead } from '../components/LeadTable';
import { Pagination } from '../components/Pagination';
import { useLayoutActions } from '../components/LayoutActionsContext';
import { listLeads, isAdminApiConfigured } from '../lib/adminApi';

const PAGE_SIZE = 25;

export function LeadsPage() {
  const configured = isAdminApiConfigured();
  const { setActions } = useLayoutActions();

  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState({
    name: '',
    contact: '',
    refId: '',
    startDate: '',
    endDate: '',
  });

  const handleFilterChange = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setCurrentPage(1);
  };

  const handleResetFilters = () => {
    setFilters({ name: '', contact: '', refId: '', startDate: '', endDate: '' });
    setCurrentPage(1);
  };

  const offset = (currentPage - 1) * itemsPerPage;

  useEffect(() => {
    if (!configured) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    const params: Parameters<typeof listLeads>[0] = {
      limit: itemsPerPage,
      offset,
    };
    const refIdNum = parseInt(filters.refId.trim(), 10);
    if (filters.refId.trim() && !isNaN(refIdNum)) params.qr_id = refIdNum;
    if (filters.contact.trim()) params.from_phone = filters.contact.trim();
    if (filters.startDate) params.start_ts = Math.floor(new Date(filters.startDate).getTime() / 1000);
    if (filters.endDate) params.end_ts = Math.floor(new Date(filters.endDate + 'T23:59:59').getTime() / 1000);

    listLeads(params)
      .then((res) => {
        if (cancelled) return;
        const items = Array.isArray(res?.items) ? res.items : [];
        const mapped: Lead[] = items.map((item) => ({
          id: String(item.id),
          timestamp: new Date(item.created_at * 1000),
          name: item.wa_display_name || item.from_phone,
          contact: item.from_phone,
          qrRefId: item.qr_id != null ? String(item.qr_id) : '',
        }));
        // Client-side name filter (API doesn't filter by name)
        const nameFilter = filters.name.trim().toLowerCase();
        setLeads(nameFilter ? mapped.filter((l) => l.name.toLowerCase().includes(nameFilter)) : mapped);
        setTotal(res?.total ?? 0);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load leads');
        setLeads([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [configured, offset, itemsPerPage, filters.refId, filters.contact, filters.startDate, filters.endDate, filters.name]);

  const totalPages = Math.ceil(total / itemsPerPage);

  const handleExportToExcel = useCallback(() => {
    const exportData = leads.map((lead) => ({
      'Timestamp': format(lead.timestamp, 'MMM dd, yyyy hh:mm a'),
      'Name': lead.name,
      'Contact': lead.contact,
      'QR Ref ID': lead.qrRefId,
    }));

    const worksheet = XLSX.utils.json_to_sheet(exportData);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Leads');

    const maxWidth = exportData.reduce((acc, row) => {
      Object.keys(row).forEach((key) => {
        const value = String(row[key as keyof typeof row]);
        acc[key] = Math.max(acc[key] || 10, value.length);
      });
      return acc;
    }, {} as Record<string, number>);

    worksheet['!cols'] = Object.keys(maxWidth).map((key) => ({
      wch: Math.min(maxWidth[key] + 2, 50),
    }));

    XLSX.writeFile(workbook, `leads-export-${format(new Date(), 'yyyy-MM-dd')}.xlsx`);
  }, [leads]);

  // Server-side filtered count is `total`; after client name filter use leads.length
  const filteredLeads = useMemo(() => leads, [leads]);

  useEffect(() => {
    setActions(
      <button
        onClick={handleExportToExcel}
        disabled={filteredLeads.length === 0}
        className="flex w-full items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors sm:w-auto"
      >
        <Download className="w-4 h-4" />
        <span className="hidden sm:inline">Export to Excel</span>
        <span className="sm:hidden">Export</span>
      </button>,
    );
    return () => setActions(null);
  }, [filteredLeads.length, handleExportToExcel, setActions]);

  return (
    <div className="bg-gray-50 h-full">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-4 h-full flex flex-col min-h-0">
        <div className="shrink-0">
          <LeadFilters
            filters={filters}
            onFilterChange={handleFilterChange}
            onReset={handleResetFilters}
          />
        </div>

        {!configured && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Admin API not configured. Set <code>VITE_ADMIN_API_SECRET</code> in your <code>.env</code> file.
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-hidden mt-3">
          {loading && leads.length === 0 ? (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center text-sm text-gray-500">
              Loading leads…
            </div>
          ) : (
            <LeadTable
              leads={filteredLeads}
              currentPage={1}
              itemsPerPage={filteredLeads.length || 1}
            />
          )}
        </div>

        {total > 0 && (
          <div className="shrink-0">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              itemsPerPage={itemsPerPage}
              totalItems={total}
              onPageChange={setCurrentPage}
              onItemsPerPageChange={(items) => {
                setItemsPerPage(items);
                setCurrentPage(1);
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
