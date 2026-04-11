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
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      {/* Mobile: card list */}
      <div className="min-h-0 flex-1 overflow-auto bg-gray-50 p-2 sm:hidden">
        <div className="space-y-3">
          {paginatedLeads.map((lead) => (
            <article
              key={lead.id}
              className="overflow-hidden rounded-2xl bg-white px-4 py-3.5 shadow-sm ring-1 ring-gray-950/[0.06]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-[15px] font-semibold leading-snug text-gray-900">
                    {lead.name}
                  </h3>
                  <p className="mt-1 break-all text-sm leading-snug text-gray-600">{lead.contact}</p>
                </div>
                <div className="shrink-0 text-right">
                  <time
                    className="block text-xs font-medium text-gray-500"
                    dateTime={lead.timestamp.toISOString()}
                  >
                    {format(lead.timestamp, 'MMM d, yyyy')}
                  </time>
                  <span className="mt-0.5 block text-[11px] text-gray-400">
                    {format(lead.timestamp, 'h:mm a')}
                  </span>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
                {lead.qrRefId ? (
                  <span className="inline-flex items-baseline gap-1.5 rounded-md bg-gray-50 px-2 py-1 text-xs">
                    <span className="font-medium text-gray-400">Ref</span>
                    <span className="font-mono font-medium text-gray-800">{lead.qrRefId}</span>
                  </span>
                ) : (
                  <span className="text-xs text-gray-400">No QR ref</span>
                )}
                {lead.couponCode ? (
                  <span className="inline-flex rounded-md bg-violet-50 px-2 py-1 font-mono text-xs font-medium text-violet-900 ring-1 ring-violet-200/70">
                    {lead.couponCode}
                  </span>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      </div>

      {/* Desktop: table */}
      <div className="hidden min-h-0 flex-1 overflow-auto sm:block">
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
                QR ref
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
