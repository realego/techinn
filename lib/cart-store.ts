"use client";

import { useMemo, useSyncExternalStore } from "react";

import { configureProduct, shopProducts, type ShopSelections } from "@/config/shop-products";

export interface CartLine {
  id: string;
  productId: string;
  quantity: number;
  options: ShopSelections;
  domainName?: string;
}
const storageKey = "techinn-shop-cart";
const cartChangedEvent = "techinn-shop-cart-change";
const emptyCart = "[]";
const products = new Map(shopProducts.map((product) => [product.id, product]));
let fallbackSnapshot = emptyCart;

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(cartChangedEvent, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(cartChangedEvent, onChange);
  };
}
function getSnapshot() {
  try { return localStorage.getItem(storageKey) ?? emptyCart; }
  catch { return fallbackSnapshot; }
}
function parseCart(snapshot: string): CartLine[] {
  try {
    const parsed: unknown = JSON.parse(snapshot);
    if (!Array.isArray(parsed)) return [];
    const lines = new Map<string, CartLine>();
    for (const item of parsed) {
      if (!item || typeof item.productId !== "string" || !Number.isSafeInteger(item.quantity) || item.quantity <= 0) continue;
      const product = products.get(item.productId);
      if (!product) continue;
      // Old carts without options keep their base services; prices always come from the catalog.
      const configuration = configureProduct(product, item.options && typeof item.options === "object" ? item.options : {});
      const domainName = product.id === "domains" && typeof item.domainName === "string" ? item.domainName : undefined;
      const id = domainName ? configuration.id + ":" + domainName : configuration.id;
      const existing = lines.get(id);
      const quantity = domainName ? 1 : (existing?.quantity ?? 0) + item.quantity;
      lines.set(id, { id, productId: product.id, quantity, options: configuration.options, ...(domainName ? { domainName } : {}) });
    }
    return [...lines.values()];
  } catch { return []; }
}
function writeCart(items: CartLine[]) {
  fallbackSnapshot = JSON.stringify(items);
  try { localStorage.setItem(storageKey, fallbackSnapshot); } catch { /* Keep the current session usable if storage is disabled. */ }
  window.dispatchEvent(new Event(cartChangedEvent));
}
export function addToCart(productId: string, options: ShopSelections = {}, domainName?: string) {
  const product = products.get(productId);
  if (!product) return;
  const configuration = configureProduct(product, options);
  const items = parseCart(getSnapshot());
  const validDomainName = productId === "domains" ? domainName : undefined;
  const id = validDomainName ? configuration.id + ":" + validDomainName : configuration.id;
  const existing = items.find((item) => item.id === id);
  if (existing && productId !== "domains") existing.quantity += 1;
  else if (existing) return;
  else items.push({ id, productId, quantity: 1, options: configuration.options, ...(validDomainName ? { domainName: validDomainName } : {}) });
  writeCart(items);
}
export function setCartQuantity(lineId: string, quantity: number) {
  if (!Number.isSafeInteger(quantity)) return;
  writeCart(parseCart(getSnapshot()).map((item) => item.id === lineId
    ? { ...item, quantity: item.productId === "domains" ? 1 : quantity }
    : item).filter((item) => item.quantity > 0));
}
export function removeFromCart(lineId: string) {
  writeCart(parseCart(getSnapshot()).filter((item) => item.id !== lineId));
}
export function clearCart() { writeCart([]); }
export function useCart() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, () => emptyCart);
  return useMemo(() => {
    const items = parseCart(snapshot);
    const lines = items.map((item) => {
      const product = products.get(item.productId)!;
      return { ...item, product, ...configureProduct(product, item.options), id: item.id };
    });
    const count = items.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = lines.reduce((sum, line) => sum + Math.round(line.unitPrice * 100) * line.quantity, 0) / 100;
    return { items, lines, count, subtotal };
  }, [snapshot]);
}
