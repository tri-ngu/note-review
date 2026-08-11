import { useState } from 'react';
import type { QuestionStartMessage } from '../../types/room';
import styles from './QuestionPanel.module.css';

interface QuestionPanelProps {
  question: QuestionStartMessage;
  onSubmit: (selected: number[]) => void;
}

export function QuestionPanel({ question, onSubmit }: QuestionPanelProps) {
  const [selected, setSelected] = useState<number[]>([]);
  const [submitted, setSubmitted] = useState(false);

  const toggleOption = (position: number) => {
    if (submitted) return;
    if (!question.is_select_all) {
      setSelected([position]);
      setSubmitted(true);
      onSubmit([position]);
      return;
    }
    setSelected((prev) => (prev.includes(position) ? prev.filter((p) => p !== position) : [...prev, position]));
  };

  const submitSelectAll = () => {
    if (submitted || selected.length === 0) return;
    setSubmitted(true);
    onSubmit(selected);
  };

  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Round {question.round} of {question.total_rounds}
        </p>
        <h1 className={styles.questionText}>{question.question_text}</h1>
        <div className={styles.options}>
          {question.options.map((option, i) => {
            const position = i + 1;
            const isSelected = selected.includes(position);
            return (
              <button
                key={position}
                className={isSelected ? styles.optionSelected : styles.option}
                onClick={() => toggleOption(position)}
                disabled={submitted}
              >
                {option}
              </button>
            );
          })}
        </div>
        {question.is_select_all && (
          <button
            className={styles.submitBtn}
            onClick={submitSelectAll}
            disabled={submitted || selected.length === 0}
          >
            Submit
          </button>
        )}
        {submitted && <p className={styles.waiting}>Waiting for other players…</p>}
      </div>
    </main>
  );
}
