/**
 * The browser tab title for a page: "Headline · Wollongong News".
 *
 * Each page names itself; a page still loading its data passes nothing yet and
 * shows the site name until it knows what it is.
 */
import { useEffect } from "react";

export const SITE_NAME = "Wollongong News";

export function usePageTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · ${SITE_NAME}` : SITE_NAME;
  }, [title]);
}
