import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { NewRunModalProvider, useNewRunModal } from './NewRunModalContext.jsx'
import NewRunModal from './components/NewRunModal.jsx'
import Dashboard from './pages/Dashboard.jsx'
import RunDetail from './pages/RunDetail.jsx'
import ResourceDetail from './pages/ResourceDetail.jsx'
import WorkflowsList from './pages/WorkflowsList.jsx'
import ResourcesList from './pages/ResourcesList.jsx'

function navLinkClass({ isActive }) {
  return isActive ? 'nav-link nav-link-active' : 'nav-link'
}

function Topbar() {
  const { open } = useNewRunModal()
  return (
    <header className="topbar">
      <div className="topbar-left">
        <Link to="/" className="brand">
          Stage Runner
        </Link>
        <nav className="topbar-nav">
          <NavLink to="/" end className={navLinkClass}>
            Dashboard
          </NavLink>
          <NavLink to="/workflows" className={navLinkClass}>
            Workflows
          </NavLink>
          <NavLink to="/resources" className={navLinkClass}>
            Resources
          </NavLink>
        </nav>
      </div>
      <button type="button" className="btn-primary" onClick={() => open()}>
        + New run
      </button>
    </header>
  )
}

export default function App() {
  return (
    <NewRunModalProvider>
      <div className="app">
        <Topbar />
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/workflows" element={<WorkflowsList />} />
            <Route path="/workflows/:name/runs/:runId" element={<RunDetail />} />
            <Route path="/resources" element={<ResourcesList />} />
            <Route path="/resources/:name" element={<ResourceDetail />} />
          </Routes>
        </main>
        <NewRunModal />
      </div>
    </NewRunModalProvider>
  )
}
