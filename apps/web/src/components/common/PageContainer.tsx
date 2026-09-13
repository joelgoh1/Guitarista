import * as React from "react";
import { cn } from "@/lib/utils";

/** Standard content width + padding for non-full-bleed pages. */
export function PageContainer({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="page-container"
      className={cn("mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-8 lg:py-10", className)}
      {...props}
    />
  );
}
