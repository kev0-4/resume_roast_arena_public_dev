"use client";

// The editor for CODE and SQL rounds.
//
// Everything here is loaded on demand. CodeMirror plus five language packs
// is several hundred KB, and the overwhelming majority of sessions -- every
// HR, IB and conversation-only interview -- never open an editor at all.
// The page that imports this must do so through next/dynamic, and the
// language grammar itself is fetched only for the language actually
// selected rather than all five up front.

import { useCallback, useEffect, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import type { Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";

export const LANGUAGE_LABELS: Record<string, string> = {
  python: "Python",
  javascript: "JavaScript",
  java: "Java",
  cpp: "C/C++",
  sql: "SQL",
};

/** Grammar for one language, fetched only when that language is chosen. */
async function loadLanguage(language: string): Promise<Extension | null> {
  switch (language) {
    case "python":
      return (await import("@codemirror/lang-python")).python();
    case "javascript":
      return (await import("@codemirror/lang-javascript")).javascript();
    case "java":
      return (await import("@codemirror/lang-java")).java();
    case "cpp":
      return (await import("@codemirror/lang-cpp")).cpp();
    case "sql":
      return (await import("@codemirror/lang-sql")).sql();
    default:
      return null;
  }
}

export function CodeEditor({
  value,
  language,
  onChange,
  onPaste,
  disabled,
}: {
  value: string;
  language: string;
  onChange: (next: string) => void;
  /** Fired once per paste. Recorded as a signal, never blocked. */
  onPaste: () => void;
  disabled?: boolean;
}) {
  const [grammar, setGrammar] = useState<Extension | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ext = await loadLanguage(language);
      if (!cancelled) setGrammar(ext);
    })();
    return () => {
      cancelled = true;
    };
  }, [language]);

  const handlePaste = useCallback(() => onPaste(), [onPaste]);

  const extensions = useMemo(() => {
    const base: Extension[] = [
      EditorView.lineWrapping,
      EditorView.domEventHandlers({ paste: () => { handlePaste(); return false; } }),
      EditorView.theme({
        "&": { fontSize: "13px", height: "100%", background: "transparent" },
        ".cm-scroller": { fontFamily: "var(--font-mono, ui-monospace, monospace)", lineHeight: "1.6" },
        ".cm-gutters": { background: "transparent", border: "none", opacity: "0.5" },
        "&.cm-focused": { outline: "none" },
        ".cm-activeLine": { background: "rgba(200,240,46,0.06)" },
        ".cm-activeLineGutter": { background: "transparent" },
      }),
    ];
    if (grammar) base.push(grammar);
    return base;
  }, [grammar, handlePaste]);

  return (
    <CodeMirror
      value={value}
      height="100%"
      theme={oneDark}
      extensions={extensions}
      editable={!disabled}
      onChange={onChange}
      basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true, autocompletion: false }}
      style={{ height: "100%", overflow: "hidden" }}
    />
  );
}
