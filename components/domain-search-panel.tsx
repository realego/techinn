"use client";

import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";

type AvailabilityResult = {
  domain_name: string;
  available: boolean | null;
  status: "available" | "taken" | "unknown";
  method: string;
  availability_note: string;
};

export function DomainSearchPanel({ compact = false }: { compact?: boolean }) {
  const [domain, setDomain] = useState("");
  const [result, setResult] = useState<AvailabilityResult | null>(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);

  async function searchDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setResult(null);
    setWorking(true);
    try {
      const query = new URLSearchParams({ domain });
      const response = await apiRequest<AvailabilityResult>(
        `/services/domains/search/?${query}`,
        {},
        { authenticated: false },
      );
      setResult(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Domain availability could not be checked.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <Card className={compact ? "" : "mx-auto max-w-3xl"}>
      <CardHeader>
        <CardTitle>{compact ? "Search for a domain" : "Domain search"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(event) => void searchDomain(event)}>
          <Input
            aria-label="Domain name"
            className="border-black bg-orange-50/70 focus-visible:border-black focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
            onChange={(event) => setDomain(event.target.value)}
            placeholder="yourbusiness.co.zw"
            required
            value={domain}
          />
          <Button disabled={working} loading={working} type="submit">
            {working ? "Checking…" : "Check domain"}
          </Button>
        </form>

        {result && (
          <div className="rounded-lg border p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">{result.domain_name}</p>
                <p className="text-muted-foreground text-xs">
                  {result.status === "available"
                    ? "Estimated available"
                    : result.method === "techinn"
                      ? "Taken now — already in TechInn"
                      : result.status === "taken"
                        ? "Taken now"
                        : "Could not confirm"}
                  {" · "}
                  {result.method.toUpperCase()}
                </p>
              </div>
            </div>
            <p className="text-muted-foreground mt-3 text-xs">{result.availability_note}</p>
          </div>
        )}

        {error && <div className="text-destructive text-sm" role="alert">{error}</div>}
      </CardContent>
    </Card>
  );
}
