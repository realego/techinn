"use client";

import { ArrowRight, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface DomainSearchFormProps {
  onSearch?: (name: string) => void;
  className?: string;
  initialValue?: string;
}

export function DomainSearchForm({ onSearch, className, initialValue = "" }: DomainSearchFormProps) {
  const router = useRouter();
  const [query, setQuery] = useState(initialValue);
  const [placeholder, setPlaceholder] = useState("yourbrand.co.zw");
  const [searchFocused, setSearchFocused] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (searchFocused || query) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const examples = ["yourbrand.co.zw", "brightweb.com", "techinn.co.zw", "mybusiness.com"];
    let phraseIndex = 0;
    let length = examples[phraseIndex].length;
    let deleting = true;
    let timer: number;

    function typeNext() {
      let delay = deleting ? 55 : 95;
      if (deleting) {
        length -= 1;
        setPlaceholder(examples[phraseIndex].slice(0, length));
        if (length <= 0) {
          deleting = false;
          phraseIndex = Math.floor(Math.random() * examples.length);
          delay = 350;
        }
      } else {
        length += 1;
        setPlaceholder(examples[phraseIndex].slice(0, length));
        if (length >= examples[phraseIndex].length) {
          deleting = true;
          delay = 1500;
        }
      }
      timer = window.setTimeout(typeNext, delay);
    }

    timer = window.setTimeout(typeNext, 1300);
    return () => window.clearTimeout(timer);
  }, [query, searchFocused]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const candidate = query.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
    const label = candidate.replace(/\.(co\.zw|com|net|online)$/i, "");
    if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label)
      || (candidate !== label && !/\.(co\.zw|com|net|online)$/i.test(candidate))) {
      setError("Enter a name using letters, numbers, or hyphens.");
      return;
    }
    setError("");
    if (onSearch) {
      setIsSubmitting(true);
      onSearch(candidate);
      document.getElementById("domain-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      setIsSubmitting(true);
      router.push("/domains/?q=" + encodeURIComponent(candidate));
    }
  }

  return (
    <div className={className}>
      <form onSubmit={handleSearch} className="flex w-full flex-col gap-3 sm:flex-row">
        <div className="domain-search-frame relative min-w-0 flex-1 rounded-xl p-px">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2" />
          <Input
            aria-label="Search domain name"
            aria-invalid={Boolean(error)}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setIsSubmitting(false);
            }}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder={!query && !searchFocused ? placeholder : ""}
            className="bg-card h-13 rounded-[11px] border-transparent pl-12 text-base shadow-sm"
          />
        </div>
        <Button type="submit" size="lg" className="h-13 rounded-xl px-7" disabled={isSubmitting} loading={isSubmitting}>
          Search domains <ArrowRight className="ml-2 size-4" />
        </Button>
      </form>
      {error ? <p role="alert" className="text-destructive mt-3 text-sm">{error}</p> : null}
    </div>
  );
}
