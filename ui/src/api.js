// window.__API_BASE_URL__ is injected at container startup (see
// ui/docker-entrypoint.sh) so a single built image works across hosts;
// import.meta.env.VITE_API_BASE_URL is the build-time fallback for local dev.
export const API = window.__API_BASE_URL__ || import.meta.env.VITE_API_BASE_URL || "http://localhost:8765";
