import { Link, useLocation } from 'react-router';
import { QrCode, Users } from 'lucide-react';
import { useLayoutActions } from './LayoutActionsContext';

export function Navigation() {
  const location = useLocation();
  const { actions } = useLayoutActions();

  return (
    <nav className="border-b border-gray-200 bg-white pt-[env(safe-area-inset-top,0px)]">
      <div className="mx-auto max-w-7xl pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))] sm:pl-[max(1.5rem,env(safe-area-inset-left,0px))] sm:pr-[max(1.5rem,env(safe-area-inset-right,0px))] lg:pl-[max(2rem,env(safe-area-inset-left,0px))] lg:pr-[max(2rem,env(safe-area-inset-right,0px))]">
        <div className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:h-16 sm:py-0">
          <div className="flex items-center">
            <div className="flex flex-wrap gap-2 sm:gap-4">
              <Link
                to="/"
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  location.pathname === '/'
                    ? 'bg-blue-50 text-blue-600'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
              >
                <Users className="w-4 h-4" />
                Leads
              </Link>
              <Link
                to="/admin"
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  location.pathname === '/admin'
                    ? 'bg-purple-50 text-purple-600'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
              >
                <QrCode className="w-4 h-4" />
                Admin Panel
              </Link>
            </div>
          </div>

          {actions ? <div className="flex items-center sm:justify-end">{actions}</div> : null}
        </div>
      </div>
    </nav>
  );
}
