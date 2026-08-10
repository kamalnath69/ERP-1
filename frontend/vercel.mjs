const rawApiOrigin = process.env.EDVATIQ_API_ORIGIN?.trim();

if (!rawApiOrigin) {
  throw new Error(
    "EDVATIQ_API_ORIGIN is required. Set it to the external backend origin without /api.",
  );
}

const parsedApiOrigin = new URL(rawApiOrigin);
if (parsedApiOrigin.protocol !== "https:" && process.env.VERCEL) {
  throw new Error("EDVATIQ_API_ORIGIN must use HTTPS on Vercel.");
}
if (parsedApiOrigin.pathname !== "/" || parsedApiOrigin.search || parsedApiOrigin.hash) {
  throw new Error("EDVATIQ_API_ORIGIN must be an origin only, for example https://api.example.com.");
}

const apiOrigin = parsedApiOrigin.origin;

export const config = {
  framework: "vite",
  buildCommand: "yarn build",
  outputDirectory: "build",
  rewrites: [
    {
      source: "/api/:path*",
      destination: `${apiOrigin}/api/:path*`,
    },
    {
      source: "/(.*)",
      destination: "/index.html",
    },
  ],
  headers: [
    {
      source: "/assets/(.*)",
      headers: [
        {
          key: "Cache-Control",
          value: "public, max-age=31536000, immutable",
        },
      ],
    },
    {
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        {
          key: "Permissions-Policy",
          value: "camera=(self), microphone=(self), geolocation=()",
        },
      ],
    },
  ],
};
