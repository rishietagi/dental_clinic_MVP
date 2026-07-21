"use client";

// The Files section on the patient profile (step 5.6): X-rays, photos, documents.
//
// Reads are any active staff; UPLOAD + ARCHIVE are dentist/admin only (clinical
// records are the dentist's — mirrors the "Record visit" gate). The API enforces
// this regardless; the hidden controls are convenience.
//
// Image files preview inline (fetched as authorized blobs — the content endpoint
// needs the token, so a plain <img src> wouldn't work). Documents/PDFs get a
// "Download" action that fetches the authorized blob and saves it.

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatVisitDate } from "@/lib/use-visits";
import {
  archivePatientFile,
  fetchFileBlobUrl,
  formatFileSize,
  uploadPatientFile,
  usePatientFiles,
  useFilePreview,
  type FileKind,
  type PatientFile,
} from "@/lib/use-patient-files";

const KINDS: FileKind[] = ["xray", "photo", "document"];

const controlClass =
  "flex rounded-md border border-input bg-transparent px-3 py-2 text-sm " +
  "shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] " +
  "focus-visible:ring-ring/50";

export function PatientFilesSection({
  patientId,
  canManage,
}: {
  patientId: string;
  canManage: boolean;
}) {
  const state = usePatientFiles(patientId);
  const refetch = state.kind === "ready" ? state.refetch : () => {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>Files &amp; X-rays</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {canManage && <UploadForm patientId={patientId} onUploaded={refetch} />}

        {state.kind === "loading" && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {state.kind === "error" && (
          <p className="text-sm text-destructive">Couldn’t load files: {state.message}</p>
        )}
        {state.kind === "ready" && state.data.total === 0 && (
          <p className="text-sm text-muted-foreground">No files uploaded yet.</p>
        )}
        {state.kind === "ready" && state.data.total > 0 && (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {state.data.items.map((f) => (
              <FileTile key={f.id} file={f} canManage={canManage} onChanged={refetch} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function UploadForm({ patientId, onUploaded }: { patientId: string; onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<FileKind>("xray");
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const file = inputRef.current?.files?.[0];
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setBusy(true);
    const result = await uploadPatientFile(patientId, file, {
      kind,
      caption: caption.trim() || undefined,
    });
    setBusy(false);
    if (result.status === "forbidden") {
      setError("Only a dentist or admin can upload files.");
      return;
    }
    if (result.status === "error") {
      setError(result.message);
      return;
    }
    setCaption("");
    if (inputRef.current) inputRef.current.value = "";
    onUploaded();
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-md border p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">File</label>
          <input
            ref={inputRef}
            type="file"
            accept="image/*,application/pdf"
            className="text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Kind</label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as FileKind)}
            className={`${controlClass} w-32`}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k === "xray" ? "X-ray" : k[0].toUpperCase() + k.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-1 flex-col gap-1">
          <label className="text-xs text-muted-foreground">Caption (optional)</label>
          <Input value={caption} onChange={(e) => setCaption(e.target.value)} />
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? "Uploading…" : "Upload"}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  );
}

function FileTile({
  file,
  canManage,
  onChanged,
}: {
  file: PatientFile;
  canManage: boolean;
  onChanged: () => void;
}) {
  const isImage = file.content_type.startsWith("image/");
  const previewUrl = useFilePreview(file.id, isImage);
  const [busy, setBusy] = useState(false);

  async function download() {
    const url = await fetchFileBlobUrl(file.id);
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = file.original_filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function archive() {
    setBusy(true);
    await archivePatientFile(file.id);
    setBusy(false);
    onChanged();
  }

  return (
    <li className="flex flex-col gap-1 rounded-md border p-2 text-sm">
      <div className="flex aspect-square items-center justify-center overflow-hidden rounded bg-muted">
        {isImage && previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt={file.caption || file.original_filename}
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="text-xs uppercase text-muted-foreground">
            {file.content_type.includes("pdf") ? "PDF" : isImage ? "…" : "FILE"}
          </span>
        )}
      </div>

      <span className="truncate font-medium" title={file.original_filename}>
        {file.caption || file.original_filename}
      </span>
      <span className="text-xs text-muted-foreground">
        {file.kind === "xray" ? "X-ray" : file.kind} · {formatFileSize(file.size_bytes)} ·{" "}
        {formatVisitDate(file.created_at)}
      </span>

      <div className="mt-1 flex flex-wrap gap-2">
        <button type="button" onClick={download} className="text-xs underline">
          Download
        </button>
        {canManage && (
          <button
            type="button"
            onClick={archive}
            disabled={busy}
            className="text-xs text-destructive underline"
          >
            {busy ? "…" : "Archive"}
          </button>
        )}
      </div>
    </li>
  );
}
