import { useEffect, useState } from 'react'
import PRSidebar from './components/PRSidebar'
import TerminalView from './components/TerminalView'
import SettingsPage from './components/SettingsPage'

function App() {
  const [selectedPR, setSelectedPR] = useState(null)
  const [activePage, setActivePage] = useState('dashboard')
  const [toastMessage, setToastMessage] = useState('')

  useEffect(() => {
    fetch('http://localhost:8000/api/settings/reset', { method: 'POST' }).catch(() => {})

    const handleUnload = () => {
      fetch('http://localhost:8000/api/settings/reset', { method: 'POST', keepalive: true }).catch(() => {})
    }

    window.addEventListener('beforeunload', handleUnload)
    return () => {
      window.removeEventListener('beforeunload', handleUnload)
    }
  }, [])

  useEffect(() => {
    if (!toastMessage) return
    const timer = setTimeout(() => setToastMessage(''), 3000)
    return () => clearTimeout(timer)
  }, [toastMessage])

  return (
    <div className="relative flex h-screen w-full bg-[#0b1220] overflow-hidden text-gray-200">
      <PRSidebar
        selectedPR={selectedPR}
        onSelectPR={(pr) => {
          setActivePage('dashboard')
          setSelectedPR(pr)
        }}
        activePage={activePage}
        onChangePage={setActivePage}
      />
      <main className="flex-1 min-w-0">
        {activePage === 'settings' ? (
          <SettingsPage onSaved={(message) => setToastMessage(message)} />
        ) : (
          <TerminalView key={selectedPR || 'no-pr'} prId={selectedPR} />
        )}
      </main>
      {toastMessage && (
        <div className="absolute bottom-5 right-5 bg-success/20 border border-success/50 text-success px-4 py-2 rounded-md shadow-lg">
          {toastMessage}
        </div>
      )}
    </div>
  )
}

export default App
