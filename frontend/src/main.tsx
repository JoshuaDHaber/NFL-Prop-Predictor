import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { BetSlipProvider } from "./BetSlipContext";
import "./styles.css";

const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BetSlipProvider>
        <App />
      </BetSlipProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
