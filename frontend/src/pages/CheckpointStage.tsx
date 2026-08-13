import { useState } from 'react';
import type { ConceptAllocation } from '../types/allocation';
import { rebalanceWeightsAfterDelete } from '../lib/rebalanceWeights';
import { computeCheckpointTotals } from '../lib/checkpointTotals';
import { JournalShell } from '../components/JournalShell';
import styles from './CheckpointStage.module.css';

interface CheckpointStageProps {
  allocations: ConceptAllocation[];
  onConfirm: (allocations: ConceptAllocation[]) => void;
}

interface Entry extends ConceptAllocation {
  id: string;
}

function toId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2);
}

export function CheckpointStage({ allocations, onConfirm }: CheckpointStageProps) {
  const [entries, setEntries] = useState<Entry[]>(() => allocations.map((a) => ({ ...a, id: toId() })));
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [confirmed, setConfirmed] = useState(false);

  const totals = computeCheckpointTotals(entries);

  function updateEntry(id: string, patch: Partial<Pick<Entry, 'concept' | 'weight_percentage' | 'question_count'>>) {
    setConfirmed(false);
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }

  function deleteEntry(id: string) {
    setConfirmed(false);
    setEntries((prev) => {
      const removed = prev.find((e) => e.id === id);
      const rest = prev.filter((e) => e.id !== id);
      if (!removed) return rest;
      return rebalanceWeightsAfterDelete(rest, removed.weight_percentage);
    });
  }

  function toggleQuote(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleConfirm() {
    if (!totals.isBalanced) return;
    setConfirmed(true);
    onConfirm(entries.map(({ id: _id, ...rest }) => rest));
  }

  return (
    <JournalShell
      title="Note Review"
      subtitle="Concepts found in your Note"
      stepEyebrow="Step 2"
      stepTitle="Checkpoint"
      stepDescription="Concepts found in your Note, each with a weight and question count. Adjust or remove any before continuing."
    >
      <div className={styles.totalBar}>
        <div className={`${styles.totalFigure} ${!totals.isBalanced ? styles.warn : ''}`}>
          Total weight: <span className={styles.totalFigureValue}>{totals.totalWeight.toFixed(1)}</span>%
        </div>
        <div className={styles.qTotal}>Total questions: {totals.totalQuestions}</div>
      </div>
      <p className={`${styles.totalMsg} ${!totals.isBalanced ? styles.warn : ''}`}>
        {totals.isBalanced
          ? 'Ready to continue.'
          : `Weights must add up to 100% before you can continue — currently ${totals.totalWeight.toFixed(1)}%.`}
      </p>

      <div className={styles.entries}>
        {entries.map((entry, i) => {
          const expanded = expandedIds.has(entry.id);
          const snippet = entry.snippets[0];
          return (
            <div key={entry.id} className={styles.entry}>
              <div className={styles.entryHead}>
                <span className={styles.entryIndex}>{String(i + 1).padStart(2, '0')}</span>
                <input
                  type="text"
                  className={styles.entryNameInput}
                  aria-label="Concept name"
                  value={entry.concept}
                  onChange={(e) => updateEntry(entry.id, { concept: e.target.value })}
                />
                <button type="button" className={styles.strikeBtn} onClick={() => deleteEntry(entry.id)}>
                  Delete
                </button>
              </div>
              <div className={styles.entryFields}>
                <div className={styles.fieldBlock}>
                  <label htmlFor={`weight-${entry.id}`}>Weight %</label>
                  <input
                    id={`weight-${entry.id}`}
                    type="number"
                    min={0}
                    step={0.01}
                    value={entry.weight_percentage}
                    onChange={(e) => updateEntry(entry.id, { weight_percentage: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <div className={styles.fieldBlock}>
                  <label htmlFor={`count-${entry.id}`}>Question count</label>
                  <input
                    id={`count-${entry.id}`}
                    type="number"
                    min={0}
                    step={1}
                    value={entry.question_count}
                    onChange={(e) => updateEntry(entry.id, { question_count: parseInt(e.target.value, 10) || 0 })}
                  />
                </div>
              </div>
              {snippet && (
                <>
                  <button type="button" className={styles.toggleQuote} onClick={() => toggleQuote(entry.id)}>
                    {expanded ? '❧ Hide source quote' : '❧ View source quote'}
                  </button>
                  {expanded && (
                    <div className={styles.quotePanel}>
                      <p>&ldquo;{snippet.quote}&rdquo;</p>
                      <p className={styles.quotePage}>Page {snippet.page_number}</p>
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.confirmRow}>
        <button className={styles.confirmBtn} disabled={!totals.isBalanced} onClick={handleConfirm}>
          Confirm and Continue
        </button>
        {confirmed && <span className={styles.confirmNote}>Confirmed.</span>}
      </div>
    </JournalShell>
  );
}
