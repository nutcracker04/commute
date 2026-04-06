import { useState } from 'react';
import { Search, Calendar, ChevronDown } from 'lucide-react';

interface LeadFiltersProps {
  filters: {
    name: string;
    contact: string;
    refId: string;
    startDate: string;
    endDate: string;
  };
  onFilterChange: (key: string, value: string) => void;
  onReset: () => void;
}

export function LeadFilters({ filters, onFilterChange, onReset }: LeadFiltersProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3 sm:p-4 mb-3">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-gray-900">Filters</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsMobileOpen((prev) => !prev)}
            className="md:hidden inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 font-medium"
          >
            {isMobileOpen ? 'Hide' : 'Show'}
            <ChevronDown
              className={`w-3.5 h-3.5 transition-transform ${isMobileOpen ? 'rotate-180' : ''}`}
            />
          </button>
          <button
            onClick={onReset}
            className="text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            Reset All
          </button>
        </div>
      </div>
      
      <div className={`${isMobileOpen ? 'grid' : 'hidden'} md:grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2`}>
        <div>
          <label htmlFor="name" className="block text-xs font-medium text-gray-700 mb-1">
            Name
          </label>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
            <input
              type="text"
              id="name"
              placeholder="Search name..."
              value={filters.name}
              onChange={(e) => onFilterChange('name', e.target.value)}
              className="w-full pl-8 pr-2.5 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>

        <div>
          <label htmlFor="contact" className="block text-xs font-medium text-gray-700 mb-1">
            Contact
          </label>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
            <input
              type="text"
              id="contact"
              placeholder="Search contact..."
              value={filters.contact}
              onChange={(e) => onFilterChange('contact', e.target.value)}
              className="w-full pl-8 pr-2.5 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>

        <div>
          <label htmlFor="refId" className="block text-xs font-medium text-gray-700 mb-1">
            QR Ref ID
          </label>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
            <input
              type="text"
              id="refId"
              placeholder="Search ref ID..."
              value={filters.refId}
              onChange={(e) => onFilterChange('refId', e.target.value)}
              className="w-full pl-8 pr-2.5 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>

        <div>
          <label htmlFor="startDate" className="block text-xs font-medium text-gray-700 mb-1">
            Start Date
          </label>
          <div className="relative">
            <Calendar className="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
            <input
              type="date"
              id="startDate"
              value={filters.startDate}
              onChange={(e) => onFilterChange('startDate', e.target.value)}
              className="w-full pl-8 pr-2.5 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>

        <div>
          <label htmlFor="endDate" className="block text-xs font-medium text-gray-700 mb-1">
            End Date
          </label>
          <div className="relative">
            <Calendar className="absolute left-2.5 top-1/2 transform -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
            <input
              type="date"
              id="endDate"
              value={filters.endDate}
              onChange={(e) => onFilterChange('endDate', e.target.value)}
              className="w-full pl-8 pr-2.5 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
