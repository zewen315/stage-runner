import { Link, Route, Routes } from 'react-router-dom'
import { NewRunModalProvider, useNewRunModal } from './NewRunModalContext.jsx'
import NewRunModal from './components/NewRunModal.jsx'
import Dashboard from './pages/Dashboard.jsx'
import RunDetail from './pages/RunDetail.jsx'
import ResourceDetail from './pages/ResourceDetail.jsx'

function Topbar() {
  const { open } = useNewRunModal()
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        Stage Runner
      </Link>
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
            <Route path="/workflows/:name/runs/:runId" element={<RunDetail />} />
            <Route path="/resources/:name" element={<ResourceDetail />} />
          </Routes>
        </main>
        <NewRunModal />
      </div>
    </NewRunModalProvider>
  )
}
