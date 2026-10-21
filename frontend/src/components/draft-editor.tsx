"use client";

import { useActionState, useEffect, useRef, useState, useTransition } from "react";

import {
  generateDraftVersion,
  markDraftReviewed,
  saveDraftVersion,
  type DraftActionState,
} from "@/actions/drafts";
import { cn } from "@/components/ui";

const INITIAL: DraftActionState = { status: "idle" };

export function DraftEditor({
  leadId,
  revisionId,
  subject,
  body,
  dmBody,
  status,
  method,
  canGenerate,
}: {
  leadId: string;
  revisionId: string;
  subject: string;
  body: string;
  dmBody: string;
  status: string;
  method: string;
  canGenerate: boolean;
}) {
  const [state, formAction, pending] = useActionState(saveDraftVersion, INITIAL);
  const [reviewState, startReview] = useTransition();
  const [generateState, startGenerate] = useTransition();
  const [notice, setNotice] = useState<{ ok: boolean; message: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [copied, setCopied] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  // The draft text is held in client state, not in the DOM, so a background
  // refresh (the live progress poll) can never clear an unsaved edit
  // (PRD 6.6 / QA V29). The server-provided values seed the state once; the
  // user edits are never overwritten by a re-render.
  //
  // React's "adjusting state when a prop changes" pattern: the incoming server
  // values are tracked, and the local state is re-seeded during render when
  // they change and the user has no unsaved edits.
  const [serverValues, setServerValues] = useState({ subject, body, dmBody });
  const [subjectValue, setSubjectValue] = useState(subject);
  const [bodyValue, setBodyValue] = useState(body);
  const [dmBodyValue, setDmBodyValue] = useState(dmBody);

  if (
    !dirty &&
    (serverValues.subject !== subject ||
      serverValues.body !== body ||
      serverValues.dmBody !== dmBody)
  ) {
    setServerValues({ subject, body, dmBody });
    setSubjectValue(subject);
    setBodyValue(body);
    setDmBodyValue(dmBody);
  }

  // Warn before leaving with unsaved edits (PRD 4.5).
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  async function handleCopy() {
    const text = [subjectValue, bodyValue, dmBodyValue]
      .filter((part) => part.trim())
      .join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setNotice({ ok: true, message: "Copied. Copying never marks a draft as sent." });
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setNotice({ ok: false, message: "Could not copy. Select the text and copy manually." });
    }
  }

  function handleExport() {
    const text = [subjectValue, bodyValue, dmBodyValue]
      .filter((part) => part.trim())
      .join("\n\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `draft-${leadId}.txt`;
    link.click();
    URL.revokeObjectURL(url);
    setNotice({ ok: true, message: "Exported as text. Exporting never marks a draft as sent." });
  }

  return (
    <div className="space-y-5">
      <form
        ref={formRef}
        action={formAction}
        onChange={() => setDirty(true)}
        className="space-y-5"
      >
        <input type="hidden" name="leadId" value={leadId} />
        <input type="hidden" name="revisionId" value={revisionId} />

        <div className="space-y-1.5">
          <label htmlFor="subject" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
            Email subject
          </label>
          <input
            id="subject"
            name="subject"
            value={subjectValue}
            onChange={(event) => {
              setSubjectValue(event.target.value);
              setDirty(true);
            }}
            className="field"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="body" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
            Email body
          </label>
          <textarea
            id="body"
            name="body"
            value={bodyValue}
            onChange={(event) => {
              setBodyValue(event.target.value);
              setDirty(true);
            }}
            rows={11}
            className="field font-mono text-[13px] leading-relaxed"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="dm_body" className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
            Instagram DM
          </label>
          <textarea
            id="dm_body"
            name="dm_body"
            value={dmBodyValue}
            onChange={(event) => {
              setDmBodyValue(event.target.value);
              setDirty(true);
            }}
            rows={4}
            className="field font-mono text-[13px] leading-relaxed"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={pending}
            className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400rounded-lg border border-ink-600 px-4 py-2 text-sm font-semibold text-mist-200 transition-colors hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pending ? "Saving…" : "Save"}
          </button>

          <button
            type="button"
            onClick={() =>
              startReview(async () => {
                const result = await markDraftReviewed(leadId, revisionId);
                setNotice({ ok: result.status === "saved", message: result.message ?? "" });
              })
            }
            disabled={reviewState || !revisionId}
            className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400rounded-lg border border-accent-600/60 bg-accent-600/15 px-4 py-2 text-sm font-semibold text-accent-200 transition-colors hover:bg-accent-600/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {reviewState ? "Working…" : "Mark reviewed"}
          </button>

          <button
            type="button"
            onClick={handleCopy}
            className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400rounded-lg border border-ink-600 px-4 py-2 text-sm font-semibold text-mist-200 transition-colors hover:bg-ink-800"
          >
            {copied ? "Copied" : "Copy"}
          </button>

          <button
            type="button"
            onClick={handleExport}
            className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400rounded-lg border border-ink-600 px-4 py-2 text-sm font-semibold text-mist-200 transition-colors hover:bg-ink-800"
          >
            Export text
          </button>

          <button
            type="button"
            onClick={() =>
              startGenerate(async () => {
                const result = await generateDraftVersion(leadId, revisionId, "email");
                setNotice({ ok: result.status === "saved", message: result.message ?? "" });
              })
            }
            disabled={generateState || !canGenerate}
            title={
              canGenerate
                ? "Creates a new version; the current one is kept."
                : "AI generation is unavailable. Manual writing still works."
            }
            className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400rounded-lg border border-sky-500/40 bg-sky-500/15 px-4 py-2 text-sm font-semibold text-sky-300 transition-colors hover:bg-sky-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generateState ? "Requesting…" : "Generate new version"}
          </button>
        </div>

        {state.status !== "idle" && state.message ? (
          <p
            className={cn("text-xs", state.status === "saved" ? "text-accent-300" : "text-rose-alert")}
            role="status"
          >
            {state.message}
          </p>
        ) : null}
        {notice ? (
          <p
            className={cn("text-xs", notice.ok ? "text-accent-300" : "text-rose-alert")}
            role="status"
          >
            {notice.message}
          </p>
        ) : null}
      </form>

      <p className="text-[11px] text-mist-400">
        Drafts are never sent. Version {revisionId || "—"} · {method || "manual"} ·{" "}
        {status ? status.replace(/_/g, " ") : "needs review"}. Saving creates a new version and
        keeps the previous one in the history.
      </p>
    </div>
  );
}
