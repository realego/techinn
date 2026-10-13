"use client";

import {
  AppWindow,   ArrowDownWideNarrow, ArrowRight, Check, ChevronDown, ChevronRight, Globe2, HardDrive, Info,
  LayoutGrid, Mail, Monitor, PanelLeft, Plus, Search, Server, ShoppingBag, ShoppingCart, SlidersHorizontal, X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type CSSProperties,useEffect, useMemo, useRef, useState } from "react";

import { PromotionTag } from "@/components/promotion-tag";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, useSidebar,
} from "@/components/ui/sidebar";
import { billingPrice, configureProduct, domainExtensionChoices, type ShopCategory, type ShopProduct, shopProducts, type ShopSelections } from "@/config/shop-products";
import { addToCart, useCart } from "@/lib/cart-store";
import { cn } from "@/lib/utils";

const categories = [
  { name: "All" as const, label: "All services", icon: LayoutGrid },
  { name: "Web Hosting" as const, label: "Web hosting", icon: Server },
  { name: "Email Hosting" as const, label: "Email hosting", icon: Mail },
  { name: "Domains" as const, label: "Domains", icon: Globe2 },
  { name: "Website Design" as const, label: "Website design", icon: Monitor },
  { name: "App Development" as const, label: "App development", icon: AppWindow },
];

const categoryServices: Record<ShopCategory, string> = {
  All: "", "Web Hosting": "web", "Email Hosting": "email", Domains: "domains",
  "Website Design": "website", "App Development": "app",
};

// Adapted from shadcn sidebar-07: keep the icon rail within the shop below the site header.
function ShopSidebar({ category, onCategoryChange, cartCount }: {
  category: ShopCategory;
  onCategoryChange: (value: ShopCategory) => void;
  cartCount: number;
}) {
  const { open, isMobile, openMobile, setOpenMobile, toggleSidebar } = useSidebar();
  const expanded = open && !isMobile;

  function categoryMenu(showLabels: boolean) {
    return (
      <SidebarMenu className="gap-2">
        {categories.map(({ name, label, icon: Icon }) => (
          <SidebarMenuItem key={name}>
            <SidebarMenuButton
              isActive={category === name}
              aria-label={label}
              aria-pressed={category === name}
              tooltip={{ children: label, hidden: showLabels || isMobile }}
              onClick={() => { onCategoryChange(name); setOpenMobile(false); }}
              className={cn("h-10 transition-colors data-[active=true]:bg-brand/10 data-[active=true]:text-brand", showLabels ? "px-3" : "w-10 justify-center p-0")}
            >
              <Icon />
              {showLabels && <><span className="flex-1">{label}</span><span className="text-muted-foreground text-xs tabular-nums">{name === "All" ? shopProducts.length : shopProducts.filter((product) => product.category === name).length}</span></>}
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    );
  }

  return (
    <>
      <Sidebar collapsible="none" className={cn("sticky top-24 h-[calc(100svh-7rem)] min-h-96 shrink-0 self-start bg-transparent transition-[width] duration-200 motion-reduce:transition-none", expanded ? "w-52" : "w-14 sm:w-16")}>
        <SidebarHeader className="border-b px-2 py-3 sm:px-3">
          <Button variant="ghost" size="icon" className="size-10 justify-start px-3" onClick={toggleSidebar} aria-label={expanded ? "Collapse shop categories" : "Expand shop categories"} aria-expanded={isMobile ? openMobile : open}>
            <PanelLeft />
          </Button>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup className="px-2 py-4 sm:px-3">
            {expanded && <p className="text-muted-foreground mb-3 px-3 text-[10px] font-medium uppercase tracking-widest">Browse services</p>}
            <SidebarGroupContent><nav aria-label="Shop categories">{categoryMenu(expanded)}</nav></SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="border-t p-2 sm:p-3">
          <SidebarMenu><SidebarMenuItem>
            <SidebarMenuButton asChild tooltip={{ children: cartCount ? `Checkout, ${cartCount} ${cartCount === 1 ? "item" : "items"}` : "Checkout", hidden: expanded || isMobile }} className={cn("h-10", !expanded && "w-10 justify-center p-0")}>
              <Link href="/checkout/" aria-label={cartCount ? `Checkout, ${cartCount} ${cartCount === 1 ? "item" : "items"}` : "Checkout"}>
                <span className="relative inline-flex">
                  <ShoppingCart />
                  {cartCount > 0 && <span aria-hidden="true" className="bg-primary text-primary-foreground absolute -top-2 -right-2 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-semibold tabular-nums">{cartCount > 99 ? "99+" : cartCount}</span>}
                </span>
                {expanded && <><span className="flex-1">Checkout</span>{cartCount > 0 && <span className="text-muted-foreground text-xs tabular-nums">{cartCount}</span>}</>}
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem></SidebarMenu>
        </SidebarFooter>
      </Sidebar>
      <Sheet open={isMobile && openMobile} onOpenChange={setOpenMobile}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="border-b p-5"><SheetTitle>Shop categories</SheetTitle><SheetDescription>Choose what your business needs.</SheetDescription></SheetHeader>
          <nav aria-label="Mobile shop categories" className="p-3">{categoryMenu(true)}</nav>
        </SheetContent>
      </Sheet>
    </>
  );
}

function simpleExplanation(product: ShopProduct) {
  switch (product.category) {
    case "Website Design":
      return `A professionally built website for your business. For example, a small shop could have Home, Products, About, and Contact pages that work well on phones.`;
    case "Web Hosting":
      return `The online space where your website lives. For example, your customers can visit your business website any time, while you manage its content and files.`;
    case "Email Hosting":
      return `Business email using your own domain instead of a free email address. For example, you could use hello@yourbusiness.co.zw for customer questions and accounts@yourbusiness.co.zw for invoices.`;
    case "Domains":
      return `Your business’s address on the internet. For example, customers can type yourbusiness.co.zw to find your website and recognize your email address.`;
    case "App Development":
      return `A mobile app designed for your business. For example, customers could browse your services, book an appointment, or check updates from their phone.`;
  }
}

function ProductRow({ product, selections, onSelectionsChange, quantities }: {
  product: ShopProduct;
  selections: ShopSelections;
  onSelectionsChange: (value: ShopSelections) => void;
  quantities: Map<string, number>;
}) {
  const [added, setAdded] = useState(false);
  const [learnMoreOpen, setLearnMoreOpen] = useState(false);
  const [domainChoice, setDomainChoice] = useState<"existing" | "add" | "">("");
  const [domainExtension, setDomainExtension] = useState(domainExtensionChoices[0].id);
  const [domainChoiceError, setDomainChoiceError] = useState(false);
  const [requiredDomainQuery, setRequiredDomainQuery] = useState("");
  const [requiredDomainTld, setRequiredDomainTld] = useState(domainExtensionChoices[0].id);
  const [requiredDomainResult, setRequiredDomainResult] = useState<{ name: string; extension: string } | null>(null);
  const [requiredDomainError, setRequiredDomainError] = useState("");
  const [domainQuery, setDomainQuery] = useState("");
  const [domainResult, setDomainResult] = useState<{ name: string; extension: string } | null>(null);
  const [domainSearchError, setDomainSearchError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const domainChoiceRef = useRef<HTMLFieldSetElement>(null);
  const requiredDomainSearchRef = useRef<HTMLInputElement>(null);
  const requiredDomainSearchContainerRef = useRef<HTMLDivElement>(null);
  const domainSearchRef = useRef<HTMLInputElement>(null);
  const domainSearchContainerRef = useRef<HTMLDivElement>(null);
  const configured = configureProduct(product, selections);
  const domainPrices = product.options.find((option) => option.id === "extension")?.choices.map((choice) => choice.price) ?? [];
  const fromPrice = product.id === "domains" && domainPrices.length > 0
    ? Math.min(...domainPrices)
    : product.supportsYearly && configured.yearly
      ? billingPrice(product.price, true)
      : product.price;
  const quantity = quantities.get(configured.id) ?? 0;
  const isDomainProduct = product.id === "domains";
  const requiresDomain = product.category === "Web Hosting" || product.category === "Email Hosting" || product.category === "Website Design";
  const selectedDomainExtension = domainExtensionChoices.find((choice) => choice.id === domainExtension);
  const storageFeature = product.features.find((feature) => feature.includes("GB"));
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  function shakeDomainSearch() {
    const searchElement = domainSearchContainerRef.current;
    if (!searchElement) return;
    searchElement.scrollIntoView({ behavior: "smooth", block: "center" });
    domainSearchRef.current?.focus({ preventScroll: true });
    searchElement.classList.remove("domain-choice-shake");
    void searchElement.offsetWidth;
    searchElement.classList.add("domain-choice-shake");
  }

  function shakeRequiredDomainSearch() {
    const searchElement = requiredDomainSearchContainerRef.current;
    if (!searchElement) return;
    searchElement.scrollIntoView({ behavior: "smooth", block: "center" });
    requiredDomainSearchRef.current?.focus({ preventScroll: true });
    searchElement.classList.remove("domain-choice-shake");
    void searchElement.offsetWidth;
    searchElement.classList.add("domain-choice-shake");
  }

  function validateDomainName(value: string) {
    const candidate = value.trim().toLowerCase().replace(/\.$/, "");
    const match = candidate.match(/^([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.(co\.zw|com|net|online)$/);
    const suffix = match?.[2];
    const extension = suffix === "co.zw" ? "co-zw" : suffix;
    if (!match || !extension || !domainExtensionChoices.some((choice) => choice.id === extension)) return null;
    return { name: candidate, extension };
  }

  function searchRequiredDomain() {
    const name = requiredDomainQuery.trim().toLowerCase().replace(/\.$/, "");
    if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(name)) {
      setRequiredDomainResult(null);
      setRequiredDomainError("Enter a valid domain name using letters, numbers, or hyphens.");
      shakeRequiredDomainSearch();
      return;
    }
    const extension = requiredDomainTld === "co-zw" ? "co.zw" : requiredDomainTld;
    const result = { name: `${name}.${extension}`, extension: requiredDomainTld };
    setRequiredDomainResult(result);
    setDomainExtension(result.extension);
    setRequiredDomainError("");
  }

  function handleAdd() {
    if (isDomainProduct && !domainResult) {
      setDomainSearchError("Search for a domain name before adding it to your cart.");
      shakeDomainSearch();
      return;
    }
    if (requiresDomain && !domainChoice) {
      setDomainChoiceError(true);
      const domainChoiceElement = domainChoiceRef.current;
      if (domainChoiceElement) {
        domainChoiceElement.scrollIntoView({ behavior: "smooth", block: "center" });
        domainChoiceElement.focus({ preventScroll: true });
        domainChoiceElement.classList.remove("domain-choice-shake");
        void domainChoiceElement.offsetWidth;
        domainChoiceElement.classList.add("domain-choice-shake");
      }
      return;
    }
    if (requiresDomain && domainChoice === "add" && !requiredDomainResult) {
      setRequiredDomainError("Search for a domain name before adding this service.");
      shakeRequiredDomainSearch();
      return;
    }
    if (requiresDomain && domainChoice === "add" && requiredDomainResult) {
      addToCart("domains", { extension: requiredDomainResult.extension }, requiredDomainResult.name);
    }
    const options = isDomainProduct && domainResult
      ? { ...configured.options, extension: domainResult.extension }
      : configured.options;
    addToCart(product.id, options, isDomainProduct ? domainResult?.name : undefined);
    setAdded(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setAdded(false), 1100);
  }
  function changeOption(optionId: string, value: string) {
    setAdded(false);
    onSelectionsChange({ ...selections, [optionId]: value });
  }

  function searchDomain() {
    const result = validateDomainName(domainQuery);
    if (!result) {
      setDomainResult(null);
      setDomainSearchError("Enter a valid name ending in .co.zw, .com, .net, or .online.");
      shakeDomainSearch();
      return;
    }
    setDomainResult(result);
    setDomainSearchError("");
    changeOption("extension", result.extension);
  }

  return (
    <li id={product.id} data-product-id={product.id} data-service={product.visual} style={{ "--shop-image": `url(${product.image})` } as CSSProperties} className="shop-service-row scroll-mt-24 border-b last:border-b-0">
      <Collapsible className="group/row transition-colors hover:bg-muted/15 data-[state=open]:bg-muted/20">
        <div className="grid gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_140px] lg:gap-6">
          <div className="shop-service-identity relative isolate min-w-0 self-stretch overflow-hidden">
            <div className="shop-service-art pointer-events-none absolute inset-x-0 top-0" aria-hidden="true" />
            <div className="absolute inset-x-3 top-3 z-20 flex items-start justify-between gap-2">
              <span className="rounded-md border border-orange-500/40 bg-background/90 px-2.5 py-1.5 text-xs font-semibold text-orange-700 shadow-sm backdrop-blur-sm dark:text-orange-300">
                From ${fromPrice.toFixed(2)}{product.id === "domains" ? "/yr" : product.cadence}
              </span>
              <div className="group/learn relative">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  aria-expanded={learnMoreOpen}
                  aria-controls={product.id + "-learn-more"}
                  onClick={() => setLearnMoreOpen((open) => !open)}
                  className="h-8 gap-1.5 border-orange-500/30 bg-background/90 px-2.5 text-xs shadow-sm backdrop-blur-sm"
                >
                  <Info aria-hidden="true" className="size-3.5 text-orange-600 dark:text-orange-400" />
                  {learnMoreOpen ? "Close" : "Learn more"}
                </Button>
                <div
                  id={product.id + "-learn-more"}
                  className={cn(
                    "absolute top-full right-0 mt-2 w-[min(18rem,calc(100vw-7rem))] rounded-lg border bg-popover p-3 text-left text-xs text-popover-foreground opacity-0 shadow-xl transition duration-200 motion-reduce:transition-none",
                    "pointer-events-none translate-y-1 group-hover/learn:pointer-events-auto group-hover/learn:translate-y-0 group-hover/learn:opacity-100 group-focus-within/learn:pointer-events-auto group-focus-within/learn:translate-y-0 group-focus-within/learn:opacity-100",
                    learnMoreOpen && "pointer-events-auto translate-y-0 opacity-100",
                  )}
                >
                  <p className="mb-1 font-semibold">{product.name}, in simple terms</p>
                  <p className="text-muted-foreground leading-relaxed">{simpleExplanation(product)}</p>
                </div>
              </div>
            </div>
            {product.popular && <div className="absolute top-12 right-3 z-10"><PromotionTag kind="popular" className="w-16" /></div>}
            <div className="shop-service-copy relative min-w-0">
              <div className="shop-service-category mb-2 text-[10px] font-bold uppercase tracking-[.12em]">{product.category}</div>
              <div>
                <h3 className="text-xl leading-tight font-bold tracking-tight sm:text-[22px]">{product.name}</h3>
              </div>
              <p className="text-muted-foreground mt-2 max-w-md text-xs leading-relaxed">{product.description}</p>
              <div className="shop-service-feature mt-3 inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-semibold">
                {storageFeature ? <HardDrive aria-hidden="true" className="size-3.5 shrink-0" /> : <Check aria-hidden="true" className="size-3.5 shrink-0" />}
                <span>{storageFeature || product.features[0]}</span>
              </div>
              <div>
              <CollapsibleTrigger className="text-muted-foreground hover:text-foreground mt-2 inline-flex items-center gap-1 text-[11px] font-medium focus-visible:outline-2 focus-visible:outline-ring" aria-label={"View details for " + product.name}>
                What’s included <ChevronDown className="size-3 transition-transform group-data-[state=open]/row:rotate-180 motion-reduce:transition-none" />
              </CollapsibleTrigger>
              </div>
            </div>
          </div>
          <fieldset className="min-w-0 self-center">
            <legend className="mb-1 flex items-center gap-2 text-xs font-semibold"><SlidersHorizontal aria-hidden="true" className="shop-service-category size-3.5" />Select your add-ons<span className="sr-only"> for {product.name}</span></legend>
            <p className="text-muted-foreground mb-4 text-[11px]">Optional. Choose below to update your total.</p>
            {isDomainProduct && (
              <div
                ref={domainSearchContainerRef}
                className={cn("mb-4 rounded-lg border border-orange-200 bg-orange-50/40 p-3 outline-none transition-colors dark:border-orange-900 dark:bg-orange-950/10", domainSearchError ? "ring-2 ring-orange-500/30" : "")}
              >
                <label htmlFor="shop-domain-search" className="mb-2 block text-[11px] font-semibold">Search for a domain</label>
                <div className="flex min-w-0 gap-2">
                  <Input
                    ref={domainSearchRef}
                    id="shop-domain-search"
                    value={domainQuery}
                    onChange={(event) => {
                      setDomainQuery(event.target.value);
                      setDomainResult(null);
                      setDomainSearchError("");
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        searchDomain();
                      }
                    }}
                    placeholder="yourbusiness.co.zw"
                    aria-invalid={Boolean(domainSearchError)}
                    aria-describedby={domainSearchError ? "shop-domain-search-error" : undefined}
                    className="h-9 min-w-0 flex-1 border-orange-300 bg-background text-xs focus-visible:border-orange-500 focus-visible:ring-orange-500/30 dark:border-orange-800"
                  />
                  <Button type="button" size="sm" variant="outline" className="h-9 shrink-0 gap-1.5 border-orange-300 text-orange-700 hover:bg-orange-100 dark:border-orange-800 dark:text-orange-300 dark:hover:bg-orange-950" onClick={searchDomain}>
                    <Search className="size-3.5" />Search
                  </Button>
                </div>
                {domainSearchError && <p id="shop-domain-search-error" role="alert" className="mt-2 text-xs font-medium text-orange-600 dark:text-orange-400">{domainSearchError}</p>}
                {domainResult && (
                  <div role="status" className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/5 px-3 py-2 text-xs">
                    <span className="flex min-w-0 items-center gap-1.5 font-medium break-all text-emerald-700 dark:text-emerald-400">
                      <Check aria-hidden="true" className="size-3.5 shrink-0" />{domainResult.name} · Sample available
                    </span>
                    <span className="shrink-0 font-semibold">${configured.unitPrice.toFixed(2)}/yr</span>
                    <span className="text-muted-foreground w-full text-[10px]">Demo availability only; a live domain check is not connected.</span>
                  </div>
                )}
              </div>
            )}
            {requiresDomain && (
              <fieldset
                ref={domainChoiceRef}
                tabIndex={-1}
                aria-describedby={domainChoiceError ? product.id + "-domain-error" : undefined}
                className={cn("mb-4 rounded-lg border bg-muted/20 p-3 outline-none transition-colors", domainChoiceError && !domainChoice ? "border-orange-500 ring-2 ring-orange-500/30" : "border-border")}
              >
                <legend className="px-1 text-[11px] font-semibold">This service needs a domain</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className={cn("flex cursor-pointer items-start gap-2 rounded-md border p-2.5 text-xs transition-colors", domainChoice === "existing" ? "border-brand bg-brand/5" : "hover:bg-muted/40")}>
                    <input
                      type="radio"
                      name={product.id + "-domain-choice"}
                      value="existing"
                      required
                      checked={domainChoice === "existing"}
                      onChange={() => { setDomainChoice("existing"); setDomainChoiceError(false); }}
                      className="accent-orange-500"
                    />
                    <span><span className="block font-medium">I already have a domain</span><span className="text-muted-foreground mt-0.5 block">Use a domain you own.</span></span>
                  </label>
                  <label className={cn("flex cursor-pointer items-start gap-2 rounded-md border p-2.5 text-xs transition-colors", domainChoice === "add" ? "border-brand bg-brand/5" : "hover:bg-muted/40")}>
                    <input
                      type="radio"
                      name={product.id + "-domain-choice"}
                      value="add"
                      required
                      checked={domainChoice === "add"}
                      onChange={() => { setDomainChoice("add"); setDomainChoiceError(false); }}
                      className="accent-orange-500"
                    />
                    <span><span className="block font-medium">Add a domain to my cart</span><span className="text-muted-foreground mt-0.5 block">Search for its name and extension.</span></span>
                  </label>
                </div>
                {domainChoiceError && !domainChoice && (
                  <p id={product.id + "-domain-error"} role="alert" className="mt-2 text-xs font-medium text-orange-600 dark:text-orange-400">
                    Choose whether you already have a domain or want to add one, then select Add to cart again.
                  </p>
                )}
                {domainChoice === "add" && (
                  <div className="mt-3">
                    <label htmlFor={product.id + "-required-domain-search"} className="mb-1.5 block text-[11px] font-medium">Search for the domain to add</label>
                    <div
                      ref={requiredDomainSearchContainerRef}
                      className={cn("rounded-md border border-orange-200 bg-orange-50/40 p-2 dark:border-orange-900 dark:bg-orange-950/10", requiredDomainError ? "ring-2 ring-orange-500/30" : "")}
                    >
                      <div className="flex min-w-0 gap-2">
                        <Input
                          ref={requiredDomainSearchRef}
                          id={product.id + "-required-domain-search"}
                          value={requiredDomainQuery}
                          onChange={(event) => {
                            setRequiredDomainQuery(event.target.value);
                            setRequiredDomainResult(null);
                            setRequiredDomainError("");
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              searchRequiredDomain();
                            }
                          }}
                          placeholder="yourbusiness"
                          aria-invalid={Boolean(requiredDomainError)}
                          aria-describedby={requiredDomainError ? product.id + "-required-domain-error" : undefined}
                          className="h-9 min-w-0 flex-1 border-orange-300 bg-background text-xs focus-visible:border-orange-500 focus-visible:ring-orange-500/30 dark:border-orange-800"
                        />
                        <Select
                          value={requiredDomainTld}
                          onValueChange={(value) => {
                            setRequiredDomainTld(value);
                            setRequiredDomainResult(null);
                            setRequiredDomainError("");
                          }}
                        >
                          <SelectTrigger aria-label="Domain extension" className="h-9 w-[94px] shrink-0 border-orange-300 bg-background px-2 text-xs dark:border-orange-800">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent position="popper">
                            {domainExtensionChoices.map((choice) => (
                              <SelectItem key={choice.id} value={choice.id} className="text-xs">
                                {choice.id === "co-zw" ? ".co.zw" : `.${choice.id}`}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button type="button" size="sm" variant="outline" className="h-9 shrink-0 gap-1.5 border-orange-300 text-orange-700 hover:bg-orange-100 dark:border-orange-800 dark:text-orange-300 dark:hover:bg-orange-950" onClick={searchRequiredDomain}>
                          <Search className="size-3.5" />Search
                        </Button>
                      </div>
                    </div>
                    {requiredDomainError && <p id={product.id + "-required-domain-error"} role="alert" className="mt-2 text-xs font-medium text-orange-600 dark:text-orange-400">{requiredDomainError}</p>}
                    {requiredDomainResult && (
                      <div role="status" className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/5 px-3 py-2 text-xs">
                        <span className="flex min-w-0 items-center gap-1.5 font-medium break-all text-emerald-700 dark:text-emerald-400">
                          <Check aria-hidden="true" className="size-3.5 shrink-0" />{requiredDomainResult.name} · Sample available
                        </span>
                        <span className="shrink-0 font-semibold">${selectedDomainExtension?.price}/yr</span>
                        <span className="text-muted-foreground w-full text-[10px]">Demo availability only; a live domain check is not connected.</span>
                      </div>
                    )}
                  </div>
                )}
              </fieldset>
            )}
            {product.supportsYearly && (
              <div className="mb-4">
                <p className="mb-2 text-[11px] font-medium">Billing period</p>
                <div role="group" aria-label={product.name + " billing period"} className="bg-muted/60 inline-flex max-w-full items-center gap-1 rounded-full border p-1">
                  <Button type="button" size="sm" variant={configured.yearly ? "ghost" : "default"} className="h-8 rounded-full px-3 text-xs" aria-pressed={!configured.yearly} onClick={() => changeOption("billing", "monthly")}>Monthly</Button>
                  <Button type="button" size="sm" variant={configured.yearly ? "default" : "ghost"} className="h-8 rounded-full px-3 text-xs" aria-pressed={configured.yearly} onClick={() => changeOption("billing", "yearly")}>Yearly <span className="text-[10px]">Save 10%</span></Button>
                </div>
                <p className="text-muted-foreground mt-2 text-[10px]">{configured.yearly ? "Billed yearly. 10% off the plan and selected extras." : "Billed monthly. Switch to yearly to save 10%."}</p>
              </div>
            )}
            <div className="grid min-w-0 gap-3 sm:grid-cols-2">
              {product.options.map((option) => (
                isDomainProduct && option.id === "extension" ? null :
                <div key={option.id} className="min-w-0">
                  <div className="mb-1.5 flex min-h-8 flex-wrap items-center gap-2">
                    <label htmlFor={product.id + "-" + option.id} className="text-foreground/85 text-[11px] font-medium">{option.name}</label>
                    {option.free && <PromotionTag kind="free" />}
                  </div>
                  <Select value={selections[option.id] || ""} onValueChange={(value) => changeOption(option.id, value)}>
                    <div className="shop-addon-frame" data-selected={Boolean(selections[option.id] && selections[option.id] !== "none")}>
                      <SelectTrigger id={product.id + "-" + option.id} className="h-10 w-full min-w-0 text-xs [&>span]:truncate"><SelectValue placeholder="Select here" /></SelectTrigger>
                    </div>
                    <SelectContent position="popper" className="border-foreground/25 max-w-[calc(100vw-2rem)] shadow-xl">
                      {option.choices.map((choice) => <SelectItem key={choice.id} value={choice.id} className="text-xs">{choice.label}{choice.price > 0 ? ` (+$${billingPrice(choice.price, configured.yearly).toFixed(2)})` : choice.id !== "none" && option.free ? " (Free)" : ""}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
            <p className="text-muted-foreground mt-2 text-[10px]">Optional extras · {configured.cadence === "one time" ? "one-time prices" : "prices " + configured.cadence}</p>
          </fieldset>
          <div className="flex items-center justify-between gap-3 border-t border-dashed pt-3 lg:flex-col lg:items-stretch lg:justify-center lg:gap-5 lg:border-0 lg:pt-0">
            <div className="min-w-0 lg:text-right" role="status" aria-label={product.name + " configured price"}>
              <p className="text-lg font-semibold tracking-tight tabular-nums">${configured.unitPrice.toFixed(2)}</p>
              <p className="text-muted-foreground text-[10px] sm:text-[11px]">{configured.cadence}</p>
              {configured.yearly && <p className="text-orange-600 mt-1 text-[10px] dark:text-orange-400">${(configured.unitPrice / 12).toFixed(2)}/mo equivalent · Save 10%</p>}
              {configured.extraPrice > 0 && <p className="text-brand mt-1 text-[10px] tabular-nums">Includes ${configured.extraPrice.toFixed(2)} in extras</p>}
            </div>
            <div className="flex w-[108px] shrink-0 flex-col items-stretch gap-1.5 lg:w-full">
              <p className="text-muted-foreground text-center text-[10px] leading-tight [overflow-wrap:anywhere]">
                {isDomainProduct && domainResult
                  ? <>Adding <span className="text-orange-600 font-medium dark:text-orange-400">{domainResult.name}</span> · ${configured.unitPrice.toFixed(2)}/yr</>
                  : domainChoice === "add" && requiredDomainResult && selectedDomainExtension
                  ? <>Adding <span className="text-orange-600 font-medium dark:text-orange-400">{requiredDomainResult.name}</span> · ${selectedDomainExtension.price}/yr + </>
                  : null}
                {!isDomainProduct && <span>Adding <span className="text-orange-600 font-medium dark:text-orange-400">{product.name}</span> · ${configured.unitPrice.toFixed(2)} {configured.cadence}</span>}
              </p>
              <Button
                size="sm"
                variant="default"
                className="h-9 w-full gap-1.5"
                onClick={handleAdd}
                aria-label={added
                  ? (domainResult?.name ?? product.name) + " added to cart"
                  : "Add " + (domainResult?.name ?? product.name) + " to cart for $" + configured.unitPrice.toFixed(2) + " " + configured.cadence}
              >
                {added ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}{added ? "Added" : isDomainProduct ? "Add domain to cart" : requiresDomain && domainChoice === "add" ? "Add both to cart" : "Add to cart"}
              </Button>
              <span className="text-muted-foreground h-3 text-center text-[10px] tabular-nums">{quantity > 0 ? `${quantity} in cart` : ""}</span>
            </div>
          </div>
        </div>
        <CollapsibleContent>
          <div className="border-t border-dashed px-4 py-4 sm:px-6 lg:pl-[76px]">
            <p className="mb-3 text-xs font-medium">What’s included in the base price</p>
            <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {product.features.map((feature) => <li key={feature} className="text-muted-foreground flex items-start gap-2 text-xs"><Check className="text-brand size-3.5 shrink-0" />{feature}</li>)}
            </ul>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

export function ShopExperience() {
  const params = useSearchParams();
  const router = useRouter();
  const service = params.get("service") ?? "";
  const category = categories.find((item) => categoryServices[item.name] === service)?.name ?? "All";
  const selectedPlan = params.get("plan");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("featured");
  const { items, count } = useCart();
  const [selections, setSelections] = useState<Record<string, ShopSelections>>({});
  const yearlyDefault = params.get("billing") === "yearly";
  const effectiveSelections = useMemo(() => Object.fromEntries(shopProducts.map((product) => [product.id,
    selections[product.id] ?? (product.supportsYearly && yearlyDefault ? { billing: "yearly" } : {}),
  ])), [selections, yearlyDefault]);
  const selectedCategory = categories.find((item) => item.name === category)!;
  const quantities = new Map(items.map((item) => [item.id, item.quantity]));

  function setCategory(next: ShopCategory) {
    setSearch("");
    router.push(next === "All" ? "/shop/" : "/shop/?service=" + categoryServices[next], { scroll: false });
  }

  useEffect(() => {
    if (!selectedPlan) return;
    const product = shopProducts.find((item) => item.id === `${service}-${selectedPlan}` && item.category === category);
    if (product) document.getElementById(product.id)?.scrollIntoView({ block: "start" });
  }, [service, selectedPlan, category]);

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    const results = shopProducts.filter((product) => (category === "All" || product.category === category) &&
      (!query || [product.name, product.description, product.category, ...product.features, ...product.options.map((option) => option.name)].join(" ").toLowerCase().includes(query)));
    if (sort === "price-low") results.sort((a, b) => configureProduct(a, effectiveSelections[a.id]).unitPrice - configureProduct(b, effectiveSelections[b.id]).unitPrice);
    if (sort === "price-high") results.sort((a, b) => configureProduct(b, effectiveSelections[b.id]).unitPrice - configureProduct(a, effectiveSelections[a.id]).unitPrice);
    if (sort === "name") results.sort((a, b) => a.name.localeCompare(b.name));
    return results;
  }, [category, search, sort, effectiveSelections]);

  return (
    <main className="relative px-2 pt-6 pb-16 sm:px-4 sm:pt-10">
      <div className="max-w-container mx-auto">
        <SidebarProvider defaultOpen={true} className="min-h-0 items-stretch rounded-xl border bg-background shadow-xs">
          <ShopSidebar category={category} onCategoryChange={setCategory} cartCount={count} />
          <section className="min-w-0 flex-1 rounded-r-xl border-l" aria-label="Shop catalog">
            <div className="flex min-h-16 items-center justify-between gap-2 border-b px-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-2 text-xs"><ShoppingBag className="text-brand size-4 shrink-0" /><span className="text-muted-foreground">Shop</span><ChevronRight className="text-muted-foreground size-3 shrink-0" /><span className="truncate font-medium">{selectedCategory.label}</span></div>
              <Link href="/checkout/" className="text-muted-foreground hover:text-foreground hidden items-center gap-2 text-xs sm:flex">{count} in cart <ArrowRight className="size-3.5" /></Link>
            </div>
            <div className="px-4 py-6 sm:px-6 sm:py-8">
              <div className="mb-2 flex items-center gap-2"><span className="bg-brand size-1.5 rounded-full" /><span className="text-muted-foreground text-[10px] font-medium uppercase tracking-[.16em]">TechInn services</span></div>
              <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{category === "All" ? <>Build your <span className="text-orange-600 dark:text-orange-400">online presence.</span></> : selectedCategory.label}</h1>
              <p className="text-muted-foreground mt-2 max-w-xl text-xs leading-relaxed sm:text-sm">{category === "Website Design" ? "Start with a five-page website from $60. Add the features your business needs, each with its own price." : "Find your domain, hosting, email, and website services in one place."}</p>
            </div>
            <div className="flex flex-col gap-3 border-y bg-muted/20 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <div className="relative min-w-0 sm:w-72">
                <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2" />
                <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search services…" aria-label="Search shop products" className="h-9 bg-background pr-8 pl-9 text-xs" />
                {search && <button onClick={() => setSearch("")} aria-label="Clear search" className="text-muted-foreground absolute inset-y-0 right-0 flex w-8 items-center justify-center"><X className="size-3.5" /></button>}
              </div>
              <div className="flex items-center justify-between gap-3">
                <p role="status" className="text-muted-foreground whitespace-nowrap text-[11px] tabular-nums">{filteredProducts.length} services</p>
                <Select value={sort} onValueChange={setSort}>
                  <SelectTrigger aria-label="Sort services" className="h-9 w-36 bg-background text-xs"><ArrowDownWideNarrow className="size-3.5" /><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="featured">Featured</SelectItem><SelectItem value="price-low">Price: low to high</SelectItem><SelectItem value="price-high">Price: high to low</SelectItem><SelectItem value="name">Name</SelectItem></SelectContent>
                </Select>
              </div>
            </div>
            <div className="text-muted-foreground hidden grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_140px] gap-6 border-b px-6 py-3 text-[10px] font-medium uppercase tracking-wider lg:grid"><span>Service</span><span>Customize your service</span><span className="text-right">Your total · USD</span></div>
            {filteredProducts.length ? (
              <ul aria-label="Services" className="m-0 list-none p-0">{filteredProducts.map((product) => <ProductRow key={product.id} product={product} selections={effectiveSelections[product.id]} onSelectionsChange={(value) => setSelections((current) => ({ ...current, [product.id]: value }))} quantities={quantities} />)}</ul>
            ) : (
              <div className="px-4 py-16 text-center"><Search className="text-muted-foreground mx-auto mb-3 size-6" /><p className="text-sm font-medium">No services found</p><p className="text-muted-foreground mt-1 text-xs">Try a different search or category.</p><Button variant="link" size="sm" onClick={() => { setSearch(""); setCategory("All"); }}>Show all services</Button></div>
            )}
            <div className="text-muted-foreground border-t px-4 py-4 text-[10px] sm:px-6">Prices in USD. Billing terms are shown beside each service.</div>
          </section>
        </SidebarProvider>
      </div>
    </main>
  );
}
