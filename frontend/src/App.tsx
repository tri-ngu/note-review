import { useState } from 'react';
import type { Question, QuestionSet } from './types/question';
import { renameConceptEverywhere } from './lib/renameConcept';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { fixtureQuestionSet } from './fixtures/fixture';

function App() {
  const [view, setView] = useState<'browse' | 'review'>('browse');
  const [questionSet, setQuestionSet] = useState<QuestionSet>(fixtureQuestionSet);

  const updateQuestion = (index: number, updated: Question, renameFrom?: string) => {
    setQuestionSet((prev) => {
      let questions = prev.questions.map((q, i) => (i === index ? updated : q));
      if (renameFrom) {
        questions = renameConceptEverywhere(questions, renameFrom, updated.concept);
      }
      return { questions };
    });
  };

  if (view === 'review') {
    return <ReviewSession questionSet={questionSet} onExit={() => setView('browse')} />;
  }

  return (
    <FlashcardView
      questionSet={questionSet}
      onStartReview={() => setView('review')}
      onUpdateQuestion={updateQuestion}
    />
  );
}

export default App;
