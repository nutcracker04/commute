import { Outlet } from 'react-router';
import { Navigation } from './Navigation';
import { LayoutActionsProvider } from './LayoutActionsContext';

export function Layout() {
  return (
    <LayoutActionsProvider>
      <div className="h-screen overflow-hidden bg-gray-50 flex flex-col">
        <Navigation />
        <div className="flex-1 min-h-0">
          <Outlet />
        </div>
      </div>
    </LayoutActionsProvider>
  );
}
