import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Class names joined, with a later Tailwind class overriding an earlier one of its kind. */
export function cn(...classes: ClassValue[]): string {
  return twMerge(clsx(classes));
}
