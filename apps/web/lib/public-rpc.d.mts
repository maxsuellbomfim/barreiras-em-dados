export type PublicRpcRequest = Readonly<{
  url: string;
  headers: Readonly<Record<string, string>>;
  body: string;
}>;

export type PublicRpcOptions = Readonly<{
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  revalidateSeconds?: number;
}>;

export function fetchPublicRpcRows(
  request: PublicRpcRequest,
  options?: PublicRpcOptions,
): Promise<unknown[] | null>;
