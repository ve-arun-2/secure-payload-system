import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SecurePayloadPage } from './pages/SecurePayloadPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
    // gcTime 0: mutation variables (which may hold plaintext) are never kept in the cache.
    mutations: { retry: false, gcTime: 0 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SecurePayloadPage />
    </QueryClientProvider>
  );
}
