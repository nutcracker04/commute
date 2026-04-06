import { createBrowserRouter } from 'react-router';
import { Layout } from './components/Layout';
import { LeadsPage } from './pages/LeadsPage';
import { AdminPage } from './pages/AdminPage';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: Layout,
    children: [
      { index: true, Component: LeadsPage },
      { path: 'admin', Component: AdminPage },
    ],
  },
]);
