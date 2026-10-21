"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";

import { addContact, type ActionResult } from "@/actions/fit";
import { cn } from "@/components/ui";

export function ManualContactForm({ leadId }: { leadId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [type, setType] = useState<"email" | "phone">("email");
  const [value, setValue] = useState("");
  const [source, setSource] = useState("");
  const [feedback, setFeedback] = useState<ActionResult | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    startTransition(async () => {
      const result = await addContact(leadId, { type, value, sourceUrl: source });
      setFeedback(result);
      if (result.ok) {
        setValue("");
        setSource("");
        router.refresh();
      }
    });
  }

  return (
    <form onSubmit={submit} className="space-y-2 border-t border-ink-800 px-5 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-mist-400">
        Add contact with source
      </p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="sm:w-28">
          <label htmlFor={`manual-type-${leadId}`} className="mb-1 block text-xs text-mist-300">
            Type
          </label>
          <select
            id={`manual-type-${leadId}`}
            className="field"
            value={type}
            onChange={(event) =>
              setType(event.target.value === "phone" ? "phone" : "email")
            }
          >
            <option value="email">Email</option>
            <option value="phone">Phone</option>
          </select>
        </div>
        <div className="sm:flex-1">
          <label htmlFor={`manual-value-${leadId}`} className="mb-1 block text-xs text-mist-300">
            Contact value
          </label>
          <input
            id={`manual-value-${leadId}`}
            className="field"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={type === "email" ? "name@example.com" : "+1 415 555 0199"}
            required
          />
        </div>
        <div className="sm:flex-1">
          <label htmlFor={`manual-source-${leadId}`} className="mb-1 block text-xs text-mist-300">
            Source URL
          </label>
          <input
            id={`manual-source-${leadId}`}
            className="field"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder="https://…"
            required
          />
        </div>
        <button
          type="submit"
          disabled={pending}
          className=" focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400min-h-11 shrink-0 rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-mist-200 hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? "Adding…" : "Add contact"}
        </button>
      </div>
      {feedback ? (
        <p
          role="status"
          className={cn("text-xs", feedback.ok ? "text-accent-300" : "text-rose-alert")}
        >
          {feedback.message}
        </p>
      ) : null}
    </form>
  );
}
