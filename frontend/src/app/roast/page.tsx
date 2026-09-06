"use client";

import { useCallback, useRef, useState } from "react";
import { ArrowRight, FileText, LogIn, RefreshCcw, UploadCloud, X } from "lucide-react";
import { ArrowAccentLeft, ArrowDarkDown } from "@/components/landing/accents";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";

const HEADLINE_SHADOW = stackedShadow(10, "#001A99");

const ACCEPTED_EXTENSIONS = /\.(pdf|docx?)$/i;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function RoastPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [mode, setMode] = useState<"anonymous" | "signin">("anonymous");
  const inputRef = useRef<HTMLInputElement>(null);

  const acceptFile = useCallback((candidate: File | null | undefined) => {
    if (!candidate) return;
    const okType = candidate.type === "application/pdf" || ACCEPTED_EXTENSIONS.test(candidate.name);
    if (!okType) return;
    setFile(candidate);
  }, []);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    acceptFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center px-4 pb-16 md:px-10">
        <div className="mb-10 mt-4 flex w-full flex-col items-center text-center md:mb-14">
          <h1
            className="m-0 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-white"
            style={{ textShadow: HEADLINE_SHADOW }}
          >
            Drop your resume
          </h1>
          <h1
            className="m-0 mt-1 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-brand-lime md:mt-2"
            style={{ textShadow: HEADLINE_SHADOW }}
          >
            get roasted
          </h1>
        </div>

        <div className="relative w-full max-w-2xl">
          <div className="pointer-events-none absolute -left-24 top-6 hidden h-24 w-24 md:block">
            <ArrowAccentLeft />
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => !file && inputRef.current?.click()}
            className={[
              "relative flex w-full flex-col items-center justify-center rounded-[2rem] border-[3px] border-dashed px-8 py-14 text-center transition-colors duration-200 md:py-16",
              file ? "cursor-default border-black/10 bg-white" : "cursor-pointer",
              !file && dragActive ? "border-black bg-brand-lime" : "",
              !file && !dragActive ? "border-black/20 bg-white/95 hover:border-black/40" : "",
            ].join(" ")}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.doc,.docx"
              className="hidden"
              onChange={(e) => acceptFile(e.target.files?.[0])}
            />

            {!file ? (
              <>
                <div
                  className={[
                    "mb-5 flex h-16 w-16 items-center justify-center rounded-full transition-colors duration-200 md:h-20 md:w-20",
                    dragActive ? "bg-black" : "bg-brand-blue",
                  ].join(" ")}
                >
                  <UploadCloud className={dragActive ? "text-brand-lime" : "text-white"} size={32} strokeWidth={2} />
                </div>
                <p className="font-display text-lg uppercase text-black md:text-2xl">
                  {dragActive ? "Drop it like it's hot" : "Drag & drop your resume"}
                </p>
                <p className="mt-2 font-mono text-xs font-semibold text-black/50 md:text-sm">
                  or click to browse · PDF, DOC, DOCX up to 10MB
                </p>
              </>
            ) : (
              <div className="flex w-full flex-col items-center">
                <div className="flex w-full max-w-sm items-center gap-3 rounded-2xl bg-brand-blue p-3 pr-4 text-white shadow-lg">
                  <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-white/15">
                    <FileText size={20} className="text-brand-lime" />
                  </div>
                  <div className="min-w-0 flex-1 text-left">
                    <p className="truncate font-mono text-xs font-bold md:text-sm">{file.name}</p>
                    <p className="mt-0.5 font-mono text-[10px] text-white/70 md:text-xs">{formatFileSize(file.size)}</p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      inputRef.current?.click();
                    }}
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-white/15 transition-colors hover:bg-white/25"
                    aria-label="Replace file"
                  >
                    <RefreshCcw size={14} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                    }}
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-lime transition-colors hover:brightness-95"
                    aria-label="Remove file"
                  >
                    <X size={14} className="text-black" />
                  </button>
                </div>
                <p className="mt-4 font-mono text-[10px] font-semibold uppercase tracking-wide text-black/40 md:text-xs">
                  Ready to roast
                </p>
              </div>
            )}
          </div>

          <div className="mx-auto -mb-2 mt-1 flex h-16 w-16 justify-center md:hidden">
            <ArrowDarkDown />
          </div>

          <div className="mt-8 flex flex-col items-center gap-4 md:mt-10">
            <button
              disabled={!file}
              className={[
                "flex items-center gap-2 rounded-full px-8 py-4 font-display text-sm uppercase tracking-wide transition-all md:text-base",
                file
                  ? "bg-brand-lime text-black shadow-[4px_4px_0_#000] hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]"
                  : "cursor-not-allowed bg-white/20 text-white/50",
              ].join(" ")}
            >
              Roast me
              <ArrowRight size={18} strokeWidth={2.5} />
            </button>

            <div className="flex items-center gap-1 rounded-full border border-white/25 bg-white/10 p-1">
              <button
                onClick={() => setMode("anonymous")}
                className={[
                  "rounded-full px-4 py-1.5 text-xs font-bold transition-colors",
                  mode === "anonymous" ? "bg-white text-brand-blue" : "text-white/70 hover:text-white",
                ].join(" ")}
              >
                Continue anonymously
              </button>
              <button
                onClick={() => setMode("signin")}
                className={[
                  "flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-bold transition-colors",
                  mode === "signin" ? "bg-white text-brand-blue" : "text-white/70 hover:text-white",
                ].join(" ")}
              >
                <LogIn size={12} />
                Sign in for extra features
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
