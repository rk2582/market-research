import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "quiet";

const STYLES: Record<Variant, string> = {
  primary:
    "min-h-11 rounded-full bg-accent px-5 text-on-accent font-medium hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50",
  secondary:
    "min-h-11 rounded-full bg-rule px-5 text-ink hover:bg-unconfirmed-tint disabled:cursor-not-allowed disabled:opacity-50",
  quiet: "rounded-md px-1 py-1 text-accent-ink hover:underline",
};

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 text-[15px] transition ${STYLES[variant]} ${className}`}
      {...props}
    />
  );
}
