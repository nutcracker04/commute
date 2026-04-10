import { format } from 'date-fns';

export interface Lead {
  id: string;
  timestamp: Date;
  name: string;
  contact: string;
  qrRefId: string;
  couponCode: string;
}

interface LeadTableProps {
  leads: Lead[];
  currentPage: number;
  itemsPerPage: number;
}

export function LeadTable({ leads, currentPage, itemsPerPage }: LeadTableProps) {
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedLeads = leads.slice(startIndex, endIndex);

  if (leads.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center h-full flex items-center justify-center">
        <p className="text-gray-500">No leads found matching your filters.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden h-full flex flex-col">
      {/* Mobile: card list */}
      <div className="divide-y divide-gray-100 sm:hidden overflow-auto">
        {paginatedLeads.map((lead) => (
          <div key={lead.id} className="px-3 py-2">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-900 leading-5 truncate">
                  {lead.name}
                </div>
                <div className="text-sm text-gray-600 leading-5 truncate">{lead.contact}</div>
              </div>

              <div className="text-[13px] text-gray-500 text-right leading-4 whitespace-nowrap">
                <div>{format(lead.timestamp, 'MMM dd, yyyy')}</div>
                <div>{format(lead.timestamp, 'hh:mm a')}</div>
              </div>
            </div>

            <div className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2">
              <div className="text-xs text-gray-500 leading-4">QR</div>
              <div className="text-xs font-mono text-gray-900 leading-4 truncate">
                {lead.qrRefId}
              </div>
            </div>
            {lead.couponCode ? (
              <div className="mt-1 text-xs font-mono text-purple-800">Coupon: {lead.couponCode}</div>
            ) : null}
          </div>
        ))}
      </div>

      {/* Desktop: table */}
      <div className="hidden sm:block overflow-auto">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Timestamp
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Contact
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                QR Ref ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Coupon
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {paginatedLeads.map((lead) => (
              <tr key={lead.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-3 whitespace-nowrap text-sm text-gray-900">
                  <div>{format(lead.timestamp, 'MMM dd, yyyy')}</div>
                  <div className="text-gray-500">{format(lead.timestamp, 'hh:mm a')}</div>
                </td>
                <td className="px-6 py-3 whitespace-nowrap text-sm text-gray-900">
                  {lead.name}
                </td>
                <td className="px-6 py-3 whitespace-nowrap text-sm text-gray-900">
                  {lead.contact}
                </td>
                <td className="px-6 py-3 whitespace-nowrap text-sm font-mono text-gray-900">
                  {lead.qrRefId}
                </td>
                <td className="px-6 py-3 whitespace-nowrap text-sm font-mono text-gray-900">
                  {lead.couponCode || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
