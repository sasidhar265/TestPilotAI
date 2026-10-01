// Only backend API requests leave the bundled origin. Assets always remain local.
export function apiTarget(input, localOrigin, backend) {
  const base = new URL(localOrigin);
  const url = new URL(input instanceof Request ? input.url : input, base);
  if (url.protocol !== base.protocol || url.host !== base.host) return null;
  if (!url.pathname.startsWith("/api/") && url.pathname !== "/openapi.json") return null;
  return `${backend}${url.pathname}${url.search}`;
}

export function exportName(value) {
  return (
    (value || "export")
      .split(/[\\/]/)
      .pop()
      .replace(/[^a-zA-Z0-9._ -]/g, "_")
      .slice(0, 120) || "export"
  );
}
