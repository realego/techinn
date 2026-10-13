"use client";

import { ArrowLeft, CheckCircle2, CircleX, LoaderCircle, Minus, Plus, Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { CartLineOptions } from "@/components/cart-line-options";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, cancelCheckoutPayment, type CheckoutPayment, createCheckoutPayment, getApiSession, pollCheckoutPayment } from "@/lib/api";
import { useVisitAttribution } from "@/lib/attribution";
import { useSignedIn } from "@/lib/auth";
import { useSignInHref } from "@/lib/auth-redirect";
import { clearCart, removeFromCart, setCartQuantity, useCart } from "@/lib/cart-store";

const paymentMethods = [
  { id: "ecocash", label: "EcoCash", image: "/payment-methods/ecocash.png", width: 74, height: 22 },
  { id: "onemoney", label: "OneMoney", image: "/payment-methods/onemoney.png", width: 30, height: 22 },
  { id: "card", label: "Cards", image: "/payment-methods/cards.jpg", width: 72, height: 24 },
] as const;
const pollWindowMs = 90_000;
const checkoutKeyStorage = "techinn-checkout-key";
const checkoutCartStorage = "techinn-checkout-cart";

export function CheckoutExperience() {
  const [returnedPaymentUuid] = useState(() => (
    typeof window === "undefined"
      ? ""
      : new URLSearchParams(window.location.search).get("payment") ?? ""
  ));
  const { lines, subtotal: total } = useCart();
  const cartSignature = JSON.stringify(lines.map((line) => [line.id, line.quantity]));
  const isSignedIn = useSignedIn();
  const signInHref = useSignInHref();
  const customer = getApiSession()?.customer;
  const [paymentMethod, setPaymentMethod] = useState<(typeof paymentMethods)[number]["id"]>("ecocash");
  const [customNameservers, setCustomNameservers] = useState(false);
  const [postalSameAsPhysical, setPostalSameAsPhysical] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [pollStopped, setPollStopped] = useState(false);
  const [networkIssue, setNetworkIssue] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");
  const [cancelError, setCancelError] = useState("");
  const [payment, setPayment] = useState<CheckoutPayment | null>(null);
  const [checkoutStarted, setCheckoutStarted] = useState(
    () => typeof window !== "undefined" && Boolean(window.sessionStorage.getItem(checkoutKeyStorage)),
  );
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pollWindowStartedAt, setPollWindowStartedAt] = useState(
    () => returnedPaymentUuid ? Date.now() : 0,
  );
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pollInFlight = useRef(false);
  const checkoutKey = useRef<string | null>(
    typeof window === "undefined" ? null : window.sessionStorage.getItem(checkoutKeyStorage),
  );
  const clearedPayment = useRef<string | null>(null);
  const attribution = useVisitAttribution();
  const needsBusinessDetails = lines.some((line) => ["Web Hosting", "Email Hosting", "Website Design"].includes(line.product.category));
  const includesDomainRegistration = lines.some((line) => line.product.category === "Domains");

  const applyPaymentUpdate = useCallback((updated: CheckoutPayment) => {
    setPayment(updated);
    if (updated.status !== "successful" || clearedPayment.current === updated.uuid) return;
    clearedPayment.current = updated.uuid;
    const originalCart = window.sessionStorage.getItem(checkoutCartStorage);
    window.sessionStorage.removeItem(checkoutKeyStorage);
    window.sessionStorage.removeItem(checkoutCartStorage);
    checkoutKey.current = null;
    setCheckoutStarted(false);
    if (originalCart === cartSignature) clearCart();
  }, [cartSignature]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (dialogOpen && !dialog.open) dialog.showModal();
    if (!dialogOpen && dialog.open) dialog.close();
  }, [dialogOpen]);

  useEffect(() => {
    const paymentUuid = payment?.uuid;
    const paymentStatus = payment?.status;
    if (!paymentUuid || paymentStatus !== "processing" || pollStopped) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll(currentPaymentUuid: string) {
      if (cancelled) return;
      if (pollInFlight.current) {
        timer = setTimeout(() => poll(currentPaymentUuid), 1000);
        return;
      }
      if (Date.now() - pollWindowStartedAt >= pollWindowMs) {
        setPollStopped(true);
        return;
      }
      pollInFlight.current = true;
      setPolling(true);
      try {
        const updated = await pollCheckoutPayment(currentPaymentUuid);
        if (cancelled) return;
        applyPaymentUpdate(updated);
        setNetworkIssue(false);
      } catch {
        if (cancelled) return;
        setNetworkIssue(true);
      } finally {
        pollInFlight.current = false;
        if (!cancelled) setPolling(false);
      }
      if (!cancelled && Date.now() - pollWindowStartedAt < pollWindowMs) {
        timer = setTimeout(() => poll(currentPaymentUuid), 5000);
      } else if (!cancelled) {
        setPollStopped(true);
      }
    }

    timer = setTimeout(() => poll(paymentUuid), 4000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [payment?.uuid, payment?.status, pollStopped, pollWindowStartedAt, applyPaymentUpdate]);

  useEffect(() => {
    if (!isSignedIn || !returnedPaymentUuid) return;
    let cancelled = false;
    pollCheckoutPayment(returnedPaymentUuid)
      .then((updated) => {
        if (!cancelled) {
          applyPaymentUpdate(updated);
          setDialogOpen(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNetworkIssue(true);
          setDialogOpen(true);
        }
      });
    const url = new URL(window.location.href);
    url.searchParams.delete("payment");
    window.history.replaceState({}, "", url);
    return () => {
      cancelled = true;
    };
  }, [isSignedIn, returnedPaymentUuid, applyPaymentUpdate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setCheckoutError("");
    setNetworkIssue(false);
    setDialogOpen(true);
    const formData = new FormData(event.currentTarget);
    const details = Object.fromEntries(
      [
        "business_name", "business_type", "preferred_domain", "registrant_name",
        "registrant_business_name", "physical_address", "physical_city", "physical_country",
        "postal_same_as_physical", "postal_address", "postal_city", "postal_country",
        "nameserver_type", "nameserver_1", "nameserver_2", "nameserver_3", "nameserver_4",
        "nameserver_ip_1", "nameserver_ip_2", "nameserver_ip_3", "nameserver_ip_4",
      ]
        .map((key) => [key, String(formData.get(key) ?? "")])
        .filter(([, value]) => Boolean(value)),
    );
    if (postalSameAsPhysical) details.postal_same_as_physical = "true";
    const visitAttribution = Object.fromEntries(
      ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "landing_path"]
        .map((key) => [key, String(attribution?.[key as keyof typeof attribution] ?? "")])
        .filter(([, value]) => Boolean(value)),
    );
    if (!checkoutKey.current) {
      checkoutKey.current = crypto.randomUUID();
      window.sessionStorage.setItem(checkoutKeyStorage, checkoutKey.current);
      window.sessionStorage.setItem(checkoutCartStorage, cartSignature);
    }
    setCheckoutStarted(true);
    try {
      const result = await createCheckoutPayment({
        checkout_key: checkoutKey.current,
        payment_method: paymentMethod,
        displayed_total: total.toFixed(2),
        phone: String(formData.get("phone") ?? ""),
        payment_phone: String(formData.get("payment_phone") ?? ""),
        items: lines.map((line) => ({
          product_id: line.productId,
          quantity: line.quantity,
          options: line.options,
          ...(line.domainName ? { domain_name: line.domainName } : {}),
        })),
        details,
        attribution: visitAttribution,
      });
      applyPaymentUpdate(result);
      setPollWindowStartedAt(Date.now());
      setPollStopped(false);
      if (paymentMethod === "card" && result.redirect_url && result.status === "processing") {
        window.location.assign(result.redirect_url);
      }
    } catch (cause) {
      if (cause instanceof ApiError) {
        checkoutKey.current = null;
        window.sessionStorage.removeItem(checkoutKeyStorage);
        window.sessionStorage.removeItem(checkoutCartStorage);
        setCheckoutStarted(false);
      }
      setCheckoutError(
        cause instanceof Error
          ? cause.message
          : "We couldn’t start checkout. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function checkAgain() {
    if (!payment || pollInFlight.current || cancelling) return;
    pollInFlight.current = true;
    setPolling(true);
    setNetworkIssue(false);
    try {
      const updated = await pollCheckoutPayment(payment.uuid);
      applyPaymentUpdate(updated);
      setPollWindowStartedAt(Date.now());
      setPollStopped(false);
    } catch {
      setNetworkIssue(true);
      setPollWindowStartedAt(Date.now());
      setPollStopped(false);
    } finally {
      pollInFlight.current = false;
      setPolling(false);
    }
  }

  async function cancelPayment() {
    if (!payment || cancelling || polling) return;
    setCancelling(true);
    setCancelError("");
    setPollStopped(true);
    try {
      const updated = await cancelCheckoutPayment(payment.uuid);
      applyPaymentUpdate(updated);
      setNetworkIssue(false);
    } catch (cause) {
      setCancelError(
        cause instanceof Error
          ? cause.message
          : "We couldn't cancel the payment. Please try again.",
      );
      setPollStopped(false);
      setPollWindowStartedAt(Date.now());
    } finally {
      setCancelling(false);
    }
  }

  function tryNewPayment() {
    checkoutKey.current = null;
    window.sessionStorage.removeItem(checkoutKeyStorage);
    window.sessionStorage.removeItem(checkoutCartStorage);
    setCheckoutStarted(false);
    setPayment(null);
    setCheckoutError("");
    setNetworkIssue(false);
    setDialogOpen(false);
  }

  const customerName = [customer?.first_name, customer?.last_name].filter(Boolean).join(" ");
  const paymentInProgress = payment?.status === "processing";
  const orderLocked = checkoutStarted || paymentInProgress;

  return (
    <section className="px-4 pt-6 pb-24 sm:pt-8">
      <div className="max-w-container mx-auto">
        <Link href="/shop/" className="text-muted-foreground mb-8 inline-flex items-center gap-2 text-sm hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to shop
        </Link>
        <div className="mb-10">
          <Badge variant="outline" className="mb-4 border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-400">Secure checkout</Badge>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-5xl">Review your order</h1>
          <p className="text-muted-foreground mt-3 max-w-2xl">Confirm your services and contact details before continuing to payment.</p>
        </div>

        {lines.length === 0 ? (
          <Card className="mx-auto max-w-xl py-12 text-center">
            <CardHeader><CardTitle>Your cart is empty</CardTitle><CardDescription>Choose a service and its optional features to continue.</CardDescription></CardHeader>
            <CardContent><Button asChild><Link href="/shop/">Browse the shop</Link></Button></CardContent>
          </Card>
        ) : !isSignedIn ? (
          <Card className="mx-auto max-w-xl py-8 text-center">
            <CardHeader>
              <CardTitle>Sign in to continue</CardTitle>
              <CardDescription>Your cart is saved on this device. Sign in or create an account to submit your order and start a secure payment.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col justify-center gap-3 sm:flex-row">
              <Button asChild><Link href={signInHref}>Sign in or create an account</Link></Button>
              <Button asChild variant="outline"><Link href="/shop/">Continue shopping</Link></Button>
            </CardContent>
          </Card>
        ) : (
          <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_390px] lg:items-start">
            <div className="grid gap-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-3"><span className="bg-brand/10 text-brand flex size-9 items-center justify-center rounded-full text-sm font-semibold">1</span><div><CardTitle>Contact information</CardTitle><CardDescription>Order details will be saved to your TechInn account.</CardDescription></div></div>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-2 text-sm"><span className="font-medium">Full name</span><span className="text-muted-foreground min-h-10 rounded-md border px-3 py-2">{customerName || "TechInn customer"}</span></div>
                  <div className="grid gap-2 text-sm"><span className="font-medium">Email address</span><span className="text-muted-foreground min-h-10 rounded-md border px-3 py-2">{customer?.email}</span></div>
                  <label className="grid gap-2 text-sm font-medium sm:col-span-2">Contact phone number<Input autoComplete="tel" defaultValue={customer?.phone ?? ""} name="phone" placeholder="+263 ..." required type="tel" /></label>
                </CardContent>
              </Card>

              {needsBusinessDetails && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Business and website details</CardTitle>
                    <CardDescription>These details will be attached to your order so we can prepare your hosting or website service.</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-2 text-sm font-medium">Business or project name<Input autoComplete="organization" name="business_name" placeholder="Your business name" required /></label>
                    <label className="grid gap-2 text-sm font-medium">What does your business do?<Input name="business_type" placeholder="For example, catering or accounting" required /></label>
                    <label className="grid gap-2 text-sm font-medium sm:col-span-2">Preferred website name <span className="text-muted-foreground inline font-normal">(if known)</span><Input autoComplete="url" name="preferred_domain" placeholder="yourbusiness.co.zw" /></label>
                  </CardContent>
                </Card>
              )}

              {includesDomainRegistration && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Domain registrant and DNS details</CardTitle>
                    <CardDescription>These details are required for the domain registration request and will be sent to the registry.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label className="grid gap-2 text-sm font-medium">Registrant or owner name<Input autoComplete="name" defaultValue={customerName} name="registrant_name" required /></label>
                      <label className="grid gap-2 text-sm font-medium">Business or organization <span className="text-muted-foreground inline font-normal">(optional)</span><Input autoComplete="organization" defaultValue={customer?.company_name ?? ""} name="registrant_business_name" /></label>
                      <div className="grid gap-1 text-sm sm:col-span-2">
                        <span className="font-medium">Registrant email</span>
                        <span className="text-muted-foreground min-h-10 rounded-md border px-3 py-2">{customer?.email}</span>
                      </div>
                      <label className="grid gap-2 text-sm font-medium">Physical address<Input autoComplete="street-address" name="physical_address" placeholder="Street and building" required /></label>
                      <label className="grid gap-2 text-sm font-medium">City or town<Input autoComplete="address-level2" name="physical_city" required /></label>
                      <label className="grid gap-2 text-sm font-medium">Country<Input autoComplete="country-name" defaultValue="Zimbabwe" name="physical_country" required /></label>
                    </div>
                    <label className="flex items-start gap-2 text-sm">
                      <input checked={postalSameAsPhysical} className="mt-1 accent-amber-500" onChange={(event) => setPostalSameAsPhysical(event.target.checked)} type="checkbox" />
                      <span>Postal address is the same as the physical address</span>
                    </label>
                    {!postalSameAsPhysical && (
                      <div className="grid gap-4 sm:grid-cols-2">
                        <label className="grid gap-2 text-sm font-medium">Postal address<Input autoComplete="street-address" name="postal_address" required /></label>
                        <label className="grid gap-2 text-sm font-medium">Postal city or town<Input autoComplete="address-level2" name="postal_city" required /></label>
                        <label className="grid gap-2 text-sm font-medium">Postal country<Input autoComplete="country-name" name="postal_country" required /></label>
                      </div>
                    )}
                    <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm">
                      <input
                        checked={!customNameservers}
                        className="mt-0.5 accent-amber-500"
                        name="nameserver_type"
                        onChange={() => setCustomNameservers(false)}
                        type="radio"
                        value="techinn"
                      />
                      <span><span className="font-medium">Use TechInn nameservers</span><span className="text-muted-foreground mt-1 block">We’ll manage your DNS records in the TechInn portal.</span></span>
                    </label>
                    <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm">
                      <input
                        checked={customNameservers}
                        className="mt-0.5 accent-amber-500"
                        name="nameserver_type"
                        onChange={() => setCustomNameservers(true)}
                        type="radio"
                        value="custom"
                      />
                      <span><span className="font-medium">I have custom nameservers</span><span className="text-muted-foreground mt-1 block">Enter at least two nameservers from your DNS provider.</span></span>
                    </label>
                    {customNameservers && (
                      <div className="grid gap-3 sm:grid-cols-2">
                        {[1, 2, 3, 4].map((index) => (
                          <div key={index} className="grid gap-2 rounded-md border p-3 sm:grid-cols-2">
                            <label className="grid gap-2 text-sm font-medium">
                              Nameserver {index}{index > 2 && <span className="text-muted-foreground inline font-normal">(optional)</span>}
                              <Input autoComplete="off" name={`nameserver_${index}`} placeholder={`ns${index}.example.com`} required={index <= 2} />
                            </label>
                            <label className="grid gap-2 text-sm font-medium">
                              IPv4 or IPv6 address{index > 2 && <span className="text-muted-foreground inline font-normal">(optional)</span>}
                              <Input autoComplete="off" inputMode="url" name={`nameserver_ip_${index}`} placeholder="IPv4 or IPv6 address" />
                            </label>
                          </div>
                        ))}
                        <p className="text-muted-foreground text-xs sm:col-span-2">Enter the IP for each custom nameserver. IPs already configured for TechInn nameservers can be left blank.</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>

            <Card className="lg:sticky lg:top-24">
              <CardHeader>
                <CardTitle>Order summary</CardTitle>
                <CardDescription>{lines.length} {lines.length === 1 ? "service" : "services"} selected</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="divide-y">
                  {lines.map((line) => (
                    <div key={line.id} className="flex gap-3 py-4 first:pt-0">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{line.domainName ?? line.product.name}</p>
                        <p className="text-muted-foreground mt-1 text-xs">${line.unitPrice.toFixed(2)} {line.cadence}{line.yearly ? " · Yearly billing, 10% saved" : ""}</p>
                        <CartLineOptions options={line.selectedOptions} />
                        <div className="mt-3 flex items-center gap-1">
                          {line.product.category !== "Domains" ? (
                            <>
                              <Button type="button" variant="outline" size="icon" className="size-7" aria-label={"Decrease " + line.product.name} disabled={orderLocked} onClick={() => setCartQuantity(line.id, line.quantity - 1)}><Minus className="size-3" /></Button>
                              <span className="w-7 text-center text-xs">{line.quantity}</span>
                              <Button type="button" variant="outline" size="icon" className="size-7" aria-label={"Increase " + line.product.name} disabled={orderLocked} onClick={() => setCartQuantity(line.id, line.quantity + 1)}><Plus className="size-3" /></Button>
                            </>
                          ) : <span className="text-muted-foreground text-xs">One domain per registration</span>}
                          <Button type="button" variant="ghost" size="icon" className="text-muted-foreground hover:text-destructive ml-1 size-7" aria-label={"Remove " + line.product.name} disabled={orderLocked} onClick={() => removeFromCart(line.id)}><Trash2 className="size-3.5" /></Button>
                        </div>
                      </div>
                      <span className="shrink-0 text-sm font-medium">${(line.unitPrice * line.quantity).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-between border-t pt-4">
                  <span className="font-medium">Order total</span><span className="text-xl font-semibold">${total.toFixed(2)}</span>
                </div>
                <p className="text-muted-foreground mt-2 text-xs">Recurring terms are listed beside each service. Taxes, if applicable, are calculated at confirmation.</p>
                <fieldset className="mt-5 space-y-2.5">
                  <legend className="text-sm font-medium">Payment method</legend>
                  <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Payment method">
                    {paymentMethods.map((method) => (
                      <label
                        key={method.id}
                        className={"flex min-h-16 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border px-1.5 py-2 text-center transition-colors focus-within:ring-2 focus-within:ring-amber-500 " + (paymentMethod === method.id ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40" : "hover:border-amber-500/50 hover:bg-amber-500/5")}
                      >
                        <input
                          checked={paymentMethod === method.id}
                          className="sr-only"
                          name="paymentMethod"
                          onChange={() => setPaymentMethod(method.id)}
                          required
                          type="radio"
                          value={method.id}
                        />
                        <Image alt="" height={method.height} src={method.image} unoptimized width={method.width} />
                        <span className="text-[11px] font-medium leading-tight">{method.label}{method.id === "ecocash" ? " · Default" : ""}</span>
                      </label>
                    ))}
                  </div>
                  {paymentMethod !== "card" && (
                    <label className="grid gap-1.5 text-xs font-medium">
                      {paymentMethod === "ecocash" ? "EcoCash number to pay from" : "OneMoney number to pay from"}
                      <Input autoComplete="tel" className="h-9" inputMode="tel" name="payment_phone" placeholder="077 123 4567 or +263 77 123 4567" required type="tel" />
                      <span className="text-muted-foreground font-normal">We’ll convert the number to local format before sending it to Paynow.</span>
                    </label>
                  )}
                  <p className="text-muted-foreground text-[11px] leading-snug">Mobile money requests are sent securely through Paynow. Card payments continue on Paynow’s secure page.</p>
                </fieldset>
                {payment?.status === "processing" && (
                  <Button type="button" variant="outline" className="mt-4 w-full" onClick={() => setDialogOpen(true)}>
                    View payment status
                  </Button>
                )}
                <Button type="submit" className="mt-5 w-full" size="lg" loading={submitting} disabled={submitting || paymentInProgress}>
                  {submitting ? "Starting secure checkout" : paymentInProgress ? "Payment in progress" : `Pay $${total.toFixed(2)} with ${paymentMethods.find((method) => method.id === paymentMethod)?.label}`}
                </Button>
                <p className="text-muted-foreground mt-3 text-center text-[11px]">
                  {attribution?.utm_source ? `Visit source recorded: ${attribution.utm_source}. ` : ""}
                  Your card or mobile money details are handled by Paynow.
                </p>
              </CardContent>
            </Card>
          </form>
        )}
      </div>

      <dialog
        ref={dialogRef}
        aria-label="Payment status"
        className="m-auto w-[calc(100%-2rem)] max-w-lg border-0 bg-transparent p-0 backdrop:bg-black/50"
        onCancel={(event) => {
          event.preventDefault();
          setDialogOpen(false);
        }}
        onClose={() => setDialogOpen(false)}
      >
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              {payment?.status === "successful"
                ? <CheckCircle2 className="text-emerald-600 size-6" />
                : payment?.status === "failed" || payment?.status === "cancelled" || payment?.status === "expired" || payment?.status === "refunded" || checkoutError
                  ? <CircleX className="text-destructive size-6" />
                  : <LoaderCircle className="text-amber-600 size-6 animate-spin" />}
              <div>
                <CardTitle>
                  {checkoutError
                    ? "Checkout needs attention"
                    : payment?.status === "successful"
                      ? "Payment confirmed"
                      : payment?.status === "cancelled"
                        ? "Payment cancelled"
                        : payment?.status === "failed" || payment?.status === "expired" || payment?.status === "refunded"
                          ? "Payment not completed"
                        : submitting
                          ? "Starting your payment"
                          : "Checking your payment"}
                </CardTitle>
                <CardDescription>{checkoutError || payment?.message || "Please wait while we securely contact Paynow."}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {payment && (
              <div className="bg-muted/50 rounded-lg p-4 text-sm">
                <div className="flex justify-between gap-3"><span className="text-muted-foreground">Order</span><span className="font-medium">{payment.order_number}</span></div>
                <div className="mt-2 flex justify-between gap-3"><span className="text-muted-foreground">Amount</span><span className="font-semibold">{payment.currency} {Number(payment.amount).toFixed(2)}</span></div>
              </div>
            )}
            {payment?.status === "cancelled" && (
              <div role="status" className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
                <CircleX className="mt-0.5 size-5 shrink-0" />
                <div>
                  <p className="font-semibold">Payment cancelled</p>
                  <p className="mt-1">{payment.message}</p>
                </div>
              </div>
            )}
            {payment?.status === "processing" && (
              <p className="text-muted-foreground rounded-lg border p-3 text-sm">If a payment prompt appears, approve it on your phone. We’ll check the status automatically.</p>
            )}
            {payment?.status === "processing" && (
              <p className="text-muted-foreground text-xs">
                Canceling checks Paynow and cancels the order in TechInn. Paynow’s current integration cannot revoke a request already started, so a mobile prompt or hosted payment page may remain active. Any later payment confirmation will still update your order.
              </p>
            )}
            {networkIssue && (
              <p role="status" className="text-muted-foreground text-sm">We’re still checking. The connection was interrupted, but your payment has not been marked as failed. We’ll try again.</p>
            )}
            {cancelError && (
              <p role="alert" className="text-destructive text-sm">{cancelError}</p>
            )}
            {payment?.status === "processing" && pollStopped && (
              <p role="status" className="text-muted-foreground text-sm">This is taking longer than usual. Your payment is still being checked; please check again rather than submitting another payment.</p>
            )}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              {payment?.status === "successful" ? (
                <>
                  <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Close</Button>
                  <Button asChild><Link href="/dashboard/">Go to your dashboard</Link></Button>
                </>
              ) : payment?.status === "failed" || payment?.status === "cancelled" || payment?.status === "expired" || payment?.status === "refunded" ? (
                <>
                  <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Close</Button>
                  <Button type="button" onClick={tryNewPayment}>Start a new payment</Button>
                </>
              ) : (
                <>
                  <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Close</Button>
                  {payment && (
                    <>
                      <Button type="button" variant="outline" loading={cancelling} disabled={cancelling || polling} onClick={cancelPayment}>
                        {cancelling ? "Canceling payment" : "Cancel payment"}
                      </Button>
                      <Button type="button" loading={polling} disabled={polling || cancelling} onClick={checkAgain}>
                        {polling ? "Checking payment" : "Check payment status"}
                      </Button>
                    </>
                  )}
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </dialog>
    </section>
  );
}
