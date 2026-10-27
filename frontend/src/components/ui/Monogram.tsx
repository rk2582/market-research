const SIZES = {
  sm: "h-12 w-12 rounded-xl text-[22px]",
  md: "h-15 w-15 rounded-2xl text-[28px]",
  lg: "h-20 w-20 rounded-[22px] text-[38px] shadow-float",
};

/** A company's first letter in a rounded tile (stands in for a logo). */
export function Monogram({
  name,
  size = "sm",
  onMuted = false,
  className = "",
}: {
  name: string;
  size?: keyof typeof SIZES;
  onMuted?: boolean; // placed on a grey card: use a white tile
  className?: string;
}) {
  const letter = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden="true"
      className={`flex flex-none items-center justify-center font-bold text-ink ${size === "lg" || onMuted ? "bg-surface" : "bg-surface-2"} ${SIZES[size]} ${className}`}
    >
      {letter}
    </span>
  );
}
