import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CheckCircle2, FileUp, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { Dialog } from "@/components/ui/overlay";
import { Button } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { UploadResult } from "@/lib/types";
import { cn, fmtBytes } from "@/lib/utils";

export function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<UploadResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setFiles([]);
    setResults(null);
    setError(null);
  }

  function add(list: FileList | null) {
    if (!list) return;
    const picked = Array.from(list).filter((f) => /\.(nessus|xml)$/i.test(f.name));
    setFiles((prev) => [
      ...prev,
      ...picked.filter((p) => !prev.some((f) => f.name === p.name && f.size === p.size)),
    ]);
    setResults(null);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    for (const f of files) form.append("files", f);
    try {
      const res = await api.upload<UploadResult[]>("/scans/upload", form);
      setResults(res);
      setFiles([]);
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) reset();
      }}
      title="Import Nessus scans"
      description="Export from Nessus as “Nessus (.nessus)” format. Large files are processed in the background."
      footer={
        results ? (
          <Button variant="primary" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={!files.length} loading={busy} onClick={submit}>
              Import {files.length > 1 ? `${files.length} files` : "file"}
            </Button>
          </>
        )
      }
    >
      {results ? (
        <ul className="space-y-2">
          {results.map((r) => (
            <li key={r.filename} className="flex items-start gap-2.5 text-sm">
              {r.scan_id ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0 text-critical" />
              )}
              <div className="min-w-0">
                <div className="truncate font-medium">{r.filename}</div>
                {r.scan_id ? (
                  <Link
                    to="/scans/$scanId"
                    params={{ scanId: String(r.scan_id) }}
                    onClick={() => onOpenChange(false)}
                    className="text-xs text-brand hover:underline"
                  >
                    Queued for import — view progress
                  </Link>
                ) : (
                  <div className="text-xs text-critical">
                    {r.error}
                    {r.duplicate_of && (
                      <>
                        {" "}
                        <Link
                          to="/scans/$scanId"
                          params={{ scanId: String(r.duplicate_of) }}
                          onClick={() => onOpenChange(false)}
                          className="text-brand hover:underline"
                        >
                          Open existing scan
                        </Link>
                      </>
                    )}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <button
            type="button"
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              add(e.dataTransfer.files);
            }}
            className={cn(
              "flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition",
              drag ? "border-brand bg-brand-soft" : "border-line hover:border-ink-3/50",
            )}
          >
            <FileUp className="mb-2 size-7 text-ink-3" />
            <span className="text-sm font-medium">Drop .nessus files here or click to browse</span>
            <span className="mt-1 text-xs text-ink-3">
              Several files at once are fine. Duplicates are detected automatically.
            </span>
          </button>
          <input
            ref={input}
            type="file"
            accept=".nessus,.xml"
            multiple
            hidden
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
          {files.length > 0 && (
            <ul className="mt-3 divide-y divide-line rounded-md border border-line">
              {files.map((f) => (
                <li
                  key={f.name + f.size}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                >
                  <span className="truncate">{f.name}</span>
                  <span className="flex shrink-0 items-center gap-3 text-xs text-ink-3">
                    {fmtBytes(f.size)}
                    <button
                      type="button"
                      className="hover:text-critical"
                      onClick={() => setFiles((prev) => prev.filter((p) => p !== f))}
                    >
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="mt-3 text-sm text-critical">{error}</p>}
        </>
      )}
    </Dialog>
  );
}
