// Extract a user-facing message from an unknown error. Handles the axios
// shape (err.response.data.detail) used by the FastAPI backend, plain
// Error instances, and arbitrary thrown values.
export function getApiErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null) {
    const detail = (err as { response?: { data?: { detail?: unknown } } })
      ?.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (err instanceof Error && err.message) return err.message;
  }
  return fallback;
}
