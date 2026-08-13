import type { ReactNode } from 'react';
import styles from './JournalShell.module.css';

interface JournalShellProps {
  title: string;
  subtitle: string;
  stepEyebrow: string;
  stepTitle: string;
  stepDescription: string;
  children: ReactNode;
}

export function JournalShell({ title, subtitle, stepEyebrow, stepTitle, stepDescription, children }: JournalShellProps) {
  return (
    <div className={styles.journal}>
      <div className={styles.cover}>
        <span className={styles.leaf}>❧</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <section aria-labelledby="stage-heading">
        <div className={styles.sectionTab}>
          <p className={styles.tabEyebrow}>{stepEyebrow}</p>
          <h2 id="stage-heading">{stepTitle}</h2>
          <p>{stepDescription}</p>
        </div>
        <div className={styles.page}>{children}</div>
      </section>
    </div>
  );
}
