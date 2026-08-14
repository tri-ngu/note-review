import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import type { ConceptAllocation } from '../types/allocation';
import { JournalShell } from '../components/JournalShell';
import styles from './UploadStage.module.css';

interface UploadStageProps {
  onUploaded: (concepts: ConceptAllocation[]) => void;
}

type UploadStatus = 'idle' | 'analyzing';

// Mirrors backend/app/extraction.py's MAX_UPLOAD_BYTES — client-side check is
// purely for instant feedback; the server re-checks and stays authoritative.
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

const ERROR_MESSAGES: Record<string, string> = {
  not_a_pdf: "That file isn't a PDF. Upload a PDF and try again.",
  file_too_large: 'This file is over the 20MB limit.',
  no_extractable_text: "This PDF has no selectable text (likely a scan) — we can't read it.",
  generation_failed: 'Something went wrong analyzing your Note. Please try again.',
  network: 'Could not reach the backend. Check your connection and try again.',
  unrecognized_upload_error: "This file couldn't be processed. Check it's a valid PDF and try again.",
};

function validateFile(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  if (!isPdf) return 'not_a_pdf';
  if (file.size > MAX_UPLOAD_BYTES) return 'file_too_large';
  return null;
}

export function UploadStage({ onUploaded }: UploadStageProps) {
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [targetCount, setTargetCount] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function selectFile(file: File) {
    const errCode = validateFile(file);
    if (errCode) {
      setErrorCode(errCode);
      setSelectedFile(null);
      return;
    }
    setErrorCode(null);
    setSelectedFile(file);
  }

  async function handleSubmit() {
    if (!selectedFile) return;
    setErrorCode(null);
    setStatus('analyzing');

    const formData = new FormData();
    formData.append('file', selectedFile);
    const trimmedCount = targetCount.trim();
    if (trimmedCount !== '') {
      formData.append('target_question_count', trimmedCount);
    }

    try {
      const res = await fetch('/upload', { method: 'POST', body: formData });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        let code: string;
        if (body.detail && ERROR_MESSAGES[body.detail]) {
          code = body.detail;
        } else if (res.status >= 400 && res.status < 500) {
          code = 'unrecognized_upload_error';
        } else {
          code = 'generation_failed';
        }
        setErrorCode(code);
        setStatus('idle');
        return;
      }
      const data = (await res.json()) as { concepts: ConceptAllocation[] };
      onUploaded(data.concepts);
    } catch {
      setErrorCode('network');
      setStatus('idle');
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) selectFile(file);
  }

  return (
    <JournalShell
      title="Note Review"
      subtitle="Upload a Note to generate a Question Set"
      stepEyebrow="Step 1"
      stepTitle="Upload"
      stepDescription="Upload a Note (PDF). It's read and broken into concepts before anything else happens."
    >
      <div
        className={`${styles.dropzone} ${dragOver ? styles.dragover : ''} ${errorCode ? styles.isError : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Drop a PDF here or browse to select one"
        onClick={() => status === 'idle' && !selectedFile && fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && status === 'idle' && !selectedFile) {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragOver(false);
        }}
        onDrop={onDrop}
      >
        {status === 'analyzing' ? (
          <div className={styles.dzFace}>
            <div className={styles.spinner} role="status" aria-live="polite" />
            <p>Analyzing your Note…</p>
          </div>
        ) : selectedFile ? (
          <div className={styles.dzFace}>
            <span className={styles.leaf}>❧</span>
            <p>{selectedFile.name}</p>
            <button
              type="button"
              className={styles.browseBtn}
              onClick={(e) => {
                e.stopPropagation();
                void handleSubmit();
              }}
            >
              Submit
            </button>
            <button
              type="button"
              className={styles.browseBtn}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFile(null);
                fileInputRef.current?.click();
              }}
            >
              Choose a different file
            </button>
          </div>
        ) : (
          <div className={styles.dzFace}>
            <span className={styles.leaf}>❧</span>
            <p>Drop the Note here</p>
            <p style={{ fontSize: '.85rem', opacity: 0.75 }}>— or —</p>
            <button
              type="button"
              className={styles.browseBtn}
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
            >
              Browse files
            </button>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className={styles.hidden}
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) selectFile(file);
            e.target.value = '';
          }}
        />
      </div>
      {errorCode && (
        <div className={styles.dzError} role="alert">
          {ERROR_MESSAGES[errorCode]}
        </div>
      )}

      <div className={styles.fieldRow}>
        <label htmlFor="qCount">Target question count</label>
        <input
          type="number"
          id="qCount"
          className={styles.qcountInput}
          min={1}
          placeholder="Auto — let AI decide"
          value={targetCount}
          disabled={status === 'analyzing'}
          onChange={(e) => setTargetCount(e.target.value)}
        />
      </div>
    </JournalShell>
  );
}
