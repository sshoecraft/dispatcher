import React from 'react'
import { Route, Routes } from 'react-router'

import MainLayout from '@/layouts/MainLayout'
import Login from '@/pages/Login'
import NotFound from '@/pages/NotFound'
import Stack from '@/pages/Stack'
import Jobs from '@/pages/Jobs'
import Dashboard from '@/pages/Dashboard'
import Settings from '@/pages/Settings'
import Workers from '@/pages/Workers'
import Queues from '@/pages/Queues'
import Specs from '@/pages/Specs'
import Users from '@/pages/Users'
import { RequiredAuth } from '@/app/secure-route'

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/stack" element={<Stack />} />
      
      {/* Protected routes */}
      <Route element={<RequiredAuth />}>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/workers" element={<Workers />} />
          <Route path="/specs" element={<Specs />} />
          <Route path="/queues" element={<Queues />} />
          <Route path="/users" element={<Users />} />
        </Route>
      </Route>
      
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default AppRoutes