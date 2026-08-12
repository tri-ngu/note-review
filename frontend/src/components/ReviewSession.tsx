import { useState } from 'react';
import type { QuestionSet } from '../types/question';
import { shuffleQuestions } from '../lib/shuffle';
import { isQuestionCorrect } from '../lib/scoring';
import { ReviewCard } from './ReviewCard';
import { Summary } from './Summary';
import styles from './ReviewSession.module.css';

interface ReviewSessionProps {
  questionSet: QuestionSet;
  onExit: () => void;
}

interface AnswerRecord {
  selected: number[];
  submitted: boolean;
}

export function ReviewSession({ questionSet, onExit }: ReviewSessionProps) {
  const [shuffled, setShuffled] = useState(() => shuffleQuestions(questionSet.questions));
  const [answers, setAnswers] = useState<AnswerRecord[]>(() => shuffled.map(() => ({ selected: [], submitted: false })));
  const [currentIndex, setCurrentIndex] = useState(0);
  const [phase, setPhase] = useState<'active' | 'summary'>('active');

  const current = shuffled[currentIndex];
  const currentAnswer = answers[currentIndex];

  const toggleOption = (optionNumber: number) => {
    setAnswers((prev) =>
      prev.map((a, i) => {
        if (i !== currentIndex || a.submitted) return a;
        if (current.is_select_all) {
          const has = a.selected.includes(optionNumber);
          return { ...a, selected: has ? a.selected.filter((n) => n !== optionNumber) : [...a.selected, optionNumber] };
        }
        return { ...a, selected: [optionNumber] };
      }),
    );
  };

  const submit = () => {
    setAnswers((prev) => prev.map((a, i) => (i === currentIndex ? { ...a, submitted: true } : a)));
  };

  const goNext = () => {
    if (currentIndex + 1 < shuffled.length) {
      setCurrentIndex((i) => i + 1);
    } else {
      setPhase('summary');
    }
  };

  const restart = () => {
    const fresh = shuffleQuestions(questionSet.questions);
    setShuffled(fresh);
    setAnswers(fresh.map(() => ({ selected: [], submitted: false })));
    setCurrentIndex(0);
    setPhase('active');
  };

  if (phase === 'summary') {
    const results = shuffled.map((q, i) => ({
      question: q,
      selected: answers[i].selected,
      correct: isQuestionCorrect(answers[i].selected, q.correct_answers),
    }));
    const score = results.filter((r) => r.correct).length;
    return <Summary total={shuffled.length} score={score} results={results} onRestart={restart} onExit={onExit} />;
  }

  return (
    <main className={styles.theme}>
      <div className={styles.cardStage}>
        <ReviewCard
          question={current}
          groupName={`review-option-${currentIndex}`}
          selected={currentAnswer.selected}
          submitted={currentAnswer.submitted}
          onToggleOption={toggleOption}
          onSubmit={submit}
        />
        <p className={styles.hint}>{currentAnswer.submitted ? 'tap next to continue' : 'select an answer, then submit'}</p>
        <div className={styles.cardNav}>
          <button className={styles.exitBtn} onClick={onExit}>
            Exit Review
          </button>
          <span className={styles.progress}>
            Card {currentIndex + 1} of {shuffled.length}
          </span>
          <button className={styles.navBtn} onClick={goNext} disabled={!currentAnswer.submitted}>
            next ›
          </button>
        </div>
      </div>
    </main>
  );
}
