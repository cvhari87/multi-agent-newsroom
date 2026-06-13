import { useEffect, useState } from 'react';
import { fetchStory } from '../api';

export default function StoryDetail({ storyId, onBack }) {
  const [story, setStory] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStory(storyId).then(setStory).catch((e) => setError(e.message));
  }, [storyId]);

  if (error) return <div className="error">Error: {error}</div>;
  if (!story) return <div className="loading">Loading…</div>;

  return (
    <div className="story-detail">
      <button className="back-btn" onClick={onBack}>← Back to stories</button>

      <h1>{story.title}</h1>

      <div className="story-meta">
        <span className={`score${story.eval_score < 5 ? ' low' : ''}`}>
          {story.eval_score?.toFixed(1)}/10
        </span>
        <span className="confidence">
          Confidence: {(story.confidence_score * 100).toFixed(0)}%
        </span>
        <div className="story-tags">
          {(story.topic_tags || []).map((tag) => (
            <span key={tag} className="tag">{tag}</span>
          ))}
        </div>
      </div>

      {story.angle && (
        <p className="story-angle"><em>Angle: {story.angle}</em></p>
      )}

      <div
        className="briefing-content"
        dangerouslySetInnerHTML={{ __html: markdownToHtml(story.full_briefing || '') }}
      />

      {story.eval_notes && (
        <blockquote className="eval-notes">
          <strong>QC Notes:</strong> {story.eval_notes}
        </blockquote>
      )}

      {story.sources && story.sources.length > 0 && (
        <div className="sources-section">
          <h3>Sources</h3>
          <ul>
            {story.sources.map((s, i) => (
              <li key={i}>
                <a href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Minimal markdown → HTML for briefing display. */
function markdownToHtml(md) {
  return md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>');
}
