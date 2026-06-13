import { useCallback, useEffect, useState } from 'react';
import { cancelRun, fetchRuns, fetchStories, triggerRun } from './api';
import TagFilter from './components/TagFilter';
import StoryCard from './components/StoryCard';
import StoryDetail from './components/StoryDetail';
import RunHistory from './components/RunHistory';
import './App.css';

const STAGE_LABELS = {
  starting: '🚀 Starting…',
  research: '🔍 Research — fetching articles…',
  verification: '✅ Verification — scoring confidence…',
  editor_review: '📋 Editor — reviewing verification…',
  editorial: '📰 Editorial — ranking stories…',
  writing: '✍️ Writing — drafting briefings…',
  evaluation: '⭐ Evaluation — scoring quality…',
  revision_loop: '🔄 Revisions — improving drafts…',
  output: '📄 Output — writing briefing file…',
  done: '✅ Complete',
  failed: '❌ Failed',
  cancelled: '🚫 Cancelled',
};

export default function App() {
  const [stories, setStories] = useState([]);
  const [activeTag, setActiveTag] = useState(null);
  const [selectedStory, setSelectedStory] = useState(null);
  const [runId, setRunId] = useState(null);
  const [activeRunId, setActiveRunId] = useState(null);
  const [running, setRunning] = useState(false);
  const [currentStage, setCurrentStage] = useState(null);

  const loadStories = useCallback(() => {
    fetchStories({ tag: activeTag, runId }).then(setStories);
  }, [activeTag, runId]);

  useEffect(() => {
    loadStories();
  }, [loadStories]);

  // Poll for run progress when a run is active
  useEffect(() => {
    if (!running || !activeRunId) return;
    const interval = setInterval(async () => {
      const runs = await fetchRuns();
      const active = runs.find((r) => r.id === activeRunId);
      if (active) {
        setCurrentStage(active.current_stage);
        if (active.status !== 'running') {
          setRunning(false);
          setActiveRunId(null);
          setCurrentStage(null);
          loadStories();
        }
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, activeRunId, loadStories]);

  const handleTriggerRun = async () => {
    setRunning(true);
    setCurrentStage('starting');
    try {
      const result = await triggerRun();
      setActiveRunId(result.run_id);
      if (result.status === 'already_running') {
        setCurrentStage('already running');
      }
    } catch {
      setCurrentStage('failed to start');
      setRunning(false);
    }
  };

  const handleCancelRun = async () => {
    if (!activeRunId) return;
    try {
      await cancelRun(activeRunId);
      setRunning(false);
      setCurrentStage('cancelled');
      setActiveRunId(null);
    } catch {
      // ignore — run may have already finished
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
          {running && (
            <button className="cancel-btn" onClick={handleCancelRun}>
              ✕ Cancel
            </button>
          )}
        </div>
        {currentStage && (
          <div className={`stage-indicator${currentStage === 'failed' || currentStage === 'cancelled' ? ' error' : ''}`}>
            {STAGE_LABELS[currentStage] || currentStage}
          </div>
        )}
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
