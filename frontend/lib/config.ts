/**
 * Base URL of the future FastAPI backend. Not used yet: auth and data are
 * mocked on the client. Set NEXT_PUBLIC_API_BASE_URL in .env.local when the
 * backend is wired up (see .env.example).
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
