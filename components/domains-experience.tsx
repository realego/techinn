"use client";

import { ArrowRight, Check, Server, ShoppingCart, Sparkles, Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { DomainSearchForm } from "@/components/domain-search-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { domainExtensionChoices } from "@/config/shop-products";
import { apiRequest } from "@/lib/api";
import { addToCart, removeFromCart, useCart } from "@/lib/cart-store";

type DomainCheck = {
  domain_name: string;
  available: boolean | null;
  status: "available" | "taken" | "unknown";
  method: string;
  availability_note: string;
};

const extensions = [
  { suffix: ".co.zw", description: "A local home for Zimbabwean brands" },
  { suffix: ".com", description: "The familiar choice for a global audience" },
  { suffix: ".net", description: "A classic fit for digital services" },
  { suffix: ".online", description: "A clear digital identity" },
];

const subscribeToLocation = () => () => {};

function parseSearch(value: string) {
  const normalized = value.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  const extension = extensions.find((option) => normalized.endsWith(option.suffix));
  const name = extension ? normalized.slice(0, -extension.suffix.length) : normalized;
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(name)) return null;
  return { name, domains: extension ? [`${name}${extension.suffix}`] : extensions.map((option) => `${name}${option.suffix}`) };
}

function resultLabel(result: DomainCheck) {
  if (result.status === "available") return "Available";
  if (result.status === "taken") return "Unavailable";
  return "Availability could not be confirmed";
}

function getDomainPrice(domain: string) {
  const extension = domainExtensionChoices.find((option) =>
    domain.endsWith(`.${option.id.replace("-", ".")}`),
  );
  return extension?.price;
}

export function DomainsExperience() {
  const { lines, count, subtotal } = useCart();
  const cartDomains = new Set(lines.filter((line) => line.productId === "domains").map((line) => line.domainName));
  const locationSearch = useSyncExternalStore(
    subscribeToLocation,
    () => window.location.search,
    () => "",
  );
  const query = new URLSearchParams(locationSearch).get("q") ?? "";
  const [manualSearch, setManualSearch] = useState("");
  const searchedInput = manualSearch || query;
  const parsedSearch = parseSearch(searchedInput);
  const [results, setResults] = useState<DomainCheck[]>([]);
  const [searchError, setSearchError] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [cartNotice, setCartNotice] = useState("");
  const [searchVersion, setSearchVersion] = useState(0);
  const resultsSectionRef = useRef<HTMLElement>(null);
  const searchDomainNames = parsedSearch?.domains.join(",") ?? "";

  useEffect(() => {
    if (!searchDomainNames) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsSearching(true);
      setSearchError("");
      void Promise.all(
        searchDomainNames.split(",").map((domain) => {
          const search = new URLSearchParams({ domain });
          return apiRequest<DomainCheck>(
            `/services/domains/search/?${search}`,
            {},
            { authenticated: false },
          );
        }),
      ).then((checks) => {
        if (active) {
          setResults(checks);
          window.requestAnimationFrame(() => {
            if (!active) return;
            resultsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
            resultsSectionRef.current?.focus({ preventScroll: true });
          });
        }
      }).catch((error: unknown) => {
        if (active) {
          setResults([]);
          setSearchError(error instanceof Error ? error.message : "Domain availability could not be checked.");
        }
      }).finally(() => {
        if (active) setIsSearching(false);
      });
    });
    return () => {
      active = false;
    };
  }, [searchDomainNames, searchVersion]);

  function buyDomain(domain: string) {
    if (cartDomains.has(domain)) return;
    const extension = domainExtensionChoices.find((option) => domain.endsWith("." + option.id.replace("-", ".")));
    const extensionId = domain.endsWith(".co.zw")
      ? "co-zw"
      : domain.slice(domain.lastIndexOf(".") + 1);
    addToCart("domains", { extension: extension?.id ?? extensionId }, domain);
    setCartNotice(`${domain} added to your cart.`);
  }

  function searchAgain(name: string) {
    setResults([]);
    setManualSearch(name);
    setSearchVersion((version) => version + 1);
  }

  return (
    <>
      <section className="relative overflow-hidden px-4 pt-6 pb-16 sm:pt-8 sm:pb-24">
        <div className="pointer-events-none absolute top-0 left-1/2 h-72 w-150 -translate-x-1/2 rounded-full bg-orange-500/10 blur-3xl" />
        <div className="max-w-container relative mx-auto flex max-w-4xl flex-col items-center text-center">
          <h1 className="max-w-3xl text-4xl leading-tight font-semibold tracking-tight text-balance sm:text-6xl">
            Find a name that <span className="text-orange-600 dark:text-orange-400">feels like yours.</span>
          </h1>
          <p className="text-muted-foreground mt-5 max-w-2xl text-base leading-7 text-balance sm:text-lg">
            Search a domain and check its current availability across popular extensions.
          </p>
          <DomainSearchForm
            key={searchedInput}
            initialValue={searchedInput}
            className="mt-10 w-full max-w-2xl"
            onSearch={searchAgain}
          />
          <p className="text-muted-foreground mt-4 text-xs">
            Estimates only · Registration is manually confirmed and first come, first served.
          </p>
        </div>
      </section>

      <section className="px-4 pb-16 sm:pb-24">
        <div className="max-w-container mx-auto">
          <div className="mb-6">
            <p className="mb-2 text-sm font-medium text-orange-700 dark:text-orange-300">Choose your extension</p>
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Popular domains</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {extensions.map((extension) => (
              <Card key={extension.suffix} className="bg-card/60 gap-4 transition-colors hover:border-orange-500/50">
                <CardHeader>
                  <CardTitle className="text-2xl">{extension.suffix}</CardTitle>
                  <CardDescription>{extension.description}</CardDescription>
                </CardHeader>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section
        id="domain-results"
        ref={resultsSectionRef}
        tabIndex={-1}
        aria-label="Domain search results"
        className="scroll-mt-28 px-4 pb-24 outline-none"
      >
        <div className="max-w-container mx-auto grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
          <Card className="min-w-0 gap-0 overflow-hidden">
            <CardHeader className="border-b pb-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="mb-2 flex items-center gap-2">
                    <Sparkles className="size-4 text-orange-600 dark:text-orange-400" />
                    <span className="text-sm font-medium text-orange-700 dark:text-orange-300">Live availability checks</span>
                  </div>
                  <CardTitle className="text-xl">
                    {parsedSearch ? `Results for “${parsedSearch.name}”` : "Search for a domain"}
                  </CardTitle>
                  <CardDescription className="mt-2">
                    {parsedSearch ? "Current domain availability results." : "Enter a name above to check current availability."}
                  </CardDescription>
                </div>
                {parsedSearch && <Badge variant="outline">{isSearching ? "Checking…" : `${results.length} checked`}</Badge>}
              </div>
            </CardHeader>
            <CardContent className="px-3 py-2 sm:px-6">
              {searchError ? (
                <p className="py-8 text-center text-sm text-destructive" role="alert">{searchError}</p>
              ) : results.length ? (
                <>
                  <Table className="table-fixed">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Domain</TableHead>
                        <TableHead className="hidden sm:table-cell">Check result</TableHead>
                        <TableHead className="w-28 text-right">Cart</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {results.map((result) => {
                        const isSelected = cartDomains.has(result.domain_name);
                        const domainPrice = getDomainPrice(result.domain_name);
                        return (
                          <TableRow key={result.domain_name}>
                            <TableCell className="py-4 whitespace-normal">
                              <div className="flex min-w-0 flex-wrap items-center gap-2 font-medium">
                                <span className="min-w-0 break-all">{result.domain_name}</span>
                                {result.available !== null && (
                                  <Image
                                    alt={result.available ? "Available" : "Unavailable"}
                                    className="h-6 w-auto object-contain"
                                    height={25}
                                    src={result.available ? "/domain-status/available.png" : "/domain-status/unavailable.png"}
                                    unoptimized
                                    width={72}
                                  />
                                )}
                              </div>
                              {domainPrice !== undefined && (
                                <p className="text-muted-foreground mt-2 text-xs">
                                  Registration: <span className="font-medium text-orange-600 dark:text-orange-400">${domainPrice}/yr</span> · Renewal: <span className="font-medium text-orange-600 dark:text-orange-400">${domainPrice}/yr</span>
                                </p>
                              )}
                              <span className="text-muted-foreground mt-1 block text-xs sm:hidden">{resultLabel(result)}</span>
                            </TableCell>
                            <TableCell className="text-muted-foreground hidden sm:table-cell">{resultLabel(result)}</TableCell>
                            <TableCell className="text-right">
                              {result.available === true && domainPrice !== undefined ? (
                                <Button
                                  variant={isSelected ? "secondary" : "default"}
                                  size="sm"
                                  disabled={isSelected || isSearching}
                                  aria-label={isSelected ? `${result.domain_name} is in your cart` : `Add ${result.domain_name} to cart`}
                                  onClick={() => buyDomain(result.domain_name)}
                                >
                                  {isSelected ? <><Check className="size-4" /><span>In cart</span></> : "Add to cart"}
                                </Button>
                              ) : <span className="text-muted-foreground text-xs">{result.available === false ? "Unavailable" : result.available === true ? "Price pending" : "Unconfirmed"}</span>}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  <p className="text-muted-foreground px-2 pt-4 pb-2 text-xs">
                    Availability can change before registration. Names are not held; if a selected name is taken, TechInn will let you know.
                  </p>
                </>
              ) : isSearching ? (
                <div aria-label="Checking domain availability" aria-live="polite" className="divide-y" role="status">
                  {Array.from({ length: parsedSearch?.domains.length ?? 3 }, (_, index) => (
                    <div className="flex items-center justify-between gap-4 py-4" key={index}>
                      <div className="min-w-0 flex-1 space-y-2">
                        <Skeleton className="h-5 w-48 max-w-full" />
                        <Skeleton className="h-4 w-36" />
                      </div>
                      <Skeleton className="h-8 w-24 shrink-0" />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground py-10 text-center text-sm">Your live search results will appear here.</p>
              )}
            </CardContent>
          </Card>

          <Card className="lg:sticky lg:top-24" aria-label="Cart summary">
            <CardHeader>
              <div className="flex items-center gap-2">
                <ShoppingCart className="size-5 text-orange-600 dark:text-orange-400" />
                <CardTitle>Your cart</CardTitle>
                <Badge variant="secondary" className="ml-auto">{count}</Badge>
              </div>
              <CardDescription>Your domains and services, ready when you are.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="sr-only" role="status" aria-live="polite">{cartNotice}</p>
              {lines.length === 0 ? (
                <div className="border-border text-muted-foreground rounded-lg border border-dashed px-4 py-8 text-center text-sm">
                  Add an available domain to get started.
                </div>
              ) : (
                <div className="max-h-72 space-y-3 overflow-y-auto">
                  {lines.map((line) => (
                    <div className="flex items-start justify-between gap-3 text-sm" key={line.id}>
                      <div className="min-w-0">
                        <p className="break-all font-medium">{line.domainName || line.product.name}</p>
                        <p className="text-muted-foreground mt-1 text-xs">${(line.unitPrice * line.quantity).toFixed(2)} {line.cadence}{line.quantity > 1 ? ` · ${line.quantity} items` : ""}</p>
                      </div>
                      <Button size="icon" className="size-7 shrink-0" variant="ghost" aria-label={`Remove ${line.domainName || line.product.name} from cart`} onClick={() => removeFromCart(line.id)}><Trash2 className="size-3.5" /></Button>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-4 flex items-center justify-between border-t pt-4 text-sm">
                <span>Subtotal <span className="text-muted-foreground text-xs">USD</span></span>
                <strong className="text-lg tabular-nums">${subtotal.toFixed(2)}</strong>
              </div>
              <p className="text-muted-foreground mt-4 text-xs">
                Domains renew yearly. Adding to cart does not reserve or register a name.
              </p>
              <div className="mt-5 space-y-2">
                <Button asChild variant="outline" className="w-full"><Link href="/shop/?service=web"><Server className="size-4" />Add hosting</Link></Button>
                {count > 0 ? <Button asChild className="w-full"><Link href="/checkout/">Checkout <ArrowRight className="size-4" /></Link></Button> : <Button disabled className="w-full">Checkout <ArrowRight className="size-4" /></Button>}
                <Button asChild variant="ghost" className="w-full"><Link href="/shop/">Continue shopping</Link></Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </>
  );
}
