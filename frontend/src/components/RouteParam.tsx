/**
 * Client-side route parameter extraction.
 *
 * Reads the ID from the URL query string (e.g. /pipeline/?id=abc123 → "abc123").
 * Query params work on S3 static hosting where path-based routing would 404.
 */

import { useEffect, useState } from "react";

/**
 * Extract the "id" query parameter from the current URL.
 * Falls back to path segment extraction for backward compatibility.
 */
export function useRouteId(position: number = 1): string | null {
  const [id, setId] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryId = params.get("id");
    if (queryId) {
      setId(queryId);
      return;
    }
    const segments = window.location.pathname.split("/").filter(Boolean);
    setId(segments[position] || null);
  }, [position]);

  return id;
}
