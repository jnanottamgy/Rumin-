import { useEffect } from "react";

/** The browser tab's title while a page is shown: "<title> — RUMIN" (nothing while unknown). */
export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    if (title) document.title = `${title} — RUMIN`;
  }, [title]);
}
