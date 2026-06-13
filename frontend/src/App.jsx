import { useCallback, useEffect, useState } from 'react';
import { fetchStories, triggerRun } from './api';
import TagFilter from './components/TagFilter';
import StoryCard from './components/StoryCard';
import StoryDetail from './components/StoryDetail';
import RunHistory from './components/RunHistory';
import './App.css';

export default function App() {
  const [stories, setStories] = useState([]);
  const [activeTag, setActiveTag] = useState(null);
  const [selectedStory, setSelectedStory] = useState(null);
  const [runId, setRunId] = useState(null);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState(null);

  const loadStories = useCallback(() => {
    fetchStories({ tag: activeTag, runId }).then(setStories);
  }, [activeTag, runId]);

  useEffect(() => {
    loadStories();
  }, [loadStories]);

  const handleTriggerRun = async () => {
    setRunning(true);
    setRunStatus(null);
    try {
      const result = await triggerRun();
      setRunStatus(`Run ${result.run_id.slice(0, 8)} — ${result.status}`);
      // Poll for completion
      const poll = setInterval(async () => {
        const updated = await fetchStories();
        if (updated.length > 0 || result.status === 'already_running') {
          clearInterval(poll);
          setRunning(false);
          setRunId(null);
          loadStories();
        }
      }, 5000);
      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(poll);
        setRunning(false);
      }, 300000);
    } catch {
      setRunStatus('Failed to trigger run');
      setRunning(false);
    }
  };

  const handleSelectRun = (id) => {
    setRunId(id);
    setSelectedStory(null);
  };

  if (selectedStory) {
    return (
      <div className="app">
        <StoryDetail
          storyId={selectedStory}
          onBack={() => setSelectedStory(null)}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>📰 AI Engineering Briefing</h1>
        <p className="subtitle">
          Daily news produced by a multi-agent newsroom
        </p>
        <div className="header-actions">
          <button
            className="run-btn"
            onClick={handleTriggerRun}
            disabled={running}
          >
            {running ? '⏳ Running…' : '▶ New Run'}
          </button>
          {runStatus && <span className="run-status">{runStatus}</span>}
        </div>
      </header>

      <TagFilter active={activeTag} onChange={setActiveTag} />

      <RunHistory onSelectRun={handleSelectRun} />

      <main className="story-grid">
        {stories.length === 0 ? (
          <div className="empty-state">
            <p>No stories yet. Trigger a run to get started.</p>
          </div>
        ) : (
          stories.map((story) => (
            <StoryCard
              key={story.id}
              story={story}
              onClick={() => setSelectedStory(story.id)}
            />
          ))
        )}
      </main>
    </div>
  );
}
