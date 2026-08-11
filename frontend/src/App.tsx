import { useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import type { Question, QuestionSet } from './types/question';
import { renameConceptEverywhere } from './lib/renameConcept';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { fixtureQuestionSet } from './fixtures/fixture';
import { HostPage } from './room/HostPage';
import { JoinPage } from './room/JoinPage';
import { PlayerPage } from './room/PlayerPage';

function FlashcardHome() {
  const [view, setView] = useState<'browse' | 'review'>('browse');
  const [questionSet, setQuestionSet] = useState<QuestionSet>(fixtureQuestionSet);
  const navigate = useNavigate();

  const updateQuestion = (index: number, updated: Question, renameFrom?: string) => {
    setQuestionSet((prev) => {
      let questions = prev.questions.map((q, i) => (i === index ? updated : q));
      if (renameFrom) {
        questions = renameConceptEverywhere(questions, renameFrom, updated.concept);
      }
      return { questions };
    });
  };

  const handleCreateRoom = async () => {
    const response = await fetch('/rooms', { method: 'POST' });
    if (!response.ok) return;
    const data = (await response.json()) as { pin: string };
    navigate(`/host/${data.pin}`);
  };

  if (view === 'review') {
    return <ReviewSession questionSet={questionSet} onExit={() => setView('browse')} />;
  }

  return (
    <FlashcardView
      questionSet={questionSet}
      onStartReview={() => setView('review')}
      onUpdateQuestion={updateQuestion}
      onCreateRoom={handleCreateRoom}
    />
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<FlashcardHome />} />
        <Route path="/host/:pin" element={<HostPage />} />
        <Route path="/join/:pin" element={<JoinPage />} />
        <Route path="/play/:pin" element={<PlayerPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
