import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import NewCasePage from './pages/NewCase';
import ProgressDashboard from './pages/ProgressDashboard';
import ResultsDashboard from './pages/ResultsDashboard';
import DebateVisualization from './pages/DebateVisualization';
import SystemObservability from './pages/SystemObservability';
import PastCases from './pages/PastCases';
import Profile from './pages/Profile';
import ExperimentMode from './pages/ExperimentMode';
import './index.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<NewCasePage />} />
          <Route path="progress" element={<ProgressDashboard />} />
          <Route path="results" element={<ResultsDashboard />} />
          <Route path="debate" element={<DebateVisualization />} />
          <Route path="past-cases" element={<PastCases />} />
          <Route path="system" element={<SystemObservability />} />
          <Route path="profile" element={<Profile />} />
          <Route path="experiments" element={<ExperimentMode />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
