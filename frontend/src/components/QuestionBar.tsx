import { useState } from 'react';

export default function QuestionBar() {
  const [q, setQ] = useState('');
  return (
    <div className="ve-card" data-testid="question-bar">
      <input
        data-testid="question-input"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Ask a question about your documents..."
      />{' '}
      <button data-testid="ask-button" disabled>
        Find
      </button>
      <div>Model search arrives in a later slice.</div>
    </div>
  );
}
