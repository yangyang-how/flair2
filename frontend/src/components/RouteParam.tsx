/**
 * Client-side route parameter extraction.
 *
 * Reads the ID from the URL path (e.g. /pipeline/abc123 → "abc123").
 * Used instead of Astro.params for static (S3) hosting where there's
 * no server to parse dynamic route segments.
 */

import { useEffect, useState } from "react";

/**
 * Extract a path segment by position from the current URL.
 * position=1 means the second segment: /pipeline/[this-one]
 */
export function useRouteId(position: number = 1): string | null {
  const [id, setId] = useState<string | null>(null);

  useEffect(() => {
    const segments = window.location.pathname.split("/").filter(Boolean);
    setId(segments[position] || null);
  }, [position]);

  return id;
}
