export default function StoryCard({ story, onClick }) {
  const score = story.eval_score?.toFixed(1) ?? '—';
  const flag = story.eval_score < 5 ? ' ⚠️' : '';

  return (
    <article className="story-card" onClick={onClick}>
      <div className="story-card-header">
        <span className={`score${story.eval_score < 5 ? ' low' : ''}`}>
          {score}/10{flag}
        </span>
        <span className="source-count" title="Sources">
          {story.source_count ?? 0} source{story.source_count !== 1 ? 's' : ''}
        </span>
      </div>
      <h3 className="story-title">{story.title}</h3>
      <p className="story-summary">{story.summary}</p>
      <div className="story-tags">
        {(story.topic_tags || []).map((tag) => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>
      {story.angle && <p className="story-angle"><em>{story.angle}</em></p>}
    </article>
  );
}
