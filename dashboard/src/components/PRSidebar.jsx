import { useState, useEffect } from 'react';
import { GitPullRequest, Search, Activity, Settings, TerminalSquare } from 'lucide-react';

const PRSidebar = ({ onSelectPR, selectedPR, activePage, onChangePage }) => {
  const [prs, setPrs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPRs = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/prs');
        const data = await response.json();
        setPrs(data.prs || []);
      } catch (error) {
        console.error("Failed to fetch PRs:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchPRs();
    // Refresh list every 10 seconds
    const interval = setInterval(fetchPRs, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-80 h-full bg-[#0f172a] border-r border-slate-800 flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="text-slate-300 w-6 h-6" />
          <h1 className="text-xl font-semibold text-slate-100">
            CodeSentinel
          </h1>
        </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input 
            type="text" 
            placeholder="Search PRs..." 
            className="w-full bg-[#0b1220] border border-slate-700 rounded-md py-2 pl-9 pr-4 text-sm focus:outline-none focus:border-slate-500 transition-colors"
          />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            onClick={() => onChangePage('dashboard')}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs border transition-colors ${
              activePage === 'dashboard'
                ? 'bg-slate-700 text-slate-100 border-slate-500'
                : 'bg-[#0b1220] text-slate-300 border-slate-700 hover:border-slate-500'
            }`}
          >
            <TerminalSquare className="w-3.5 h-3.5" />
            Dashboard
          </button>
          <button
            onClick={() => onChangePage('settings')}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs border transition-colors ${
              activePage === 'settings'
                ? 'bg-slate-700 text-slate-100 border-slate-500'
                : 'bg-[#0b1220] text-slate-300 border-slate-700 hover:border-slate-500'
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            Settings
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-2">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-2">
          Pipeline Executions
        </div>
        {activePage === 'settings' ? (
          <div className="text-sm text-gray-400 px-2">Configure models and runtime parameters in Settings.</div>
        ) : loading ? (
          <div className="text-sm text-gray-400 px-2 animate-pulse">Loading PRs...</div>
        ) : prs.length === 0 ? (
          <div className="text-sm text-gray-400 px-2">No PR logs found.</div>
        ) : (
          <ul className="space-y-1">
            {prs.map((pr) => (
              <li key={pr}>
                <button
                  onClick={() => onSelectPR(pr)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-all duration-200 text-sm ${
                    selectedPR === pr 
                      ? 'bg-slate-800 text-slate-100 font-medium' 
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <GitPullRequest className={`w-4 h-4 ${selectedPR === pr ? 'text-slate-300' : 'text-gray-500'}`} />
                  <span>Pull Request #{pr}</span>
                  {selectedPR === pr && (
                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-slate-300" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default PRSidebar;
