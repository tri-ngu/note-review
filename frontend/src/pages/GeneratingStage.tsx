import type { GenerationProgress } from '../lib/generationProgress';
import { JournalShell } from '../components/JournalShell';
import styles from './GeneratingStage.module.css';

interface GeneratingStageProps {
  progress: GenerationProgress;
  resumed?: boolean;
}

function dialGradient(pct: number): string {
  const clamped = Math.max(0, Math.min(100, pct));
  return `conic-gradient(var(--forest) 0% ${clamped}%, var(--sage) ${clamped}% 100%)`;
}

export function GeneratingStage({ progress, resumed }: GeneratingStageProps) {
  return (
    <JournalShell
      title="Note Review"
      subtitle="Writing your Question Set"
      stepEyebrow="Step 3"
      stepTitle="Generating Questions"
      stepDescription="Questions are written from the confirmed concepts, then checked and revised over several rounds."
    >
      <div className={styles.trailWrap}>
        <div className={styles.growDial} style={{ background: dialGradient(progress.percent) }}>
          <div className={styles.growDialInner}>
            <span className={styles.pctNum}>{progress.percent}%</span>
            <span className={styles.pctCap}>Complete</span>
          </div>
        </div>
        <p className={styles.stageLabel}>
          {resumed ? 'A generation run for this session is already in progress — checking back for results…' : progress.label}
        </p>
      </div>
    </JournalShell>
  );
}
