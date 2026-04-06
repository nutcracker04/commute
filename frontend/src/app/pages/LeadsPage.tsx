import { useCallback, useEffect, useState, useMemo } from 'react';
import { Download } from 'lucide-react';
import * as XLSX from 'xlsx';
import { format } from 'date-fns';
import { LeadFilters } from '../components/LeadFilters';
import { LeadTable, Lead } from '../components/LeadTable';
import { Pagination } from '../components/Pagination';
import { useLayoutActions } from '../components/LayoutActionsContext';

// Mock data generator
const generateMockLeads = (): Lead[] => {
  const names = ['John Smith', 'Sarah Johnson', 'Michael Brown', 'Emily Davis', 'David Wilson', 
                 'Jessica Martinez', 'Christopher Lee', 'Amanda Taylor', 'Matthew Anderson', 'Jennifer Thomas',
                 'Daniel Jackson', 'Lisa White', 'James Harris', 'Karen Martin', 'Robert Thompson'];
  const qrRefs = ['QR-2024-001', 'QR-2024-002', 'QR-2024-003', 'QR-2024-004', 'QR-2024-005',
                  'QR-2024-006', 'QR-2024-007', 'QR-2024-008', 'QR-2024-009', 'QR-2024-010'];
  
  const leads: Lead[] = [];
  for (let i = 0; i < 50; i++) {
    const randomDate = new Date(2026, 3, Math.floor(Math.random() * 6) + 1, 
                                Math.floor(Math.random() * 24), Math.floor(Math.random() * 60));
    leads.push({
      id: `lead-${i + 1}`,
      timestamp: randomDate,
      name: names[Math.floor(Math.random() * names.length)],
      contact: `+1 (555) ${String(Math.floor(Math.random() * 900) + 100)}-${String(Math.floor(Math.random() * 9000) + 1000)}`,
      qrRefId: qrRefs[Math.floor(Math.random() * qrRefs.length)],
    });
  }
  
  return leads.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
};

export function LeadsPage() {
  const [leads] = useState<Lead[]>(generateMockLeads());
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(25);
  const { setActions } = useLayoutActions();
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
    setFilters({
      name: '',
      contact: '',
      refId: '',
      startDate: '',
      endDate: '',
    });
    setCurrentPage(1);
  };

  const filteredLeads = useMemo(() => {
    return leads.filter((lead) => {
      const matchesName = lead.name.toLowerCase().includes(filters.name.toLowerCase());
      const matchesContact = lead.contact.toLowerCase().includes(filters.contact.toLowerCase());
      const matchesRefId = lead.qrRefId.toLowerCase().includes(filters.refId.toLowerCase());
      
      const leadDate = new Date(lead.timestamp);
      const matchesStartDate = !filters.startDate || leadDate >= new Date(filters.startDate);
      const matchesEndDate = !filters.endDate || leadDate <= new Date(filters.endDate + 'T23:59:59');
      
      return matchesName && matchesContact && matchesRefId && matchesStartDate && matchesEndDate;
    });
  }, [leads, filters]);

  const totalPages = Math.ceil(filteredLeads.length / itemsPerPage);

  const handleExportToExcel = useCallback(() => {
    const exportData = filteredLeads.map((lead) => ({
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
  }, [filteredLeads]);

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

        <div className="flex-1 min-h-0 overflow-hidden">
          <LeadTable
            leads={filteredLeads}
            currentPage={currentPage}
            itemsPerPage={itemsPerPage}
          />
        </div>

        {filteredLeads.length > 0 && (
          <div className="shrink-0">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              itemsPerPage={itemsPerPage}
              totalItems={filteredLeads.length}
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
