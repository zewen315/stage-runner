import { Link, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import NewRun from './pages/NewRun.jsx'
import RunDetail from './pages/RunDetail.jsx'
import ResourceDetail from './pages/ResourceDetail.jsx'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Stage Runner
        </Link>
        <Link to="/runs/new" className="btn-primary">
          + New run
        </Link>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/runs/new" element={<NewRun />} />
          <Route path="/workflows/:name/runs/:runId" element={<RunDetail />} />
          <Route path="/resources/:name" element={<ResourceDetail />} />
        </Routes>
      </main>
    </div>
  )
}
