import { cn } from "@/lib/utils";

interface Props {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizes = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-10 w-10" };

export default function Spinner({ size = "md", className }: Props) {
  return (
    <div
      role="status"
      className={cn(
        "inline-block animate-spin rounded-full border-2 border-current border-t-transparent text-brand-600",
        sizes[size],
        className
      )}
    />
  );
}
