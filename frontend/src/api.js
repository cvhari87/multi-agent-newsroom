/** Thin API client — all calls go through the Vite proxy in dev. */

const BASE = '/api';

export async function triggerRun() {
  const res = await fetch(`${BASE}/run`, { method: 'POST' });
  return res.json();
}

export async function cancelRun(runId) {
  const res = await fetch(`${BASE}/run/${runId}/cancel`, { method: 'POST' });
  return res.json();
}

export async function fetchRuns() {
  const res = await fetch(`${BASE}/runs`);
  return (await res.json()).runs;
}

export async function fetchStories({ tag = null, runId = null } = {}) {
  const params = new URLSearchParams();
  if (tag) params.set('tag', tag);
  if (runId) params.set('run_id', runId);
  const qs = params.toString();
  const res = await fetch(`${BASE}/stories${qs ? '?' + qs : ''}`);
  return (await res.json()).stories;
}

export async function fetchStory(id) {
  const res = await fetch(`${BASE}/stories/${id}`);
  if (!res.ok) throw new Error('Story not found');
  return res.json();
}
