import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  itemsPerPage: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onItemsPerPageChange: (items: number) => void;
}

export function Pagination({
  currentPage,
  totalPages,
  itemsPerPage,
  totalItems,
  onPageChange,
  onItemsPerPageChange,
}: PaginationProps) {
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1;
  const endItem = Math.min(currentPage * itemsPerPage, totalItems);

  return (
    <div className="mt-3 rounded-lg border border-gray-200 bg-white px-3 py-3 shadow-sm sm:px-4 sm:py-2.5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          <div className="text-xs text-gray-600 sm:text-gray-700">
            <span className="sm:hidden">
              <span className="font-medium text-gray-900">
                {startItem}–{endItem}
              </span>
              <span className="text-gray-500"> of </span>
              <span className="font-medium text-gray-900">{totalItems}</span>
            </span>
            <span className="hidden sm:inline">
              Showing <span className="font-medium">{startItem}</span> to{' '}
              <span className="font-medium">{endItem}</span> of{' '}
              <span className="font-medium">{totalItems}</span> results
            </span>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="itemsPerPage" className="shrink-0 text-xs text-gray-700">
              Per page
            </label>
            <select
              id="itemsPerPage"
              value={itemsPerPage}
              onChange={(e) => onItemsPerPageChange(Number(e.target.value))}
              className="min-h-11 rounded-md border border-gray-300 px-3 py-2 text-base focus:border-transparent focus:ring-2 focus:ring-blue-500 sm:min-h-0 sm:px-2 sm:py-1 sm:text-xs"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>

        <div className="flex items-center justify-center gap-2 sm:justify-end sm:gap-1.5">
          <button
            type="button"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-white sm:min-h-0 sm:min-w-0 sm:px-2 sm:py-1.5"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
          </button>

          <div className="min-w-[5.5rem] px-1 text-center text-xs text-gray-700 sm:hidden">
            Page <span className="font-semibold text-gray-900">{currentPage}</span>
            <span className="text-gray-400"> / </span>
            <span className="font-medium">{totalPages}</span>
          </div>

          <div className="hidden sm:flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((page) => {
                // Show first page, last page, current page, and pages around current
                return (
                  page === 1 ||
                  page === totalPages ||
                  Math.abs(page - currentPage) <= 1
                );
              })
              .map((page, idx, array) => {
                // Add ellipsis if there's a gap
                const prevPage = array[idx - 1];
                const showEllipsis = prevPage && page - prevPage > 1;

                return (
                  <div key={page} className="flex items-center gap-1">
                    {showEllipsis && (
                      <span className="px-2 text-gray-500">...</span>
                    )}
                    <button
                      onClick={() => onPageChange(page)}
                      className={`px-2.5 py-1.5 border rounded-md text-xs font-medium ${
                        currentPage === page
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {page}
                    </button>
                  </div>
                );
              })}
          </div>

          <button
            type="button"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-white sm:min-h-0 sm:min-w-0 sm:px-2 sm:py-1.5"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
