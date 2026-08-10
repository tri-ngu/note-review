import { useState } from 'react';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { fixtureQuestionSet } from './fixtures/fixture';

function App() {
  const [view, setView] = useState<'browse' | 'review'>('browse');

  if (view === 'review') {
    return <ReviewSession questionSet={fixtureQuestionSet} onExit={() => setView('browse')} />;
  }

  return <FlashcardView questionSet={fixtureQuestionSet} onStartReview={() => setView('review')} />;
}

export default App;
