const DEFAULT_REVALIDATE_SECONDS = 300;
const DEFAULT_TIMEOUT_MS = 10_000;

function isTransientStatus(status) {
  return status === 408 ||
    status === 425 ||
    status === 429 ||
    status >= 500;
}

function requestInit(request, attempt, timeoutMs, revalidateSeconds) {
  return {
    method: "POST",
    headers: request.headers,
    body: request.body,
    ...(attempt === 0
      ? { next: { revalidate: revalidateSeconds } }
      : { cache: "no-store" }),
    signal: AbortSignal.timeout(timeoutMs),
  };
}

export async function fetchPublicRpcRows(request, options = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const revalidateSeconds = options.revalidateSeconds ??
    DEFAULT_REVALIDATE_SECONDS;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    let response;
    try {
      response = await fetchImpl(
        request.url,
        requestInit(request, attempt, timeoutMs, revalidateSeconds),
      );
    } catch {
      if (attempt === 0) continue;
      return null;
    }

    if (!response.ok) {
      if (attempt === 0 && isTransientStatus(response.status)) continue;
      return null;
    }

    try {
      const payload = await response.json();
      return Array.isArray(payload) ? payload : null;
    } catch {
      return null;
    }
  }

  return null;
}
