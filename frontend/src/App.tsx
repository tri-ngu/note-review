import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import type { Question, QuestionSet } from './types/question';
import { renameConceptEverywhere } from './lib/renameConcept';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { HostPage } from './room/HostPage';
import { JoinPage } from './room/JoinPage';
import { PlayerPage } from './room/PlayerPage';

type SessionResponse = {
  status: 'empty' | 'checkpoint_pending' | 'generating' | 'ready' | 'failed';
  questions?: Question[];
};

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; questionSet: QuestionSet };

function errorMessageForSessionStatus(status: SessionResponse['status']): string {
  switch (status) {
    case 'empty':
      return 'No Question Set for this session yet — upload a Note and generate one first.';
    case 'checkpoint_pending':
      return 'A Note has been analyzed but generation has not been confirmed/run yet.';
    case 'generating':
      return 'Generation is still running for this session.';
    case 'failed':
      return 'The last generation run for this session failed.';
    default:
      return 'No Question Set is available for this session.';
  }
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail ?? `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

function FlashcardHome() {
  const [view, setView] = useState<'browse' | 'review'>('browse');
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetch('/session')
      .then((res) => res.json() as Promise<SessionResponse>)
      .then((data) => {
        if (cancelled) return;
        if (data.status === 'ready' && data.questions) {
          setLoad({ status: 'ready', questionSet: { questions: data.questions } });
        } else {
          setLoad({ status: 'error', message: errorMessageForSessionStatus(data.status) });
        }
      })
      .catch(() => {
        if (!cancelled) setLoad({ status: 'error', message: 'Could not reach the backend.' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const updateQuestion = async (index: number, updated: Question, renameFrom?: string): Promise<string | null> => {
    if (renameFrom) {
      const renameRes = await fetch(`/concepts/${encodeURIComponent(renameFrom)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: updated.concept }),
      });
      if (!renameRes.ok) {
        return `Could not rename concept: ${await errorDetail(renameRes)}`;
      }
    }

    const patchRes = await fetch(`/questions/${index + 1}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        concept: updated.concept,
        question_text: updated.question_text,
        options: updated.options,
        correct_answers: updated.correct_answers,
        is_select_all: updated.is_select_all,
        explanation: updated.explanation,
        page_number: updated.page_number,
      }),
    });
    if (!patchRes.ok) {
      return `Could not save question: ${await errorDetail(patchRes)}`;
    }
    const savedQuestion = (await patchRes.json()) as Question;

    setLoad((prev) => {
      if (prev.status !== 'ready') return prev;
      let questions = prev.questionSet.questions.map((q, i) => (i === index ? savedQuestion : q));
      if (renameFrom) {
        questions = renameConceptEverywhere(questions, renameFrom, updated.concept);
      }
      return { status: 'ready', questionSet: { questions } };
    });
    return null;
  };

  const handleCreateRoom = async () => {
    const response = await fetch('/rooms', { method: 'POST' });
    if (!response.ok) return;
    const data = (await response.json()) as { pin: string };
    navigate(`/host/${data.pin}`);
  };

  const handleJoinRoom = () => {
    navigate('/join');
  };

  if (load.status === 'loading') {
    return <p>Loading…</p>;
  }

  if (load.status === 'error') {
    return <p>{load.message}</p>;
  }

  if (view === 'review') {
    return <ReviewSession questionSet={load.questionSet} onExit={() => setView('browse')} />;
  }

  return (
    <FlashcardView
      questionSet={load.questionSet}
      onStartReview={() => setView('review')}
      onUpdateQuestion={updateQuestion}
      onCreateRoom={handleCreateRoom}
      onJoinRoom={handleJoinRoom}
    />
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<FlashcardHome />} />
        <Route path="/host/:pin" element={<HostPage />} />
        <Route path="/join" element={<JoinPage />} />
        <Route path="/join/:pin" element={<JoinPage />} />
        <Route path="/play/:pin" element={<PlayerPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
