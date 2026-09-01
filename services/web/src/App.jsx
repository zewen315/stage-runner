import { Link, Route, Routes } from 'react-router-dom'
import WorkflowsList from './pages/WorkflowsList.jsx'
import WorkflowDetail from './pages/WorkflowDetail.jsx'
import RunDetail from './pages/RunDetail.jsx'
import ResourcesList from './pages/ResourcesList.jsx'
import ResourceDetail from './pages/ResourceDetail.jsx'

export default function App() {
  return (
    <div className="app">
      <nav className="nav">
        <Link to="/">Workflows</Link>
        <Link to="/resources">Resources</Link>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<WorkflowsList />} />
          <Route path="/workflows/:name" element={<WorkflowDetail />} />
          <Route path="/workflows/:name/runs/:runId" element={<RunDetail />} />
          <Route path="/resources" element={<ResourcesList />} />
          <Route path="/resources/:name" element={<ResourceDetail />} />
        </Routes>
      </main>
    </div>
  )
}
