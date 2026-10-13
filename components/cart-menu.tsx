"use client";

import { Minus, Plus, ShoppingCart, Trash2 } from "lucide-react";
import Link from "next/link";

import { CartLineOptions } from "@/components/cart-line-options";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { removeFromCart, setCartQuantity, useCart } from "@/lib/cart-store";


export function CartMenu() {
  const { lines, count, subtotal } = useCart();
  const label = count === 1 ? "1 item" : count + " items";

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative size-9 shrink-0 rounded-lg border border-border/40 bg-muted/30"
          aria-label={"Cart, " + label}
        >
          <ShoppingCart className="size-4" />
          <span aria-hidden="true" className="bg-primary text-primary-foreground ring-background pointer-events-none absolute -top-0.5 -right-0.5 flex h-[18px] min-w-[18px] items-center justify-center overflow-hidden rounded-full px-1 text-[10px] leading-none font-semibold tabular-nums ring-2">
            <span key={count} className="cart-count-digit">{count > 99 ? "99+" : count}</span>
          </span>
        </Button>
      </DropdownMenuTrigger>
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">{label} in your cart</span>
      <DropdownMenuContent
        align="end"
        sideOffset={10}
        collisionPadding={12}
        className="flex max-h-[min(640px,var(--radix-dropdown-menu-content-available-height))] w-[min(366px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-xl p-0 shadow-xl motion-reduce:animate-none"
      >
        <div className="flex shrink-0 items-center justify-between border-b px-4 py-3.5">
          <div>
            <p className="font-semibold">Your cart</p>
            <p className="text-muted-foreground text-xs">{label}</p>
          </div>
          <ShoppingCart className="text-brand size-5" />
        </div>

        {lines.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <div className="bg-muted mx-auto mb-3 flex size-11 items-center justify-center rounded-full">
              <ShoppingCart className="text-muted-foreground size-5" />
            </div>
            <p className="font-medium">Your cart is empty</p>
            <p className="text-muted-foreground mt-1 text-sm">Browse services and add a plan to get started.</p>
            <Button asChild variant="outline" size="sm" className="mt-4">
              <Link href="/shop/">Browse shop</Link>
            </Button>
          </div>
        ) : (
          <>
            <div className="min-h-0 divide-y overflow-y-auto overscroll-contain px-4">
              {lines.map((line) => (
                <div key={line.id} className="flex gap-3 py-4">
                  <div className="bg-brand/10 text-brand flex size-10 shrink-0 items-center justify-center rounded-lg text-xs font-semibold">
                    {line.product.category === "Website Design" ? "WEB" : line.product.category === "Email Hosting" ? "MAIL" : line.product.category === "Domains" ? "DNS" : line.product.category === "App Development" ? "APP" : "HOST"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{line.domainName ?? line.product.name}</p>
                        <p className="text-muted-foreground mt-0.5 text-xs">
                          ${line.unitPrice.toFixed(2)} {line.cadence}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-destructive size-7 shrink-0"
                        aria-label={"Remove " + line.product.name}
                        onClick={() => removeFromCart(line.id)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                    <CartLineOptions options={line.selectedOptions} />
                    <div className="mt-2 flex items-center justify-between">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="outline"
                          size="icon"
                          className="size-7"
                          aria-label={"Decrease " + line.product.name + " quantity"}
                          onClick={() => setCartQuantity(line.id, line.quantity - 1)}
                        >
                          <Minus className="size-3" />
                        </Button>
                        <span className="w-7 text-center text-xs font-medium tabular-nums">{line.quantity}</span>
                        <Button
                          variant="outline"
                          size="icon"
                          className="size-7"
                          aria-label={"Increase " + line.product.name + " quantity"}
                          onClick={() => setCartQuantity(line.id, line.quantity + 1)}
                        >
                          <Plus className="size-3" />
                        </Button>
                        {line.product.quantityLabel ? (
                          <span className="text-muted-foreground ml-1 text-xs">{line.product.quantityLabel}{line.quantity > 1 ? "s" : ""}</span>
                        ) : null}
                      </div>
                      <span className="text-sm font-medium tabular-nums">${(line.unitPrice * line.quantity).toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="bg-muted/30 shrink-0 border-t px-4 py-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-muted-foreground text-sm">Subtotal</span>
                <span className="text-lg font-semibold">${subtotal.toFixed(2)}</span>
              </div>
              <p className="text-muted-foreground mb-3 text-[11px]">Subtotal includes the first billing period for each service. Yearly services are charged for the full year.</p>
              <Button asChild className="w-full">
                <Link href="/checkout/">Continue to checkout</Link>
              </Button>
            </div>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
