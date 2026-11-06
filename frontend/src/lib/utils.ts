import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Utility for merging Tailwind CSS class names with conflict resolution.
 * Used by shadcn/ui components throughout the application.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
