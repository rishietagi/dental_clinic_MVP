"use client";

// Patient files: X-rays, photos, documents (step 5.6).
//
// The content endpoint (/files/{id}/content) is auth-guarded, so its bytes can't
// be loaded with a plain <img src> (the browser wouldn't send the token). Instead
// `fetchFileBlobUrl` fetches the bytes WITH the auth header and returns an object
// URL the caller can use as an <img> src or a download href — and must revoke when
// done. Uploads use the browser's native FormData (no new dependency).

import { useCallback, useEffect, useState } from "react";

export type FileKind = "xray" | "photo" | "document";

export type PatientFile = {
  id: string;
  patient_id: string;
  visit_id: string | null;
  uploaded_by: string | null;
  kind: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  caption: string | null;
  archived: boolean;
  created_at: string;
};

type Result = { items: PatientFile[]; total: number };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Result }
  | { kind: "error"; message: string };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

// Request headers. Since 10.1 there is no authentication — the backend runs on
// this same machine and has no login — so this only sets the content type.
// Kept as a function (rather than inlined) so every call site stayed unchanged,
// and so re-adding a header later is a one-place edit.
function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export function usePatientFiles(patientId: string): State & { refetch: () => void } {
  const [state, setState] = useState<State>(
    apiUrl ? { kind: "loading" } : { kind: "error", message: "NEXT_PUBLIC_API_URL is not set." },
  );
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;

    (async () => {
      if (!cancelled) setState({ kind: "loading" });
      try {
        const headers = authHeaders();

        const res = await fetch(`${apiUrl}/patients/${patientId}/files`, { headers });
        if (!res.ok) throw new Error(`Request failed (${res.status}).`);

        const data = (await res.json()) as Result;
        if (!cancelled) setState({ kind: "ready", data });
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Could not load files.";
          setState({ kind: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [patientId, nonce]);

  return { ...state, refetch };
}

export type UploadResult =
  | { status: "ok"; file: PatientFile }
  | { status: "forbidden" }
  | { status: "error"; message: string };

export async function uploadPatientFile(
  patientId: string,
  file: File,
  meta: { kind: FileKind; caption?: string; visitId?: string },
): Promise<UploadResult> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();

    const form = new FormData();
    form.append("file", file);
    form.append("kind", meta.kind);
    if (meta.caption) form.append("caption", meta.caption);
    if (meta.visitId) form.append("visit_id", meta.visitId);

    // Don't set Content-Type — the browser sets the multipart boundary.
    const res = await fetch(`${apiUrl}/patients/${patientId}/files`, {
      method: "POST",
      headers,
      body: form,
    });

    if (res.ok) return { status: "ok", file: (await res.json()) as PatientFile };
    if (res.status === 403) return { status: "forbidden" };
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") return { status: "error", message: data.detail };
    } catch {
      // fall through
    }
    return { status: "error", message: `Upload failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not upload the file.",
    };
  }
}

export async function archivePatientFile(
  fileId: string,
): Promise<{ status: "ok" } | { status: "error"; message: string }> {
  if (!apiUrl) return { status: "error", message: "NEXT_PUBLIC_API_URL is not set." };
  try {
    const headers = authHeaders();

    const res = await fetch(`${apiUrl}/files/${fileId}/archive`, { method: "POST", headers });
    if (res.ok) return { status: "ok" };
    return { status: "error", message: `Request failed (${res.status}).` };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Could not archive the file.",
    };
  }
}

// Fetch a file's bytes WITH auth and return an object URL. Caller must
// URL.revokeObjectURL it when done (see useFilePreview). Returns null if not
// signed in or the fetch fails.
export async function fetchFileBlobUrl(fileId: string): Promise<string | null> {
  if (!apiUrl) return null;
  const headers = authHeaders();
  if (!headers) return null;
  const res = await fetch(`${apiUrl}/files/${fileId}/content`, { headers });
  if (!res.ok) return null;
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// Load an authorized object URL for a file, revoking it on unmount / change.
export function useFilePreview(fileId: string, enabled: boolean): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let revoked = false;
    let current: string | null = null;

    (async () => {
      const objectUrl = await fetchFileBlobUrl(fileId);
      if (revoked) {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        return;
      }
      current = objectUrl;
      setUrl(objectUrl);
    })();

    return () => {
      revoked = true;
      if (current) URL.revokeObjectURL(current);
    };
  }, [fileId, enabled]);

  return url;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
