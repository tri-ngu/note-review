import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import type { Question, QuestionSet } from './types/question';
import type { ConceptAllocation } from './types/allocation';
import { renameConceptEverywhere } from './lib/renameConcept';
import { INITIAL_PROGRESS, nextGenerationProgress, type GenerationEvent, type GenerationProgress } from './lib/generationProgress';
import { runGeneration } from './lib/runGeneration';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { UploadStage } from './pages/UploadStage';
import { CheckpointStage } from './pages/CheckpointStage';
import { GeneratingStage } from './pages/GeneratingStage';
import { HostPage } from './room/HostPage';
import { JoinPage } from './room/JoinPage';
import { PlayerPage } from './room/PlayerPage';

type SessionResponse = {
  status: 'empty' | 'checkpoint_pending' | 'generating' | 'ready' | 'failed';
  allocations?: ConceptAllocation[];
  questions?: Question[];
};

type Stage =
  | { name: 'loading' }
  | { name: 'session_error'; message: string }
  | { name: 'upload' }
  | { name: 'checkpoint'; allocations: ConceptAllocation[] }
  | { name: 'generating'; mode: 'live' | 'resumed'; progress: GenerationProgress }
  | { name: 'failed' }
  | { name: 'ready'; view: 'browse' | 'review'; questionSet: QuestionSet };

const SESSION_POLL_MS = 3000;

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail ?? `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

function SessionFlow() {
  const [stage, setStage] = useState<Stage>({ name: 'loading' });
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetch('/session')
      .then((res) => res.json() as Promise<SessionResponse>)
      .then((data) => {
        if (cancelled) return;
        if (data.status === 'ready' && data.questions) {
          setStage({ name: 'ready', view: 'browse', questionSet: { questions: data.questions } });
        } else if (data.status === 'checkpoint_pending' && data.allocations) {
          setStage({ name: 'checkpoint', allocations: data.allocations });
        } else if (data.status === 'generating') {
          setStage({ name: 'generating', mode: 'resumed', progress: INITIAL_PROGRESS });
        } else if (data.status === 'failed') {
          setStage({ name: 'failed' });
        } else {
          setStage({ name: 'upload' });
        }
      })
      .catch(() => {
        if (!cancelled) setStage({ name: 'session_error', message: 'Could not reach the backend.' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Resumed mid-generation on reload: no live SSE stream to attach to, so poll
  // GET /session until the background pipeline task (which keeps running
  // server-side regardless of client connection) settles.
  useEffect(() => {
    if (stage.name !== 'generating' || stage.mode !== 'resumed') return;
    let cancelled = false;
    const interval = setInterval(() => {
      fetch('/session')
        .then((res) => res.json() as Promise<SessionResponse>)
        .then((data) => {
          if (cancelled) return;
          if (data.status === 'ready' && data.questions) {
            setStage({ name: 'ready', view: 'browse', questionSet: { questions: data.questions } });
          } else if (data.status === 'failed') {
            setStage({ name: 'failed' });
          }
        })
        .catch(() => {
          /* transient network hiccup — keep polling */
        });
    }, SESSION_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [stage]);

  function handleUploaded(concepts: ConceptAllocation[]) {
    setStage({ name: 'checkpoint', allocations: concepts });
  }

  function runLiveGeneration(endpoint: '/generate' | '/generate/retry', body?: unknown) {
    setStage({ name: 'generating', mode: 'live', progress: INITIAL_PROGRESS });
    void runGeneration({
      endpoint,
      body,
      onEvent: (evt: GenerationEvent) => {
        setStage((prev) => {
          if (prev.name !== 'generating') return prev;
          return { ...prev, progress: nextGenerationProgress(prev.progress, evt) };
        });
        if (evt.stage === 'done') {
          setStage({ name: 'ready', view: 'browse', questionSet: evt.question_set });
        } else if (evt.stage === 'error') {
          setStage({ name: 'failed' });
        }
      },
    });
  }

  function handleConfirm(allocations: ConceptAllocation[]) {
    runLiveGeneration('/generate', { allocations });
  }

  function handleRetry() {
    runLiveGeneration('/generate/retry');
  }

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

    setStage((prev) => {
      if (prev.name !== 'ready') return prev;
      let questions = prev.questionSet.questions.map((q, i) => (i === index ? savedQuestion : q));
      if (renameFrom) {
        questions = renameConceptEverywhere(questions, renameFrom, updated.concept);
      }
      return { ...prev, questionSet: { questions } };
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

  switch (stage.name) {
    case 'loading':
      return <p>Loading…</p>;
    case 'session_error':
      return <p>{stage.message}</p>;
    case 'upload':
      return <UploadStage onUploaded={handleUploaded} />;
    case 'checkpoint':
      return <CheckpointStage allocations={stage.allocations} onConfirm={handleConfirm} />;
    case 'generating':
      return <GeneratingStage progress={stage.progress} resumed={stage.mode === 'resumed'} />;
    case 'failed':
      return (
        <div>
          <p>Generation failed. Please try again.</p>
          <button onClick={handleRetry}>Retry</button>
        </div>
      );
    case 'ready':
      if (stage.view === 'review') {
        return (
          <ReviewSession
            questionSet={stage.questionSet}
            onExit={() => setStage((prev) => (prev.name === 'ready' ? { ...prev, view: 'browse' } : prev))}
          />
        );
      }
      return (
        <FlashcardView
          questionSet={stage.questionSet}
          onStartReview={() => setStage((prev) => (prev.name === 'ready' ? { ...prev, view: 'review' } : prev))}
          onUpdateQuestion={updateQuestion}
          onCreateRoom={handleCreateRoom}
          onJoinRoom={handleJoinRoom}
        />
      );
  }
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SessionFlow />} />
        <Route path="/host/:pin" element={<HostPage />} />
        <Route path="/join" element={<JoinPage />} />
        <Route path="/join/:pin" element={<JoinPage />} />
        <Route path="/play/:pin" element={<PlayerPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
