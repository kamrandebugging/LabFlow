import { QueryClient } from "@tanstack/react-query";

/**
 * One application-wide query client.
 *
 * Platform data is operator-facing and changes on human action, so it is
 * refetched on mutation (explicit invalidation) rather than on a timer.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
