import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppsProvider } from './AppsContext.jsx'
import { ConfirmProvider } from './ConfirmDialog.jsx'
import Submit from './pages/Submit.jsx'
import TicketStatus from './pages/TicketStatus.jsx'
import AdminLogin from './pages/AdminLogin.jsx'
import AdminDashboard from './pages/AdminDashboard.jsx'
import AdminApps from './pages/AdminApps.jsx'

export default function App() {
  return (
    <AppsProvider>
      <ConfirmProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/submit" element={<Submit />} />
            <Route path="/ticket/:token" element={<TicketStatus />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/apps" element={<AdminApps />} />
            <Route path="*" element={<Navigate to="/submit" replace />} />
          </Routes>
        </BrowserRouter>
      </ConfirmProvider>
    </AppsProvider>
  )
}
