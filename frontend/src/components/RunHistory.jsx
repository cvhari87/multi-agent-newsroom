import { useEffect, useState } from 'react';
import { fetchRuns } from '../api';

const STAGE_LABELS = {
  starting: 'Starting',
  research: 'Research',
  verification: 'Verification',
  editor_review: 'Editor Review',
  editorial: 'Editorial',
  writing: 'Writing',
  evaluation: 'Evaluation',
  revision_loop: 'Revisions',
  output: 'Output',
  done: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export default function RunHistory({ onSelectRun }) {
  const [runs, setRuns] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (open) {
      fetchRuns().then(setRuns);
      const interval = setInterval(() => fetchRuns().then(setRuns), 3000);
      return () => clearInterval(interval);
    }
  }, [open]);

  return (
    <div className="run-history">
      <button className="toggle-btn" onClick={() => setOpen(!open)}>
        {open ? 'Hide' : 'Show'} Run History
      </button>
      {open && (
        <table className="runs-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Status</th>
              <th>Stage</th>
              <th>Stories</th>
              <th>Avg Score</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr
                key={run.id}
                className={`run-row ${run.status}`}
                onClick={() => onSelectRun(run.id)}
              >
                <td className="run-id">{run.id.slice(0, 8)}</td>
                <td>
                  <span className={`status-badge ${run.status}`}>{run.status}</span>
                </td>
                <td className="stage-cell">
                  {run.status === 'running' ? (
                    <span className="stage-running">
                      {STAGE_LABELS[run.current_stage] || run.current_stage || '…'}
                    </span>
                  ) : (
                    <span className="stage-done">
                      {STAGE_LABELS[run.current_stage] || '—'}
                    </span>
                  )}
                </td>
                <td>{run.story_count ?? '—'}</td>
                <td>{run.eval_score_avg?.toFixed(1) ?? '—'}</td>
                <td>{run.started_at ? new Date(run.started_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6} className="empty">No runs yet</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
