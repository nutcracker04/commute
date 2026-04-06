import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

type LayoutActionsContextValue = {
  actions: ReactNode | null;
  setActions: (actions: ReactNode | null) => void;
};

const LayoutActionsContext = createContext<LayoutActionsContextValue | null>(null);

export function LayoutActionsProvider({ children }: { children: ReactNode }) {
  const [actions, setActionsState] = useState<ReactNode | null>(null);

  const setActions = useCallback((next: ReactNode | null) => {
    setActionsState(next);
  }, []);

  const value = useMemo(() => ({ actions, setActions }), [actions, setActions]);

  return <LayoutActionsContext.Provider value={value}>{children}</LayoutActionsContext.Provider>;
}

export function useLayoutActions() {
  const ctx = useContext(LayoutActionsContext);
  if (!ctx) {
    throw new Error('useLayoutActions must be used within LayoutActionsProvider');
  }
  return ctx;
}
