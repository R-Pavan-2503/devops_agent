import React, { useState, useEffect } from 'react';
import { GitPullRequest, Search, Activity } from 'lucide-react';

const PRSidebar = ({ onSelectPR, selectedPR }) => {
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
    <div className="w-80 h-full bg-surface border-r border-border flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="text-primary w-6 h-6" />
          <h1 className="text-xl font-bold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
            CodeSentinel
          </h1>
        </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input 
            type="text" 
            placeholder="Search PRs..." 
            className="w-full bg-background border border-border rounded-md py-2 pl-9 pr-4 text-sm focus:outline-none focus:border-primary/50 transition-colors"
          />
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-2">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-2">
          Pipeline Executions
        </div>
        {loading ? (
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
                      ? 'bg-primary/10 text-primary font-medium' 
                      : 'text-gray-300 hover:bg-border/50 hover:text-white'
                  }`}
                >
                  <GitPullRequest className={`w-4 h-4 ${selectedPR === pr ? 'text-primary' : 'text-gray-500'}`} />
                  <span>Pull Request #{pr}</span>
                  {selectedPR === pr && (
                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)] animate-pulse" />
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
