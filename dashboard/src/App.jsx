import { useState } from 'react'
import PRSidebar from './components/PRSidebar'
import TerminalView from './components/TerminalView'

function App() {
  const [selectedPR, setSelectedPR] = useState(null)

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-gray-200">
      <PRSidebar selectedPR={selectedPR} onSelectPR={setSelectedPR} />
      <main className="flex-1 min-w-0">
        <TerminalView prId={selectedPR} />
      </main>
    </div>
  )
}

export default App
