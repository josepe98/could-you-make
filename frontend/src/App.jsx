import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Submit from './pages/Submit.jsx'
import TicketStatus from './pages/TicketStatus.jsx'
import AdminLogin from './pages/AdminLogin.jsx'
import AdminDashboard from './pages/AdminDashboard.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/submit" element={<Submit />} />
        <Route path="/ticket/:token" element={<TicketStatus />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="*" element={<Navigate to="/submit" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
