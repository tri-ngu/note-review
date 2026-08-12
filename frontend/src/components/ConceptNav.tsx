import type { Question } from '../types/question';
import { trimConcept } from '../lib/trimConcept';
import styles from './ConceptNav.module.css';

interface ConceptNavProps {
  questions: Question[];
  currentIndex: number;
  onJump: (index: number) => void;
  disabled: boolean;
}

interface ConceptGroup {
  concept: string;
  indices: number[];
}

function groupByConcept(questions: Question[]): ConceptGroup[] {
  const groups: ConceptGroup[] = [];
  const lookup = new Map<string, ConceptGroup>();
  questions.forEach((q, i) => {
    let group = lookup.get(q.concept);
    if (!group) {
      group = { concept: q.concept, indices: [] };
      lookup.set(q.concept, group);
      groups.push(group);
    }
    group.indices.push(i);
  });
  return groups;
}

export function ConceptNav({ questions, currentIndex, onJump, disabled }: ConceptNavProps) {
  const groups = groupByConcept(questions);

  return (
    <nav className={styles.nav} aria-label="Jump to question">
      {groups.map((group) => (
        <div key={group.concept} className={styles.group}>
          <p className={styles.conceptLabel}>{trimConcept(group.concept)}</p>
          <ul className={styles.questionList}>
            {group.indices.map((index) => (
              <li key={index}>
                <button
                  type="button"
                  className={index === currentIndex ? `${styles.questionBtn} ${styles.active}` : styles.questionBtn}
                  onClick={() => onJump(index)}
                  disabled={disabled}
                >
                  Question {index + 1}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
