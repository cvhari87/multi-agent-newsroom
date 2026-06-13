const ALL_TAGS = [
  'LLMs', 'Tooling', 'Infrastructure', 'Research', 'Safety',
  'Agents', 'Data', 'Benchmarks', 'Open Source', 'Industry',
];

export default function TagFilter({ active, onChange }) {
  return (
    <div className="tag-filter">
      <button
        className={`tag-btn${active === null ? ' active' : ''}`}
        onClick={() => onChange(null)}
      >
        All
      </button>
      {ALL_TAGS.map((tag) => (
        <button
          key={tag}
          className={`tag-btn${active === tag ? ' active' : ''}`}
          onClick={() => onChange(active === tag ? null : tag)}
        >
          {tag}
        </button>
      ))}
    </div>
  );
}
