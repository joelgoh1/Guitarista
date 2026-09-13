import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/** Test QueryClient: no retries, no background refetch noise. */
export function makeTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: Infinity } },
  });
}

export function withQueryClient(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}
